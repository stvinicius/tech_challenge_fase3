#!/usr/bin/env python3
"""
Batch Ingestion -- raw_downloads/ (CSV from basedosdados.org) -> S3 Bronze (Parquet)

Reads the CSVs manually downloaded from basedosdados.org, applies a minimal
schema standardization (snake_case column names) while preserving the data
exactly as it came from the source -- the Bronze layer holds raw data, with
no content transformation -- and uploads each table as Parquet to
s3://<bronze>/batch/<table>/<table>.parquet

Tables expected in raw_downloads/ (accepts .csv or .csv.gz, both the
"friendly" name and the site's default export name):

  sigla_uf                           <- state (UF) directory
  municipios                         <- municipality directory (IBGE)
  metas_nacionais                    <- national literacy target
  metas_uf                           <- literacy target per state
  metas_municipio                    <- literacy target per municipality
  indicador_crianca_alfabetizada     <- indicator per municipality/year
  indicador_crianca_alfabetizada_uf  <- indicator per state/year (optional, bonus)

Usage:
  python pipelines/batch/ingest_batch.py
  python pipelines/batch/ingest_batch.py --input-dir raw_downloads --dry-run
  python pipelines/batch/ingest_batch.py --bucket my-bronze-bucket --prefix batch
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # enables `import common`
from common import (  # noqa: E402
    BRONZE_BUCKET,
    get_logger,
    get_s3_client,
    standardize_columns,
    upload_dataframe_as_parquet,
)

logger = get_logger("ingest_batch")


@dataclass(frozen=True)
class TableSpec:
    name: str
    patterns: tuple[str, ...]
    required: bool = True


# `patterns` match the actual file names basedosdados.org produces when you
# download a table as CSV (either the "friendly" name or the site's default
# export name) -- these stay in the source language since they reflect real
# file names on disk. `name` is the English identifier used for the Bronze
# output path.
TABLES: tuple[TableSpec, ...] = (
    TableSpec("states", ("sigla_uf.csv*", "br_bd_diretorios_brasil_uf.csv*")),
    TableSpec("municipalities", ("municipios.csv*", "br_bd_diretorios_brasil_municipio.csv*")),
    TableSpec(
        "national_targets",
        ("metas_nacionais.csv*", "br_inep_avaliacao_alfabetizacao_meta_alfabetizacao_brasil.csv*"),
    ),
    TableSpec(
        "state_targets",
        ("metas_uf.csv*", "br_inep_avaliacao_alfabetizacao_meta_alfabetizacao_uf.csv*"),
    ),
    TableSpec(
        "municipality_targets",
        ("metas_municipio.csv*", "br_inep_avaliacao_alfabetizacao_meta_alfabetizacao_municipio.csv*"),
    ),
    TableSpec(
        "child_literacy_indicator",
        ("indicador_crianca_alfabetizada.csv*", "br_inep_avaliacao_alfabetizacao_municipio.csv*"),
    ),
    TableSpec(
        "child_literacy_indicator_uf",
        ("indicador_crianca_alfabetizada_uf.csv*", "br_inep_avaliacao_alfabetizacao_uf.csv*"),
        required=False,
    ),
)


def find_source_file(input_dir: Path, spec: TableSpec) -> Path | None:
    for pattern in spec.patterns:
        matches = sorted(input_dir.glob(pattern))
        if matches:
            if len(matches) > 1:
                logger.warning(
                    "Multiple files match '%s' for table '%s'; using the first one: %s",
                    pattern,
                    spec.name,
                    matches[0].name,
                )
            return matches[0]
    return None


def read_csv_any(path: Path) -> pd.DataFrame:
    """Reads a CSV (gzipped or not, inferred from the extension) as plain
    strings -- Bronze preserves the data exactly as it came in; type casts
    (int, float, date) are handled by process_silver.py."""
    try:
        return pd.read_csv(path, dtype=str, encoding="utf-8", keep_default_na=True)
    except UnicodeDecodeError:
        logger.warning("Failed to read %s as UTF-8, trying latin-1", path.name)
        return pd.read_csv(path, dtype=str, encoding="latin-1", keep_default_na=True)


def process_table(
    spec: TableSpec, path: Path, bucket: str, prefix: str, dry_run: bool, s3_client
) -> None:
    size_kb = path.stat().st_size / 1024
    logger.info("Reading %s (%.1f KB) for table '%s'", path.name, size_kb, spec.name)

    df = read_csv_any(path)
    df = standardize_columns(df)
    logger.info("  -> %d row(s), %d column(s): %s", len(df), len(df.columns), ", ".join(df.columns))

    key = f"{prefix}/{spec.name}/{spec.name}.parquet"
    if dry_run:
        logger.info("  [dry-run] nothing uploaded (destination would be s3://%s/%s)", bucket, key)
        return

    upload_dataframe_as_parquet(df, bucket, key, s3_client=s3_client)
    logger.info("  [OK] written to s3://%s/%s", bucket, key)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input-dir",
        default="raw_downloads",
        help="Folder with the manually downloaded CSVs (default: raw_downloads)",
    )
    parser.add_argument(
        "--bucket", default=BRONZE_BUCKET, help=f"Bronze S3 bucket (default: {BRONZE_BUCKET})"
    )
    parser.add_argument(
        "--prefix", default="batch", help="Prefix inside the Bronze bucket (default: batch)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Reads and validates the CSVs without uploading anything to S3 (useful for local testing)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        logger.error("Input folder not found: %s", input_dir)
        return 1

    if args.dry_run:
        logger.info("--dry-run mode: no data will be uploaded to S3")
    s3_client = None if args.dry_run else get_s3_client()

    problems: list[str] = []
    processed = 0
    for spec in TABLES:
        path = find_source_file(input_dir, spec)
        if path is None:
            if spec.required:
                problems.append(spec.name)
                logger.error(
                    "File not found for required table '%s' (accepted patterns: %s)",
                    spec.name,
                    ", ".join(spec.patterns),
                )
            else:
                logger.warning("Optional file not found for '%s' -- skipping", spec.name)
            continue

        try:
            process_table(spec, path, args.bucket, args.prefix, args.dry_run, s3_client)
            processed += 1
        except Exception:
            problems.append(spec.name)
            logger.exception("Failed to process table '%s' (%s)", spec.name, path.name)

    logger.info("Done: %d/%d table(s) processed successfully", processed, len(TABLES))

    if problems:
        logger.error("Tables with problems or missing: %s", ", ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
