"""Shared utilities for the pipeline scripts (ingest, silver, gold).

Bucket/region names are read from the same environment variables that
`infrastructure/config.sh` uses (PROJECT_NAME, AWS_REGION, etc.), with the
same defaults -- so the Python scripts and the infrastructure scripts never
drift out of sync.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import unicodedata
import uuid
from io import BytesIO
from pathlib import Path

import pandas as pd

PROJECT_NAME = os.environ.get("PROJECT_NAME", "brazil-literacy-pipeline")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

BRONZE_BUCKET = os.environ.get("BRONZE_BUCKET", f"{PROJECT_NAME}-bronze")
SILVER_BUCKET = os.environ.get("SILVER_BUCKET", f"{PROJECT_NAME}-silver")
GOLD_BUCKET = os.environ.get("GOLD_BUCKET", f"{PROJECT_NAME}-gold")
QUALITY_BUCKET = os.environ.get("QUALITY_BUCKET", f"{PROJECT_NAME}-quality-reports")

KINESIS_STREAM_NAME = os.environ.get("KINESIS_STREAM_NAME", f"{PROJECT_NAME}-stream")


def get_logger(name: str) -> logging.Logger:
    """Simple stdout logger -- CloudWatch captures it automatically when the
    script runs on Lambda/EC2; locally, it prints to the terminal."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def to_snake_case(column: str) -> str:
    """Normalizes a column name to snake_case, stripping accents/symbols."""
    text = unicodedata.normalize("NFKD", str(column)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return text or "column"


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renames a DataFrame's columns to snake_case, preserving the data
    exactly as it came in (schema standardization, not content transformation)."""
    return df.rename(columns={col: to_snake_case(col) for col in df.columns})


def get_s3_client():
    import boto3

    return boto3.client("s3", region_name=AWS_REGION)


def write_parquet_local(df: pd.DataFrame, path: Path) -> None:
    """Writes a DataFrame as a single Parquet file on disk (offline Bronze)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")


def read_parquet_local(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")


def read_partitioned_parquet_local(base_dir: Path) -> pd.DataFrame:
    """Reads Hive-style Parquet on disk, reconstructing partition columns.

    Concatenates file-by-file (pandas) so partitions with all-null float
    columns (Arrow type ``null``) still combine with partitions that have
    real doubles — ``pd.read_parquet(directory)`` as a dataset fails.
    """
    base_dir = Path(base_dir)
    files = sorted(base_dir.rglob("*.parquet"))
    if not files:
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for path in files:
        df = pd.read_parquet(path, engine="pyarrow")
        for part in path.relative_to(base_dir).parts[:-1]:
            if "=" in part:
                col, value = part.split("=", 1)
                df[col] = value
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def read_ndjson_local(path: Path) -> list[dict]:
    import json

    body = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def get_kinesis_client():
    import boto3

    return boto3.client("kinesis", region_name=AWS_REGION)


def upload_dataframe_as_parquet(df: pd.DataFrame, bucket: str, key: str, s3_client=None) -> None:
    """Serializes a DataFrame as Parquet in memory and uploads it directly to S3."""
    s3_client = s3_client or get_s3_client()
    buffer = BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)
    s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())


def read_parquet_from_s3(bucket: str, key: str, s3_client=None) -> pd.DataFrame:
    """Reads a single Parquet object from S3 and returns it as a DataFrame."""
    s3_client = s3_client or get_s3_client()
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()), engine="pyarrow")


def list_s3_keys(bucket: str, prefix: str, s3_client=None) -> list[str]:
    """Lists (with pagination) the keys under a bucket/prefix, ignoring
    empty "folder" keys (keys ending in '/', created by setup_aws.sh)."""
    s3_client = s3_client or get_s3_client()
    paginator = s3_client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith("/"):
                keys.append(obj["Key"])
    return keys


def read_ndjson_from_s3(bucket: str, key: str, s3_client=None) -> list[dict]:
    """Reads a JSON Lines file (one JSON object per line) from S3, the format
    written by `lambda_consumer.py` / `producer.py --dry-run`."""
    import json

    s3_client = s3_client or get_s3_client()
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def read_partitioned_parquet_from_s3(bucket: str, prefix: str, s3_client=None) -> pd.DataFrame:
    """Reads a Hive-style partitioned Parquet dataset
    (``s3://bucket/prefix/col1=value1/col2=value2/*.parquet``) and returns it
    as a single DataFrame, reconstructing the partition columns from each
    file's path -- the inverse of `upload_dataframe_partitioned`."""
    s3_client = s3_client or get_s3_client()
    keys = list_s3_keys(bucket, f"{prefix}/", s3_client=s3_client)
    frames: list[pd.DataFrame] = []
    for key in keys:
        relative = key[len(prefix) + 1:]
        partition_values = dict(part.split("=", 1) for part in relative.split("/")[:-1] if "=" in part)
        df = read_parquet_from_s3(bucket, key, s3_client=s3_client)
        for col, value in partition_values.items():
            df[col] = value
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def upload_dataframe_partitioned(
    df: pd.DataFrame,
    bucket: str,
    base_prefix: str,
    partition_cols: list[str],
    filename_prefix: str = "part",
    s3_client=None,
) -> list[str]:
    """Writes a DataFrame to S3 as Hive-style partitioned Parquet
    (``base_prefix/col1=value1/col2=value2/part-<uuid>.parquet``), the same
    layout that the Glue Catalog / Athena expect for "partition projection".

    The partition columns are dropped from the data files (they only remain
    encoded in the path), avoiding redundancy.
    """
    s3_client = s3_client or get_s3_client()
    written_keys: list[str] = []
    for values, group in df.groupby(partition_cols, dropna=False):
        if not isinstance(values, tuple):
            values = (values,)
        partition_path = "/".join(
            f"{col}={value}" for col, value in zip(partition_cols, values)
        )
        key = f"{base_prefix}/{partition_path}/{filename_prefix}-{uuid.uuid4().hex[:12]}.parquet"
        upload_dataframe_as_parquet(group.drop(columns=partition_cols), bucket, key, s3_client=s3_client)
        written_keys.append(key)
    return written_keys
