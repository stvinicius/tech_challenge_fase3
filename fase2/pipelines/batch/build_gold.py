#!/usr/bin/env python3
"""
Gold Layer -- S3 Silver (integrated Parquet) -> S3 Gold (analytical Parquet)

Reads the integrated Silver table (`literacy_indicator`, one row per
`municipality_id` + `year`) written by `process_silver.py` and produces 3
analytical tables ready to be consumed via Athena:

  - `municipality_indicator`: percentage of literate students by municipality
    and year (a "flattened" slice of Silver, already including the
    municipality/state attributes and the proficiency-level distribution)
  - `target_vs_result`: compares the actual result (`literacy_rate`) with the
    target set for that same year at 3 levels -- municipality, state and
    Brazil --, computing the gap (result - target) at each level. Since the
    National Commitment to Literate Children targets only exist from 2024
    onward (columns `*_target_literacy_2024..2030`), rows for earlier years
    (e.g., 2023) end up with null target/gap -- there is no target defined to
    compare against
  - `time_evolution`: historical series of the indicator aggregated by year,
    at the national and state levels (average literacy rate + the
    corresponding target and gap), useful for time-evolution charts

Written to `s3://<gold>/<table>/` -- `municipality_indicator` and
`target_vs_result` partitioned by `year/state_code` (same Hive layout as
Silver, for "partition projection" in Athena); `time_evolution` is a small,
aggregated table, written as a single Parquet file.

Usage:
  python pipelines/batch/build_gold.py
  python pipelines/batch/build_gold.py --dry-run                     # reads/writes locally to output/silver and output/gold
  python pipelines/batch/build_gold.py --silver-bucket my-silver --gold-bucket my-gold
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # enables `import process_silver`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # enables `import common`
from common import (  # noqa: E402
    GOLD_BUCKET,
    SILVER_BUCKET,
    get_logger,
    get_s3_client,
    read_partitioned_parquet_from_s3,
    read_partitioned_parquet_local,
    upload_dataframe_as_parquet,
    upload_dataframe_partitioned,
)
from process_silver import TARGET_YEARS, SILVER_TABLE_NAME  # noqa: E402

logger = get_logger("build_gold")

LEVEL_COLS = [f"proficiency_level_{i}_ratio" for i in range(9)]
PARTITION_COLS = ["year", "state_code"]

MUNICIPALITY_INDICATOR_TABLE = "municipality_indicator"
TARGET_VS_RESULT_TABLE = "target_vs_result"
TIME_EVOLUTION_TABLE = "time_evolution"


# --------------------------------------------------------------------------- #
# Silver reads
# --------------------------------------------------------------------------- #

def read_silver_from_s3(bucket: str, s3_client) -> pd.DataFrame:
    logger.info("Reading Silver: s3://%s/%s/", bucket, SILVER_TABLE_NAME)
    df = read_partitioned_parquet_from_s3(bucket, SILVER_TABLE_NAME, s3_client=s3_client)
    if not df.empty:
        df["year"] = df["year"].astype(int)
        df["state_code"] = df["state_code"].astype(str)
    return df


def read_silver_local(silver_dir: Path) -> pd.DataFrame:
    logger.info("[dry-run] Reading local Silver: %s/", silver_dir)
    df = read_partitioned_parquet_local(silver_dir)
    if df.empty:
        return df
    df["year"] = df["year"].astype(int)
    df["state_code"] = df["state_code"].astype(str)
    return df


# --------------------------------------------------------------------------- #
# Targets: pick the target value matching each row's own year
# --------------------------------------------------------------------------- #

def target_for_year(df: pd.DataFrame, level: str, target_years: tuple[int, ...] = TARGET_YEARS) -> pd.Series:
    """For each row, returns the value of the `<level>_target_literacy_<year>`
    column matching that row's own `year` (NaN if the year has no target
    defined -- targets only exist from 2024 onward)."""
    result = pd.Series(float("nan"), index=df.index, dtype="float64")
    for year in target_years:
        col = f"{level}_target_literacy_{year}"
        if col not in df.columns:
            continue
        mask = df["year"] == year
        if mask.any():
            result.loc[mask] = pd.to_numeric(df.loc[mask, col], errors="coerce")
    return result


# --------------------------------------------------------------------------- #
# Building the 3 analytical tables
# --------------------------------------------------------------------------- #

def build_municipality_indicator(silver_df: pd.DataFrame) -> pd.DataFrame:
    """% of literate students by municipality + year, with the location
    attributes and the proficiency-level distribution."""
    cols = [
        "year", "state_code", "state_name", "region", "municipality_id", "municipality_name",
        "literacy_rate", "avg_portuguese_score", "source", *LEVEL_COLS,
    ]
    df = silver_df[cols].copy()
    df = df.sort_values(["year", "state_code", "municipality_id"]).reset_index(drop=True)
    logger.info("  %s: %d row(s), %d column(s)", MUNICIPALITY_INDICATOR_TABLE, len(df), len(df.columns))
    return df


def build_target_vs_result(silver_df: pd.DataFrame) -> pd.DataFrame:
    """Compares the actual result with the target for the same year at 3
    levels (municipality, state, Brazil), computing the gap (result - target)
    at each one."""
    df = silver_df[
        ["year", "state_code", "state_name", "region", "municipality_id", "municipality_name", "literacy_rate"]
    ].copy()

    for level in ("municipality", "state", "national"):
        df[f"target_{level}"] = target_for_year(silver_df, level)
        df[f"gap_{level}"] = df["literacy_rate"] - df[f"target_{level}"]

    # nullable "boolean" dtype instead of object/pd.NA: guarantees a consistent
    # Arrow `bool` type across partitions even when an entire partition (e.g.,
    # year=2023, with no target defined) ends up 100% null -- avoids the same
    # inconsistent-schema problem described in process_silver.clean_streaming.
    df["reached_target_municipality"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    has_target = df["target_municipality"].notna()
    df.loc[has_target, "reached_target_municipality"] = df.loc[has_target, "gap_municipality"] >= 0

    df = df.sort_values(["year", "state_code", "municipality_id"]).reset_index(drop=True)
    logger.info("  %s: %d row(s), %d column(s)", TARGET_VS_RESULT_TABLE, len(df), len(df.columns))
    return df


def build_time_evolution(silver_df: pd.DataFrame) -> pd.DataFrame:
    """Historical series of the indicator aggregated by year, at the
    national and state levels (average literacy rate + the corresponding
    target/gap)."""
    tmp = silver_df.assign(
        _national_target=target_for_year(silver_df, "national"),
        _state_target=target_for_year(silver_df, "state"),
    )

    national = (
        tmp.groupby("year")
        .agg(
            municipalities_assessed=("municipality_id", "nunique"),
            avg_literacy_rate=("literacy_rate", "mean"),
            literacy_target=("_national_target", "first"),
        )
        .reset_index()
    )
    national.insert(0, "aggregation_level", "national")
    for col in ("state_code", "state_name", "region"):
        national[col] = None

    state = (
        tmp.groupby(["year", "state_code", "state_name", "region"], dropna=False)
        .agg(
            municipalities_assessed=("municipality_id", "nunique"),
            avg_literacy_rate=("literacy_rate", "mean"),
            literacy_target=("_state_target", "first"),
            **(
                {"official_state_indicator_rate": ("state_indicator_literacy_rate", "first")}
                if "state_indicator_literacy_rate" in tmp.columns
                else {}
            ),
        )
        .reset_index()
    )
    state.insert(0, "aggregation_level", "state")

    cols = [
        "aggregation_level", "year", "state_code", "state_name", "region",
        "municipalities_assessed", "avg_literacy_rate", "literacy_target",
    ]
    extra = ["official_state_indicator_rate"] if "official_state_indicator_rate" in state.columns else []
    if extra:
        national[extra[0]] = None
    df = pd.concat([national[cols + extra], state[cols + extra]], ignore_index=True)
    df["gap"] = df["avg_literacy_rate"] - df["literacy_target"]
    df["avg_literacy_rate"] = df["avg_literacy_rate"].round(2)
    df["gap"] = df["gap"].round(2)
    df = df.sort_values(["aggregation_level", "year", "state_code"], na_position="first").reset_index(drop=True)
    logger.info("  %s: %d row(s), %d column(s)", TIME_EVOLUTION_TABLE, len(df), len(df.columns))
    return df


# --------------------------------------------------------------------------- #
# Writing (partitioned S3 / single-file S3 / local --dry-run)
# --------------------------------------------------------------------------- #

def write_local_partitioned(df: pd.DataFrame, output_dir: Path, table_name: str, partition_cols: list[str]) -> list[Path]:
    base_dir = output_dir / table_name
    base_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for values, group in df.groupby(partition_cols, dropna=False):
        if not isinstance(values, tuple):
            values = (values,)
        partition_dir = base_dir
        for col, value in zip(partition_cols, values):
            partition_dir = partition_dir / f"{col}={value}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        path = partition_dir / f"{table_name}-{uuid.uuid4().hex[:12]}.parquet"
        group.drop(columns=partition_cols).to_parquet(path, index=False, engine="pyarrow")
        written.append(path)
    return written


def write_local_single(df: pd.DataFrame, output_dir: Path, table_name: str) -> Path:
    base_dir = output_dir / table_name
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{table_name}.parquet"
    df.to_parquet(path, index=False, engine="pyarrow")
    return path


def write_gold_table(
    df: pd.DataFrame,
    table_name: str,
    *,
    partitioned: bool,
    dry_run: bool,
    output_dir: Path,
    gold_bucket: str,
    s3_client,
) -> None:
    if dry_run:
        if partitioned:
            written = write_local_partitioned(df, output_dir, table_name, PARTITION_COLS)
            logger.info(
                "[dry-run] %s: %d Parquet file(s) written to %s/%s/ (partitioned by %s)",
                table_name, len(written), output_dir, table_name, "/".join(PARTITION_COLS),
            )
        else:
            path = write_local_single(df, output_dir, table_name)
            logger.info("[dry-run] %s: written to %s", table_name, path)
        return

    if partitioned:
        keys = upload_dataframe_partitioned(
            df, gold_bucket, table_name, PARTITION_COLS, filename_prefix=table_name, s3_client=s3_client
        )
        logger.info(
            "[OK] %s: %d Parquet file(s) written to s3://%s/%s/ (partitioned by %s)",
            table_name, len(keys), gold_bucket, table_name, "/".join(PARTITION_COLS),
        )
    else:
        key = f"{table_name}/{table_name}.parquet"
        upload_dataframe_as_parquet(df, gold_bucket, key, s3_client=s3_client)
        logger.info("[OK] %s: written to s3://%s/%s", table_name, gold_bucket, key)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--silver-bucket", default=SILVER_BUCKET, help=f"Silver S3 bucket (default: {SILVER_BUCKET})"
    )
    parser.add_argument(
        "--gold-bucket", default=GOLD_BUCKET, help=f"Gold S3 bucket (default: {GOLD_BUCKET})"
    )
    parser.add_argument(
        "--silver-dir",
        default="output/silver",
        help="Local folder with Silver, used in --dry-run mode (default: output/silver, "
        "the same default output of process_silver.py --dry-run)",
    )
    parser.add_argument(
        "--output-dir",
        default="output/gold",
        help="Local folder to write the Gold tables in --dry-run mode (default: output/gold)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Reads Silver from --silver-dir (local) instead of S3, and writes the result to --output-dir "
        "instead of S3 Gold",
    )
    args = parser.parse_args()

    logger.info(
        "== Gold layer: %s -> %s ==",
        f"s3://{args.silver_bucket}/{SILVER_TABLE_NAME}/" if not args.dry_run else f"{args.silver_dir}/",
        f"s3://{args.gold_bucket}/" if not args.dry_run else f"{args.output_dir}/",
    )

    try:
        if args.dry_run:
            silver_df = read_silver_local(Path(args.silver_dir))
        else:
            s3_client = get_s3_client()
            silver_df = read_silver_from_s3(args.silver_bucket, s3_client)
    except Exception:
        logger.exception(
            "Failed to read Silver -- make sure process_silver.py has already run successfully"
        )
        return 1

    if silver_df.empty:
        logger.error("Silver is empty -- aborting Gold build")
        return 1

    logger.info("Silver loaded: %d row(s), %d column(s)", len(silver_df), len(silver_df.columns))

    logger.info("-- Building the 3 analytical tables --")
    municipality_indicator_df = build_municipality_indicator(silver_df)
    target_vs_result_df = build_target_vs_result(silver_df)
    time_evolution_df = build_time_evolution(silver_df)

    s3_client = None if args.dry_run else get_s3_client()
    output_dir = Path(args.output_dir)

    logger.info("-- Writing Gold tables --")
    write_gold_table(
        municipality_indicator_df, MUNICIPALITY_INDICATOR_TABLE, partitioned=True,
        dry_run=args.dry_run, output_dir=output_dir, gold_bucket=args.gold_bucket, s3_client=s3_client,
    )
    write_gold_table(
        target_vs_result_df, TARGET_VS_RESULT_TABLE, partitioned=True,
        dry_run=args.dry_run, output_dir=output_dir, gold_bucket=args.gold_bucket, s3_client=s3_client,
    )
    write_gold_table(
        time_evolution_df, TIME_EVOLUTION_TABLE, partitioned=False,
        dry_run=args.dry_run, output_dir=output_dir, gold_bucket=args.gold_bucket, s3_client=s3_client,
    )

    logger.info("Gold layer built successfully: 3 table(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
