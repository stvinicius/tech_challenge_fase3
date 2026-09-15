#!/usr/bin/env bash
# Creates the project's base (permanent) infrastructure on AWS:
#   - S3 buckets for the Bronze / Silver / Gold layers + quality reports
#   - Database in the AWS Glue Data Catalog (metastore for the Gold tables)
#   - Amazon Athena workgroup (with a dedicated results location)
#
# Idempotent: can be run multiple times without duplicating resources.
# Does not include Kinesis/Lambda -- those resources are created on demand,
# see create_stream.sh and destroy_stream.sh.
#
# Usage: ./infrastructure/setup_aws.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./config.sh
source "${SCRIPT_DIR}/config.sh"

echo "== Brazil Literacy Pipeline -- AWS Infrastructure Setup =="
echo "Project: ${PROJECT_NAME} | Region: ${AWS_REGION}"
echo

command -v aws >/dev/null 2>&1 || {
  echo "ERROR: AWS CLI not found. Install it (https://aws.amazon.com/cli/) and run 'aws configure' before continuing." >&2
  exit 1
}

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "Authenticated in AWS account: ${ACCOUNT_ID}"
echo

create_bucket() {
  local bucket="$1"

  if aws s3api head-bucket --bucket "${bucket}" 2>/dev/null; then
    echo "  [OK] bucket already exists: ${bucket}"
    return
  fi

  echo "  Creating bucket: ${bucket}"
  if [[ "${AWS_REGION}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${bucket}" --region "${AWS_REGION}" >/dev/null
  else
    aws s3api create-bucket --bucket "${bucket}" --region "${AWS_REGION}" \
      --create-bucket-configuration LocationConstraint="${AWS_REGION}" >/dev/null
  fi

  aws s3api put-public-access-block --bucket "${bucket}" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

  aws s3api put-bucket-encryption --bucket "${bucket}" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

  echo "  [OK] bucket created (public access blocked, default SSE-S3 encryption): ${bucket}"
}

echo "-- 1/4: S3 buckets (Bronze / Silver / Gold / Quality / Athena results) --"
create_bucket "${BRONZE_BUCKET}"
create_bucket "${SILVER_BUCKET}"
create_bucket "${GOLD_BUCKET}"
create_bucket "${QUALITY_BUCKET}"
create_bucket "${ATHENA_RESULTS_BUCKET}"
echo

echo "-- 2/4: Prefixes (folders) inside Bronze --"
aws s3api put-object --bucket "${BRONZE_BUCKET}" --key "batch/" >/dev/null
aws s3api put-object --bucket "${BRONZE_BUCKET}" --key "streaming/" >/dev/null
echo "  [OK] s3://${BRONZE_BUCKET}/batch/ and s3://${BRONZE_BUCKET}/streaming/"
echo

echo "-- 3/4: AWS Glue Data Catalog --"
if aws glue get-database --name "${GLUE_DATABASE}" >/dev/null 2>&1; then
  echo "  [OK] Glue database already exists: ${GLUE_DATABASE}"
else
  aws glue create-database --database-input "{\"Name\":\"${GLUE_DATABASE}\",\"Description\":\"Gold layer for the Child Literacy Indicator\"}" >/dev/null
  echo "  [OK] Glue database created: ${GLUE_DATABASE}"
fi
echo

echo "-- 4/4: Amazon Athena (workgroup + results location) --"
if aws athena get-work-group --work-group "${ATHENA_WORKGROUP}" >/dev/null 2>&1; then
  echo "  [OK] Athena workgroup already exists: ${ATHENA_WORKGROUP}"
else
  aws athena create-work-group --name "${ATHENA_WORKGROUP}" \
    --configuration "ResultConfiguration={OutputLocation=s3://${ATHENA_RESULTS_BUCKET}/}" \
    --description "Brazil Literacy Pipeline workgroup - queries over the Gold layer" >/dev/null
  echo "  [OK] Athena workgroup created: ${ATHENA_WORKGROUP} (results in s3://${ATHENA_RESULTS_BUCKET}/)"
fi
echo

cat <<EOF
== Base infrastructure created successfully ==

S3 buckets:
  Bronze          -> s3://${BRONZE_BUCKET}
  Silver          -> s3://${SILVER_BUCKET}
  Gold            -> s3://${GOLD_BUCKET}
  Quality reports -> s3://${QUALITY_BUCKET}
  Athena results  -> s3://${ATHENA_RESULTS_BUCKET}

Glue database:     ${GLUE_DATABASE}
Athena workgroup:  ${ATHENA_WORKGROUP}

Next steps:
  1. Download the CSVs from basedosdados.org into raw_downloads/ (see README)
  2. Run pipelines/orchestrator.py (or each stage in isolation) to populate Bronze -> Silver -> Gold
  3. infrastructure/create_stream.sh creates Kinesis + Lambda on demand (a later step)
  4. Run infrastructure/athena_ddl.sql (aws athena start-query-execution or the Athena console)
     to register the 3 Gold tables in this database and query them via Athena
EOF
