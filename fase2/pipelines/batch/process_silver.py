#!/usr/bin/env python3
"""
Silver Processing -- S3 Bronze (batch Parquet + streaming JSON) -> S3 Silver (partitioned Parquet)

Reads the 5 Bronze batch tables (states, municipalities, national_targets,
state_targets, municipality_targets, child_literacy_indicator) written by
`ingest_batch.py` and the Bronze streaming events written by
`lambda_consumer.py` / `producer.py --dry-run`, and produces a single table
integrated by `municipality_id + year`:

  - Selects the Municipal network as the representative value for each
    municipality/year in the indicator (see the `MUNICIPAL_NETWORK` comment
    for why)
  - Removes duplicates (key: municipality_id + year; batch takes priority
    over streaming)
  - Handles nulls in critical fields (drops them, logging the reason/count)
  - Standardizes column names (snake_case, via `common.standardize_columns`)
  - Normalizes keys: municipality_id zero-padded to 7 digits (IBGE), state_code
    upper-cased
  - Validates: literacy_rate between 0-100, municipality_id exists in the
    municipalities table, state_code belongs to the set of 27 states (basic
    row-by-row sanity checks)
  - Integrates the 6 entities (states, municipalities, national targets,
    state targets, municipality targets, literacy indicator) into a single
    wide table, per municipality/year
  - Runs the formal quality gate (`quality/validations.py`) on the already
    clean/integrated table, producing a report (JSON/HTML) in
    `s3://<quality-reports>/silver/`; if any check fails, Silver is NOT
    written

The result is written to `s3://<silver>/literacy_indicator/` in the Hive
layout `year=<year>/state_code=<uf>/*.parquet`, which the Glue Catalog/Athena
natively recognize as partitions.

Usage:
  python pipelines/batch/process_silver.py
  python pipelines/batch/process_silver.py --dry-run   # reads output/bronze, writes output/silver
  python pipelines/batch/process_silver.py --bronze-bucket my-bronze --silver-bucket my-silver
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # enables `import common`
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # enables `import quality.validations`
from common import (  # noqa: E402
    BRONZE_BUCKET,
    QUALITY_BUCKET,
    SILVER_BUCKET,
    get_logger,
    get_s3_client,
    list_s3_keys,
    read_ndjson_from_s3,
    read_ndjson_local,
    read_parquet_from_s3,
    read_parquet_local,
    standardize_columns,
    upload_dataframe_partitioned,
)
from quality.validations import run_quality_checks, save_report  # noqa: E402

logger = get_logger("process_silver")

RATE_RANGE = (0.0, 100.0)

# The child_literacy_indicator table has one row per municipality/year FOR
# EACH education network (codes observed in the data: "0", "2", "3", "5" --
# no category dictionary is available in the downloaded CSV). Investigating
# the data showed that code "0" is a rare subset (398 municipalities, only in
# 2024, with a much lower average than the other networks) -- it is not a
# "Total" aggregate. Code "3" (Municipal), on the other hand, has near-complete
# and STABLE coverage across both available years (5,448 municipalities in
# 2023 and in 2024) and its average is very close to the national target
# published in national_targets (network "Public"), which is expected: early
# childhood education and the initial years of elementary school -- the stage
# assessed here -- are, in Brazil, predominantly a municipal responsibility,
# and the municipal network is exactly the main target of the National
# Commitment to Literate Children. That's why we use the Municipal network as
# the representative row for each municipality/year, guaranteeing a unique,
# time-comparable key (municipality_id, year) before integration.
MUNICIPAL_NETWORK = "3"

TARGET_YEARS = tuple(range(2024, 2031))
SILVER_TABLE_NAME = "literacy_indicator"
PARTITION_COLS = ["year", "state_code"]


# --------------------------------------------------------------------------- #
# Bronze reads
# --------------------------------------------------------------------------- #

def read_bronze_table(
    bucket: str,
    prefix: str,
    table: str,
    s3_client,
    *,
    bronze_dir: Path | None = None,
    dry_run: bool = False,
    required: bool = True,
) -> pd.DataFrame:
    if dry_run:
        if bronze_dir is None:
            raise ValueError("bronze_dir is required in --dry-run")
        path = Path(bronze_dir) / prefix / table / f"{table}.parquet"
        if not path.exists():
            if required:
                raise FileNotFoundError(path)
            logger.warning("Optional local bronze table missing: %s -- skipping", path)
            return pd.DataFrame()
        logger.info("Reading bronze batch (local): %s", path)
        df = read_parquet_local(path)
        logger.info("  -> %d row(s), %d column(s)", len(df), len(df.columns))
        return df

    key = f"{prefix}/{table}/{table}.parquet"
    logger.info("Reading bronze batch: s3://%s/%s", bucket, key)
    try:
        df = read_parquet_from_s3(bucket, key, s3_client=s3_client)
    except Exception:
        if required:
            raise
        logger.warning("Optional bronze table missing: s3://%s/%s -- skipping", bucket, key)
        return pd.DataFrame()
    logger.info("  -> %d row(s), %d column(s)", len(df), len(df.columns))
    return df


def read_bronze_streaming(
    bucket: str,
    prefix: str,
    s3_client,
    *,
    bronze_dir: Path | None = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    if dry_run:
        stream_dir = Path(bronze_dir) / prefix if bronze_dir is not None else None
        if stream_dir is None or not stream_dir.exists():
            logger.warning(
                "No local streaming files under %s -- continuing with batch data only",
                stream_dir,
            )
            return pd.DataFrame()
        records: list[dict] = []
        files = [
            p for p in stream_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".json", ".ndjson", ".jsonl"}
        ]
        for path in files:
            records.extend(read_ndjson_local(path))
        logger.info("Reading bronze streaming (local): %d file(s), %d event(s)", len(files), len(records))
        return pd.DataFrame.from_records(records)

    keys = list_s3_keys(bucket, f"{prefix}/", s3_client=s3_client)
    if not keys:
        logger.warning(
            "No files found under s3://%s/%s/ -- continuing with batch data only", bucket, prefix
        )
        return pd.DataFrame()

    records = []
    for key in keys:
        records.extend(read_ndjson_from_s3(bucket, key, s3_client=s3_client))
    logger.info("Reading bronze streaming: %d file(s), %d event(s)", len(keys), len(records))
    return pd.DataFrame.from_records(records)


# --------------------------------------------------------------------------- #
# Per-entity cleaning / standardization
# --------------------------------------------------------------------------- #

def clean_states(df: pd.DataFrame) -> pd.DataFrame:
    df = standardize_columns(df)
    df = df.rename(columns={"sigla": "state_code", "nome": "state_name", "regiao": "region"})
    df["state_code"] = df["state_code"].str.upper().str.strip()
    df = df.drop_duplicates(subset=["state_code"])
    logger.info("  states: %d valid state(s)", len(df))
    return df[["state_code", "state_name", "region"]]


def clean_municipalities(df: pd.DataFrame) -> pd.DataFrame:
    df = standardize_columns(df)
    df["id_municipio"] = df["id_municipio"].astype(str).str.strip().str.zfill(7)
    df["sigla_uf"] = df["sigla_uf"].str.upper().str.strip()
    df = df.rename(columns={
        "id_municipio": "municipality_id",
        "sigla_uf": "state_code",
        "nome": "municipality_name",
        "nome_uf": "state_name",
        "nome_regiao": "region",
    })
    df = df.drop_duplicates(subset=["municipality_id"])
    return df[["municipality_id", "municipality_name", "state_code", "state_name", "region"]]


def _coerce_numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def clean_literacy_assessment(df: pd.DataFrame) -> pd.DataFrame:
    df = standardize_columns(df)
    df["id_municipio"] = df["id_municipio"].astype(str).str.strip().str.zfill(7)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")

    raw_level_cols = [f"proporcao_aluno_nivel_{i}" for i in range(9)]
    _coerce_numeric(df, ["taxa_alfabetizacao", "media_portugues", *raw_level_cols])

    before = len(df)
    df = df[df["rede"].astype(str).str.strip() == MUNICIPAL_NETWORK].copy()
    logger.info(
        "  child_literacy_indicator: keeping Municipal network (code %s) -> %d/%d row(s)",
        MUNICIPAL_NETWORK,
        len(df),
        before,
    )

    level_cols = [f"proficiency_level_{i}_ratio" for i in range(9)]
    df = df.rename(columns={
        "id_municipio": "municipality_id",
        "ano": "year",
        "taxa_alfabetizacao": "literacy_rate",
        "media_portugues": "avg_portuguese_score",
        **{f"proporcao_aluno_nivel_{i}": f"proficiency_level_{i}_ratio" for i in range(9)},
    })

    df["source"] = "batch"
    df["_source_priority"] = 0
    df["_event_timestamp"] = pd.NaT
    return df[["municipality_id", "year", "literacy_rate", "avg_portuguese_score", "source",
               "_source_priority", "_event_timestamp", *level_cols]]


def clean_streaming(df: pd.DataFrame) -> pd.DataFrame:
    level_cols = [f"proficiency_level_{i}_ratio" for i in range(9)]
    columns = ["municipality_id", "year", "literacy_rate", "avg_portuguese_score", "source",
               "_source_priority", "_event_timestamp", *level_cols]
    if df.empty:
        return pd.DataFrame(columns=columns)

    df = standardize_columns(df)
    df["municipality_id"] = df["municipality_id"].astype(str).str.strip().str.zfill(7)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["literacy_rate"] = pd.to_numeric(df["literacy_percentage"], errors="coerce")
    # float("nan") instead of pd.NA: keeps dtype float64 (same as batch) instead
    # of "object" -- this matters because 100%-null columns with dtype object
    # make PyArrow infer type `null` (instead of `double`) when writing the
    # Parquet for a streaming-only partition, producing an inconsistent schema
    # across partitions and breaking reads of the full Silver dataset.
    df["avg_portuguese_score"] = float("nan")
    for col in level_cols:
        df[col] = float("nan")
    df["source"] = df.get("source", "simulated-streaming")
    df["_source_priority"] = 1
    df["_event_timestamp"] = pd.to_datetime(df.get("event_timestamp"), errors="coerce", utc=True)
    return df[columns]


def clean_municipality_targets(df: pd.DataFrame) -> pd.DataFrame:
    df = standardize_columns(df)
    df["id_municipio"] = df["id_municipio"].astype(str).str.strip().str.zfill(7)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")

    raw_target_cols = [f"meta_alfabetizacao_{year}" for year in TARGET_YEARS]
    _coerce_numeric(df, ["taxa_alfabetizacao", "percentual_participacao", *raw_target_cols])

    df = df.rename(columns={
        "id_municipio": "municipality_id",
        "ano": "year",
        "taxa_alfabetizacao": "municipality_target_base_rate",
        "percentual_participacao": "municipality_target_participation_rate",
        "nivel_alfabetizacao": "municipality_target_literacy_level",
        **{f"meta_alfabetizacao_{year}": f"municipality_target_literacy_{year}" for year in TARGET_YEARS},
    })

    before = len(df)
    df = df.drop_duplicates(subset=["municipality_id", "year"])
    if len(df) != before:
        logger.warning(
            "  municipality_targets: %d duplicate row(s) by (municipality_id, year) removed", before - len(df)
        )

    keep = ["municipality_id", "year", "municipality_target_base_rate", "municipality_target_participation_rate",
            "municipality_target_literacy_level",
            *[f"municipality_target_literacy_{year}" for year in TARGET_YEARS]]
    return df[keep]


def clean_state_targets(df: pd.DataFrame) -> pd.DataFrame:
    df = standardize_columns(df)
    df["sigla_uf"] = df["sigla_uf"].str.upper().str.strip()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")

    raw_target_cols = [f"meta_alfabetizacao_{year}" for year in TARGET_YEARS]
    _coerce_numeric(df, ["taxa_alfabetizacao", "percentual_participacao", *raw_target_cols])

    df = df.rename(columns={
        "sigla_uf": "state_code",
        "ano": "year",
        "taxa_alfabetizacao": "state_target_base_rate",
        "percentual_participacao": "state_target_participation_rate",
        **{f"meta_alfabetizacao_{year}": f"state_target_literacy_{year}" for year in TARGET_YEARS},
    })
    df = df.drop_duplicates(subset=["state_code", "year"])

    keep = ["state_code", "year", "state_target_base_rate", "state_target_participation_rate",
            *[f"state_target_literacy_{year}" for year in TARGET_YEARS]]
    return df[keep]


def clean_literacy_indicator_uf(df: pd.DataFrame) -> pd.DataFrame:
    """Official INEP state/year indicator (municipal network), joined in Silver."""
    columns = ["state_code", "year", "state_indicator_literacy_rate"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    df = standardize_columns(df)
    df["sigla_uf"] = df["sigla_uf"].str.upper().str.strip()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["taxa_alfabetizacao"] = pd.to_numeric(df["taxa_alfabetizacao"], errors="coerce")

    before = len(df)
    if "rede" in df.columns:
        df = df[df["rede"].astype(str).str.strip() == MUNICIPAL_NETWORK].copy()
        logger.info(
            "  child_literacy_indicator_uf: keeping Municipal network (code %s) -> %d/%d row(s)",
            MUNICIPAL_NETWORK,
            len(df),
            before,
        )

    df = df.rename(columns={
        "sigla_uf": "state_code",
        "ano": "year",
        "taxa_alfabetizacao": "state_indicator_literacy_rate",
    })
    df = df.drop_duplicates(subset=["state_code", "year"])
    return df[columns]


def clean_national_targets(df: pd.DataFrame) -> pd.DataFrame:
    df = standardize_columns(df)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")

    raw_target_cols = [f"meta_alfabetizacao_{year}" for year in TARGET_YEARS]
    _coerce_numeric(df, ["taxa_alfabetizacao", "percentual_participacao", *raw_target_cols])

    df = df.rename(columns={
        "ano": "year",
        "taxa_alfabetizacao": "national_target_base_rate",
        "percentual_participacao": "national_target_participation_rate",
        **{f"meta_alfabetizacao_{year}": f"national_target_literacy_{year}" for year in TARGET_YEARS},
    })
    df = df.drop_duplicates(subset=["year"])

    keep = ["year", "national_target_base_rate", "national_target_participation_rate",
            *[f"national_target_literacy_{year}" for year in TARGET_YEARS]]
    return df[keep]


# --------------------------------------------------------------------------- #
# Deduplication + integration
# --------------------------------------------------------------------------- #

def build_indicators(batch_df: pd.DataFrame, streaming_df: pd.DataFrame) -> pd.DataFrame:
    """Merges batch indicator + streaming events and deduplicates by
    (municipality_id, year), prioritizing the batch data (official INEP
    history) over streaming (synthetic measurements); ties within streaming
    keep the most recent event."""
    combined = pd.concat([batch_df, streaming_df], ignore_index=True)
    combined = combined.sort_values(
        ["_source_priority", "_event_timestamp"], ascending=[True, False], na_position="last"
    )

    before = len(combined)
    combined = combined.drop_duplicates(subset=["municipality_id", "year"], keep="first")
    logger.info(
        "Deduplication by (municipality_id, year): %d -> %d row(s) (%d duplicate(s) removed, "
        "batch takes priority over streaming)",
        before,
        len(combined),
        before - len(combined),
    )
    return combined.drop(columns=["_source_priority", "_event_timestamp"])


def integrate(
    indicators: pd.DataFrame,
    municipalities: pd.DataFrame,
    municipality_targets: pd.DataFrame,
    state_targets: pd.DataFrame,
    national_targets: pd.DataFrame,
    uf_indicator: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Joins the indicator (municipality/year) with the other entities.

    The municipalities table is the canonical source of state_code/name/region.
    `child_literacy_indicator_uf` (optional) adds the official state-level
    literacy rate for the same year — it is not a municipal target.
    """
    df = indicators.merge(municipalities, on="municipality_id", how="left")
    df = df.merge(municipality_targets, on=["municipality_id", "year"], how="left")
    df = df.merge(state_targets, on=["state_code", "year"], how="left")
    df = df.merge(national_targets, on="year", how="left")
    if uf_indicator is not None and not uf_indicator.empty:
        df = df.merge(uf_indicator, on=["state_code", "year"], how="left")
    return df


# --------------------------------------------------------------------------- #
# Basic quality validations (sanity checks before writing to Silver; the
# formal quality report is implemented in quality/validations.py, the next
# stage of the pipeline)
# --------------------------------------------------------------------------- #

def apply_quality_filters(df: pd.DataFrame, valid_states: set[str]) -> pd.DataFrame:
    total = len(df)

    no_municipality = df["municipality_name"].isna()
    if no_municipality.any():
        logger.warning(
            "  %d row(s) dropped: municipality_id not found in the municipalities table "
            "(referential integrity)",
            int(no_municipality.sum()),
        )
    df = df[~no_municipality]

    no_year = df["year"].isna()
    if no_year.any():
        logger.warning("  %d row(s) dropped: null/invalid year", int(no_year.sum()))
    df = df[~no_year]

    no_rate = df["literacy_rate"].isna()
    if no_rate.any():
        logger.warning(
            "  %d row(s) dropped: null literacy_rate (critical field)", int(no_rate.sum())
        )
    df = df[~no_rate]

    out_of_range = ~df["literacy_rate"].between(*RATE_RANGE)
    if out_of_range.any():
        logger.warning(
            "  %d row(s) dropped: literacy_rate out of range %s",
            int(out_of_range.sum()),
            RATE_RANGE,
        )
    df = df[~out_of_range]

    invalid_state = ~df["state_code"].isin(valid_states)
    if invalid_state.any():
        logger.warning(
            "  %d row(s) dropped: state_code outside the valid set of %d states",
            int(invalid_state.sum()),
            len(valid_states),
        )
    df = df[~invalid_state]

    logger.info("Quality filters: %d -> %d row(s) (%d dropped)", total, len(df), total - len(df))
    return df


# --------------------------------------------------------------------------- #
# Local write (--dry-run)
# --------------------------------------------------------------------------- #

def write_local_partitioned(df: pd.DataFrame, output_dir: Path, partition_cols: list[str]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for values, group in df.groupby(partition_cols, dropna=False):
        if not isinstance(values, tuple):
            values = (values,)
        partition_dir = output_dir
        for col, value in zip(partition_cols, values):
            partition_dir = partition_dir / f"{col}={value}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        path = partition_dir / f"{SILVER_TABLE_NAME}-{uuid.uuid4().hex[:12]}.parquet"
        group.drop(columns=partition_cols).to_parquet(path, index=False, engine="pyarrow")
        written.append(path)
    return written


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--bronze-bucket", default=BRONZE_BUCKET, help=f"Bronze S3 bucket (default: {BRONZE_BUCKET})"
    )
    parser.add_argument(
        "--silver-bucket", default=SILVER_BUCKET, help=f"Silver S3 bucket (default: {SILVER_BUCKET})"
    )
    parser.add_argument(
        "--quality-bucket",
        default=QUALITY_BUCKET,
        help=f"S3 bucket for quality reports (default: {QUALITY_BUCKET})",
    )
    parser.add_argument("--batch-prefix", default="batch", help="Bronze batch prefix (default: batch)")
    parser.add_argument(
        "--streaming-prefix", default="streaming", help="Bronze streaming prefix (default: streaming)"
    )
    parser.add_argument(
        "--bronze-dir",
        default="output/bronze",
        help="Local Bronze folder in --dry-run mode (default: output/bronze, "
        "the same default output of ingest_batch.py --dry-run)",
    )
    parser.add_argument(
        "--output-dir",
        default="output/silver",
        help="Local folder to write the result in --dry-run mode (default: output/silver)",
    )
    parser.add_argument(
        "--quality-output-dir",
        default="output/quality-reports",
        help="Local folder to write the quality report in --dry-run mode "
        "(default: output/quality-reports)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Reads Bronze from --bronze-dir (local) and writes Silver to --output-dir. No S3.",
    )
    args = parser.parse_args()

    s3_client = None if args.dry_run else get_s3_client()
    bronze_dir = Path(args.bronze_dir)
    read_kw = dict(
        s3_client=s3_client,
        bronze_dir=bronze_dir,
        dry_run=args.dry_run,
    )
    logger.info(
        "== Silver processing: %s/{%s,%s} -> %s ==",
        str(bronze_dir) if args.dry_run else f"s3://{args.bronze_bucket}",
        args.batch_prefix,
        args.streaming_prefix,
        args.output_dir if args.dry_run else f"s3://{args.silver_bucket}/{SILVER_TABLE_NAME}/",
    )

    logger.info("-- Reading Bronze batch tables --")
    try:
        states_raw = read_bronze_table(
            args.bronze_bucket, args.batch_prefix, "states", **read_kw
        )
        municipalities_raw = read_bronze_table(
            args.bronze_bucket, args.batch_prefix, "municipalities", **read_kw
        )
        national_targets_raw = read_bronze_table(
            args.bronze_bucket, args.batch_prefix, "national_targets", **read_kw
        )
        state_targets_raw = read_bronze_table(
            args.bronze_bucket, args.batch_prefix, "state_targets", **read_kw
        )
        municipality_targets_raw = read_bronze_table(
            args.bronze_bucket, args.batch_prefix, "municipality_targets", **read_kw
        )
        assessment_raw = read_bronze_table(
            args.bronze_bucket, args.batch_prefix, "child_literacy_indicator", **read_kw
        )
        uf_indicator_raw = read_bronze_table(
            args.bronze_bucket,
            args.batch_prefix,
            "child_literacy_indicator_uf",
            required=False,
            **read_kw,
        )
    except Exception:
        logger.exception(
            "Failed to read Bronze batch tables -- make sure ingest_batch.py has already run successfully"
        )
        return 1

    logger.info("-- Reading Bronze streaming events --")
    streaming_raw = read_bronze_streaming(
        args.bronze_bucket, args.streaming_prefix, **read_kw
    )

    logger.info("-- Cleaning and standardizing per entity --")
    states_df = clean_states(states_raw)
    municipalities_df = clean_municipalities(municipalities_raw)
    national_targets_df = clean_national_targets(national_targets_raw)
    state_targets_df = clean_state_targets(state_targets_raw)
    municipality_targets_df = clean_municipality_targets(municipality_targets_raw)
    assessment_batch_df = clean_literacy_assessment(assessment_raw)
    assessment_streaming_df = clean_streaming(streaming_raw)
    uf_indicator_df = clean_literacy_indicator_uf(uf_indicator_raw)

    logger.info("-- Deduplication (batch + streaming) --")
    indicators_df = build_indicators(assessment_batch_df, assessment_streaming_df)

    logger.info("-- Integration of the 6 entities + UF indicator by municipality/year --")
    silver_df = integrate(
        indicators_df,
        municipalities_df,
        municipality_targets_df,
        state_targets_df,
        national_targets_df,
        uf_indicator=uf_indicator_df,
    )
    logger.info("  -> %d row(s), %d column(s) before quality filters", len(silver_df), len(silver_df.columns))

    logger.info("-- Basic quality validations --")
    valid_states = set(states_df["state_code"])
    silver_df = apply_quality_filters(silver_df, valid_states)

    if silver_df.empty:
        logger.error("No rows left after quality filters -- aborting Silver write")
        return 1

    silver_df["year"] = silver_df["year"].astype(int)
    logger.info("Integrated Silver table: %d row(s), %d column(s)", len(silver_df), len(silver_df.columns))

    logger.info("-- Formal quality gate (quality/validations.py) --")
    municipality_ids = set(municipalities_df["municipality_id"])
    quality_report = run_quality_checks(silver_df, municipality_ids, valid_states, table_name=SILVER_TABLE_NAME)
    report_paths = save_report(
        quality_report,
        bucket=args.quality_bucket,
        prefix=SILVER_TABLE_NAME,
        s3_client=s3_client,
        output_dir=args.quality_output_dir,
        dry_run=args.dry_run,
    )

    if not quality_report.passed:
        logger.error(
            "Formal quality validations FAILED -- aborting Silver write (report: %s)",
            report_paths,
        )
        return 1

    if args.dry_run:
        written = write_local_partitioned(silver_df, Path(args.output_dir), PARTITION_COLS)
        logger.info(
            "[dry-run] %d Parquet file(s) written locally to %s/ (partitioned by %s)",
            len(written),
            args.output_dir,
            "/".join(PARTITION_COLS),
        )
    else:
        keys = upload_dataframe_partitioned(
            silver_df,
            args.silver_bucket,
            SILVER_TABLE_NAME,
            PARTITION_COLS,
            filename_prefix=SILVER_TABLE_NAME,
            s3_client=s3_client,
        )
        logger.info(
            "[OK] %d Parquet file(s) written to s3://%s/%s/ (partitioned by %s)",
            len(keys),
            args.silver_bucket,
            SILVER_TABLE_NAME,
            "/".join(PARTITION_COLS),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
