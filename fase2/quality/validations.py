#!/usr/bin/env python3
"""
Data Quality -- custom Pandas validations (no Great Expectations)

Acts as the quality gate between `process_silver.py` (cleaning + integration
of the 6 entities) and writing the integrated table to S3 Silver: it runs 5
business checks on the already-clean table and produces a formal report
(JSON + HTML), reaffirming with auditable evidence the same guarantees the
row-by-row filters in `apply_quality_filters` already applied:

  1. No nulls in critical columns (municipality_id, year, literacy_rate)
  2. Composite key (municipality_id, year) is unique (no duplicates)
  3. literacy_rate between 0 and 100
  4. state_code belongs to the valid set of 27 states
  5. municipality_id exists in the municipalities table (referential integrity)

If any check fails, `QualityReport.passed` will be `False`; the caller
(typically `process_silver.py`) must then **not write to Silver**, log the
error via `logger.error` (captured by CloudWatch when running on AWS) and
still publish the report to `s3://<quality-reports>/` for auditing -- even a
failed run leaves a trace of why.

It also works as a standalone script, useful for validating an already
written Parquet file (e.g., the Silver output of a
`process_silver.py --dry-run`) without running the whole pipeline:

  python quality/validations.py \
      --input-parquet output/silver \
      --municipalities-parquet output/municipalities.parquet \
      --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))  # enables `import common`
from common import QUALITY_BUCKET, get_logger, get_s3_client  # noqa: E402

logger = get_logger("validations")

VALID_STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

DEFAULT_CRITICAL_COLUMNS = ("municipality_id", "year", "literacy_rate")
DEFAULT_KEY_COLUMNS = ("municipality_id", "year")
DEFAULT_VALUE_COLUMN = "literacy_rate"
DEFAULT_VALUE_RANGE = (0.0, 100.0)
DEFAULT_STATE_COLUMN = "state_code"
DEFAULT_REF_COLUMN = "municipality_id"

MAX_SAMPLE_ROWS = 10


# --------------------------------------------------------------------------- #
# Report structures
# --------------------------------------------------------------------------- #

@dataclass
class CheckResult:
    name: str
    description: str
    passed: bool
    total_rows: int
    failed_rows: int
    sample: list[dict] = field(default_factory=list)
    details: str = ""


@dataclass
class QualityReport:
    table: str
    generated_at: str
    total_rows: int
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["passed"] = self.passed
        return data


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #

def _sample(df: pd.DataFrame, mask: pd.Series, columns: list[str]) -> list[dict]:
    if not mask.any():
        return []
    cols = [c for c in columns if c in df.columns]
    return df.loc[mask, cols].head(MAX_SAMPLE_ROWS).astype(str).to_dict("records")


def check_not_null(df: pd.DataFrame, columns: tuple[str, ...]) -> CheckResult:
    """No row may have a null value in any of the critical columns."""
    cols = [c for c in columns if c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    mask = df[cols].isna().any(axis=1) if cols else pd.Series(False, index=df.index)
    per_column = {c: int(df[c].isna().sum()) for c in cols}
    details = f"Nulls per column: {per_column}"
    if missing:
        details += f" | missing column(s) in the table: {missing}"
    return CheckResult(
        name="not_null",
        description=f"No nulls in the critical columns ({', '.join(columns)})",
        passed=not mask.any() and not missing,
        total_rows=len(df),
        failed_rows=int(mask.sum()),
        sample=_sample(df, mask, cols),
        details=details,
    )


def check_unique_key(df: pd.DataFrame, key_columns: tuple[str, ...]) -> CheckResult:
    """The composite key (e.g., municipality_id + year) must have no duplicates."""
    cols = [c for c in key_columns if c in df.columns]
    if len(cols) != len(key_columns):
        return CheckResult(
            name="unique_key",
            description=f"Composite key ({', '.join(key_columns)}) is unique",
            passed=False,
            total_rows=len(df),
            failed_rows=len(df),
            details=f"missing key column(s) in the table: {[c for c in key_columns if c not in df.columns]}",
        )
    duplicated_all = df.duplicated(subset=cols, keep=False)
    duplicated_extra = df.duplicated(subset=cols, keep="first")
    return CheckResult(
        name="unique_key",
        description=f"Composite key ({', '.join(key_columns)}) is unique",
        passed=not duplicated_all.any(),
        total_rows=len(df),
        failed_rows=int(duplicated_all.sum()),
        sample=_sample(df, duplicated_all, cols),
        details=f"{int(duplicated_extra.sum())} duplicate row(s) beyond the first occurrence",
    )


def check_value_range(df: pd.DataFrame, column: str, low: float, high: float) -> CheckResult:
    """Numeric column must be within [low, high] (nulls are ignored here --
    already covered by `check_not_null`)."""
    if column not in df.columns:
        return CheckResult(
            name="value_range",
            description=f"{column} between {low} and {high}",
            passed=False,
            total_rows=len(df),
            failed_rows=len(df),
            details=f"column '{column}' missing from the table",
        )
    values = pd.to_numeric(df[column], errors="coerce")
    out_of_range = values.notna() & ~values.between(low, high)
    key_cols = [c for c in DEFAULT_KEY_COLUMNS if c in df.columns]
    return CheckResult(
        name="value_range",
        description=f"{column} between {low} and {high}",
        passed=not out_of_range.any(),
        total_rows=len(df),
        failed_rows=int(out_of_range.sum()),
        sample=_sample(df, out_of_range, [*key_cols, column]),
        details=f"min={values.min()}, max={values.max()}",
    )


def check_valid_categories(df: pd.DataFrame, column: str, valid_values: set[str]) -> CheckResult:
    """Column values must belong to a closed set (e.g., the 27 states)."""
    if column not in df.columns:
        return CheckResult(
            name="valid_categories",
            description=f"{column} belongs to the valid set of {len(valid_values)} value(s)",
            passed=False,
            total_rows=len(df),
            failed_rows=len(df),
            details=f"column '{column}' missing from the table",
        )
    invalid = ~df[column].isin(valid_values)
    found = sorted(set(df.loc[invalid, column].dropna().astype(str).unique()))
    return CheckResult(
        name="valid_categories",
        description=f"{column} belongs to the valid set of {len(valid_values)} value(s)",
        passed=not invalid.any(),
        total_rows=len(df),
        failed_rows=int(invalid.sum()),
        sample=_sample(df, invalid, [column]),
        details=f"Invalid value(s) found: {found[:MAX_SAMPLE_ROWS]}",
    )


def check_referential_integrity(
    df: pd.DataFrame, column: str, valid_ids: set[str], ref_name: str
) -> CheckResult:
    """Every foreign key (e.g., municipality_id) must exist in the reference
    table (e.g., municipalities)."""
    if column not in df.columns:
        return CheckResult(
            name="referential_integrity",
            description=f"{column} exists in the {ref_name} table",
            passed=False,
            total_rows=len(df),
            failed_rows=len(df),
            details=f"column '{column}' missing from the table",
        )
    if not valid_ids:
        logger.warning(
            "check_referential_integrity: the set of valid IDs for '%s' is empty -- check skipped", ref_name
        )
        return CheckResult(
            name="referential_integrity",
            description=f"{column} exists in the {ref_name} table",
            passed=True,
            total_rows=len(df),
            failed_rows=0,
            details=f"check skipped: no reference ID for '{ref_name}' was provided",
        )
    invalid = ~df[column].astype(str).isin(valid_ids)
    return CheckResult(
        name="referential_integrity",
        description=f"{column} exists in the {ref_name} table",
        passed=not invalid.any(),
        total_rows=len(df),
        failed_rows=int(invalid.sum()),
        sample=_sample(df, invalid, [column]),
        details=f"{int(invalid.sum())} value(s) of '{column}' with no match in '{ref_name}'",
    )


# --------------------------------------------------------------------------- #
# Orchestration + report
# --------------------------------------------------------------------------- #

def run_quality_checks(
    df: pd.DataFrame,
    municipality_ids: set[str],
    valid_states: set[str] = VALID_STATES,
    *,
    table_name: str = "literacy_indicator",
    critical_columns: tuple[str, ...] = DEFAULT_CRITICAL_COLUMNS,
    key_columns: tuple[str, ...] = DEFAULT_KEY_COLUMNS,
    value_column: str = DEFAULT_VALUE_COLUMN,
    value_range: tuple[float, float] = DEFAULT_VALUE_RANGE,
    state_column: str = DEFAULT_STATE_COLUMN,
    ref_column: str = DEFAULT_REF_COLUMN,
) -> QualityReport:
    """Runs the 5 business checks on `df` and returns the consolidated
    report. Doesn't write anything to disk/S3 -- see `save_report`."""
    logger.info("Running quality validations on %d row(s) of '%s'...", len(df), table_name)

    checks = [
        check_not_null(df, critical_columns),
        check_unique_key(df, key_columns),
        check_value_range(df, value_column, *value_range),
        check_valid_categories(df, state_column, valid_states),
        check_referential_integrity(df, ref_column, municipality_ids, "municipalities"),
    ]

    for check in checks:
        log = logger.info if check.passed else logger.error
        log(
            "  [%s] %s -> %d/%d row(s) with issues",
            "OK" if check.passed else "FAILED",
            check.description,
            check.failed_rows,
            check.total_rows,
        )

    report = QualityReport(
        table=table_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_rows=len(df),
        checks=checks,
    )
    logger.info("Overall quality validation result: %s", "PASSED" if report.passed else "FAILED")
    return report


def render_html_report(report: QualityReport) -> str:
    rows = "\n".join(
        "<tr class=\"{cls}\">"
        "<td>{name}</td><td>{description}</td><td>{status}</td>"
        "<td>{failed}/{total}</td><td>{details}</td></tr>".format(
            cls="ok" if c.passed else "fail",
            name=c.name,
            description=c.description,
            status="OK" if c.passed else "FAILED",
            failed=c.failed_rows,
            total=c.total_rows,
            details=c.details,
        )
        for c in report.checks
    )
    status = "PASSED" if report.passed else "FAILED"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Quality Report -- {report.table}</title>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; margin: 2rem; color: #222; }}
h1 {{ font-size: 1.4rem; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; font-size: 0.9rem; vertical-align: top; }}
th {{ background: #f4f4f4; }}
tr.ok {{ background: #e9f7ef; }}
tr.fail {{ background: #fdecea; }}
.status {{ font-weight: bold; }}
.status.ok {{ color: #1e7e34; }}
.status.fail {{ color: #a71d2a; }}
</style>
</head>
<body>
<h1>Quality Report -- {report.table}</h1>
<p>Generated at: {report.generated_at}</p>
<p>Total rows evaluated: {report.total_rows}</p>
<p>Overall result: <span class="status {'ok' if report.passed else 'fail'}">{status}</span></p>
<table>
<thead><tr><th>Check</th><th>Description</th><th>Status</th><th>Rows with issues</th><th>Details</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""


def save_report(
    report: QualityReport,
    bucket: str = QUALITY_BUCKET,
    prefix: str = "silver",
    s3_client=None,
    output_dir: str | Path = "output/quality-reports",
    dry_run: bool = False,
) -> dict[str, str]:
    """Serializes the report as JSON + HTML and writes it to
    `s3://<bucket>/<prefix>/` (or locally to `output_dir` in `dry_run`
    mode). Returns the paths/URIs of the two files written."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    status = "PASSED" if report.passed else "FAILED"
    base_name = f"{report.table}-{timestamp}-{status}"
    json_body = json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str)
    html_body = render_html_report(report)

    if dry_run:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{base_name}.json"
        html_path = output_dir / f"{base_name}.html"
        json_path.write_text(json_body, encoding="utf-8")
        html_path.write_text(html_body, encoding="utf-8")
        logger.info("[dry-run] Quality report written locally to %s and %s", json_path, html_path)
        return {"json": str(json_path), "html": str(html_path)}

    s3_client = s3_client or get_s3_client()
    json_key = f"{prefix}/{base_name}.json"
    html_key = f"{prefix}/{base_name}.html"
    s3_client.put_object(Bucket=bucket, Key=json_key, Body=json_body.encode("utf-8"), ContentType="application/json")
    s3_client.put_object(Bucket=bucket, Key=html_key, Body=html_body.encode("utf-8"), ContentType="text/html")
    logger.info(
        "Quality report written to s3://%s/%s and s3://%s/%s", bucket, json_key, bucket, html_key
    )
    return {"json": f"s3://{bucket}/{json_key}", "html": f"s3://{bucket}/{html_key}"}


# --------------------------------------------------------------------------- #
# Standalone CLI
# --------------------------------------------------------------------------- #

def _read_parquet_path(path: Path) -> pd.DataFrame:
    """Reads a single Parquet file or a Hive-style partitioned folder
    (`col=value/...`), automatically recognizing the partition columns."""
    return pd.read_parquet(path, engine="pyarrow")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input-parquet", required=True, help="Parquet file or (partitioned) folder with the table to validate"
    )
    parser.add_argument(
        "--municipalities-parquet",
        help="Parquet for the municipalities table (referential integrity check); "
        "if omitted, that check is skipped",
    )
    parser.add_argument("--table-name", default="literacy_indicator", help="Table name shown in the report")
    parser.add_argument("--bucket", default=QUALITY_BUCKET, help=f"S3 bucket for reports (default: {QUALITY_BUCKET})")
    parser.add_argument("--prefix", default="silver", help="Prefix inside the reports bucket (default: silver)")
    parser.add_argument(
        "--output-dir",
        default="output/quality-reports",
        help="Local folder to write the report in --dry-run mode (default: output/quality-reports)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Writes the report locally to --output-dir instead of uploading it to S3",
    )
    args = parser.parse_args()

    df = _read_parquet_path(Path(args.input_parquet))
    logger.info("Table loaded from %s: %d row(s), %d column(s)", args.input_parquet, len(df), len(df.columns))

    if args.municipalities_parquet:
        municipalities_df = _read_parquet_path(Path(args.municipalities_parquet))
        municipality_ids = set(municipalities_df["municipality_id"].astype(str))
    else:
        logger.warning(
            "--municipalities-parquet not provided: the referential integrity check will be skipped"
        )
        municipality_ids = set()

    report = run_quality_checks(df, municipality_ids, VALID_STATES, table_name=args.table_name)
    save_report(
        report,
        bucket=args.bucket,
        prefix=args.prefix,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )

    if not report.passed:
        logger.error("Quality validations FAILED -- the data must not be written to Silver")
        return 1

    logger.info("Quality validations OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
