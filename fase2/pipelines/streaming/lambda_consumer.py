"""
Streaming Ingestion -- lambda_consumer.py: Kinesis -> S3 Bronze (streaming)

AWS Lambda handler triggered automatically by the Kinesis -> Lambda event
source mapping (created by `infrastructure/create_stream.sh`). For each batch
of records received from the stream, decodes the JSON events and writes them
all together as a single JSON Lines file to:

  s3://<BRONZE_BUCKET>/streaming/dt=<YYYY-MM-DD>/<request_id>.json

No content transformation -- the Bronze layer preserves the events exactly
as they arrived, following the same philosophy as ingest_batch.py.

This file is packaged and deployed on its own (without `pipelines/common.py`,
see `infrastructure/create_stream.sh`), so it doesn't import anything from
the rest of the project -- it only uses `boto3` (natively available in the
Lambda runtime) and the standard library.

Environment variables (set by create_stream.sh when publishing the function):
  BRONZE_BUCKET             S3 bucket for the Bronze layer (required)
  BRONZE_STREAMING_PREFIX   prefix inside the bucket (default: "streaming")
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def decode_record(raw_record: dict) -> dict | None:
    """Decodes a Kinesis record (base64 -> JSON). Returns None on invalid
    payload, without interrupting the rest of the batch."""
    try:
        payload = base64.b64decode(raw_record["kinesis"]["data"])
        return json.loads(payload)
    except Exception:
        logger.exception("Record discarded: invalid payload (sequence_number=%s)",
                          raw_record.get("kinesis", {}).get("sequenceNumber"))
        return None


def handler(event: dict, context) -> dict:
    bucket = os.environ.get("BRONZE_BUCKET")
    prefix = os.environ.get("BRONZE_STREAMING_PREFIX", "streaming")
    request_id = getattr(context, "aws_request_id", "local-test")

    raw_records = event.get("Records", [])
    logger.info("Received %d record(s) from Kinesis", len(raw_records))

    decoded = [d for d in (decode_record(r) for r in raw_records) if d is not None]
    errors = len(raw_records) - len(decoded)

    if not decoded:
        logger.warning("No valid records in this batch -- nothing written to S3")
        return {"records_received": len(raw_records), "records_written": 0, "errors": errors}

    if not bucket:
        raise RuntimeError("BRONZE_BUCKET environment variable is not set")

    body = "\n".join(json.dumps(record, ensure_ascii=False) for record in decoded)
    dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{prefix}/dt={dt}/{request_id}.json"

    get_s3_client().put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    logger.info("[OK] %d record(s) written to s3://%s/%s (%d error(s))", len(decoded), bucket, key, errors)

    return {"records_received": len(raw_records), "records_written": len(decoded), "errors": errors}
