#!/usr/bin/env bash
# Creates the on-demand Kinesis stream and wires up the consumer Lambda:
#   1. Creates the Kinesis Data Stream (1 shard)
#   2. Creates the Lambda execution IAM role (if it doesn't exist)
#   3. Packages and publishes pipelines/streaming/lambda_consumer.py as a Lambda function
#   4. Creates the Kinesis -> Lambda event source mapping
#
# Idempotent: can be run again to update the Lambda code without duplicating
# the stream or the role.
#
# Usage: ./infrastructure/create_stream.sh
# After running the demo (producer.py), destroy the stream with
# destroy_stream.sh so you stop paying for the shard.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./config.sh
source "${SCRIPT_DIR}/config.sh"

REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAMBDA_SRC="${REPO_ROOT}/pipelines/streaming/lambda_consumer.py"
BUILD_DIR="${SCRIPT_DIR}/.lambda_build"
LAMBDA_ZIP="${BUILD_DIR}/lambda_consumer.zip"

echo "== Creating on-demand Kinesis stream: ${KINESIS_STREAM_NAME} =="
echo

command -v aws >/dev/null 2>&1 || { echo "ERROR: AWS CLI not found." >&2; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "ERROR: 'zip' command not found." >&2; exit 1; }
[[ -f "${LAMBDA_SRC}" ]] || {
  echo "ERROR: ${LAMBDA_SRC} not found." >&2
  echo "Implement pipelines/streaming/lambda_consumer.py (the 'streaming' stage of the plan) before running this script." >&2
  exit 1
}

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

echo "-- 1/4: Kinesis Data Stream --"
if aws kinesis describe-stream-summary --stream-name "${KINESIS_STREAM_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "  [OK] stream already exists: ${KINESIS_STREAM_NAME}"
else
  echo "  Creating stream (${KINESIS_SHARD_COUNT} shard)..."
  aws kinesis create-stream --stream-name "${KINESIS_STREAM_NAME}" \
    --shard-count "${KINESIS_SHARD_COUNT}" --region "${AWS_REGION}"
  echo "  Waiting for the stream to become ACTIVE..."
  aws kinesis wait stream-exists --stream-name "${KINESIS_STREAM_NAME}" --region "${AWS_REGION}"
  echo "  [OK] stream active: ${KINESIS_STREAM_NAME}"
fi
STREAM_ARN="$(aws kinesis describe-stream-summary --stream-name "${KINESIS_STREAM_NAME}" \
  --region "${AWS_REGION}" --query 'StreamDescriptionSummary.StreamARN' --output text)"
echo

echo "-- 2/4: Lambda execution IAM role --"
TRUST_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
if aws iam get-role --role-name "${LAMBDA_ROLE_NAME}" >/dev/null 2>&1; then
  echo "  [OK] role already exists: ${LAMBDA_ROLE_NAME}"
else
  aws iam create-role --role-name "${LAMBDA_ROLE_NAME}" \
    --assume-role-policy-document "${TRUST_POLICY}" >/dev/null
  aws iam attach-role-policy --role-name "${LAMBDA_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaKinesisExecutionRole
  echo "  [OK] role created: ${LAMBDA_ROLE_NAME}"
fi

S3_POLICY_DOC="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::${BRONZE_BUCKET}/streaming/*\"}]}"
aws iam put-role-policy --role-name "${LAMBDA_ROLE_NAME}" \
  --policy-name "${LAMBDA_S3_POLICY_NAME}" --policy-document "${S3_POLICY_DOC}" >/dev/null
echo "  [OK] s3:PutObject permission on s3://${BRONZE_BUCKET}/streaming/* granted"

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
echo

echo "-- 3/4: Lambda function (${LAMBDA_FUNCTION_NAME}) --"
mkdir -p "${BUILD_DIR}"
rm -f "${LAMBDA_ZIP}"
(cd "$(dirname "${LAMBDA_SRC}")" && zip -q "${LAMBDA_ZIP}" "$(basename "${LAMBDA_SRC}")")

if aws lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "  Updating the existing function's code..."
  aws lambda update-function-code --function-name "${LAMBDA_FUNCTION_NAME}" \
    --zip-file "fileb://${LAMBDA_ZIP}" --region "${AWS_REGION}" >/dev/null
  aws lambda wait function-updated --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}"
  aws lambda update-function-configuration --function-name "${LAMBDA_FUNCTION_NAME}" \
    --region "${AWS_REGION}" --environment "Variables={BRONZE_BUCKET=${BRONZE_BUCKET}}" >/dev/null
  aws lambda wait function-updated --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}"
  echo "  [OK] code updated: ${LAMBDA_FUNCTION_NAME}"
else
  echo "  Creating function..."
  # A brand-new IAM role can take a few seconds to propagate; retry on failure.
  for attempt in 1 2 3 4 5; do
    if aws lambda create-function --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}" \
      --runtime python3.12 --role "${ROLE_ARN}" --handler lambda_consumer.handler \
      --zip-file "fileb://${LAMBDA_ZIP}" --timeout 30 --memory-size 128 \
      --environment "Variables={BRONZE_BUCKET=${BRONZE_BUCKET}}" >/dev/null 2>&1; then
      break
    fi
    echo "  role still propagating, retrying in 5s (attempt ${attempt}/5)..."
    sleep 5
  done
  aws lambda wait function-active --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}"
  echo "  [OK] function created: ${LAMBDA_FUNCTION_NAME}"
fi
echo

echo "-- 4/4: Event source mapping (Kinesis -> Lambda) --"
EXISTING_UUID="$(aws lambda list-event-source-mappings --function-name "${LAMBDA_FUNCTION_NAME}" \
  --event-source-arn "${STREAM_ARN}" --region "${AWS_REGION}" \
  --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || true)"
if [[ -n "${EXISTING_UUID}" && "${EXISTING_UUID}" != "None" ]]; then
  echo "  [OK] mapping already exists: ${EXISTING_UUID}"
else
  aws lambda create-event-source-mapping --function-name "${LAMBDA_FUNCTION_NAME}" \
    --event-source-arn "${STREAM_ARN}" --starting-position LATEST --batch-size 100 \
    --region "${AWS_REGION}" >/dev/null
  echo "  [OK] mapping created between ${KINESIS_STREAM_NAME} and ${LAMBDA_FUNCTION_NAME}"
fi
echo

cat <<EOF
== Demo stream ready ==

Kinesis stream:  ${KINESIS_STREAM_NAME}
Lambda:          ${LAMBDA_FUNCTION_NAME}
Destination:     s3://${BRONZE_BUCKET}/streaming/

Next steps:
  1. python pipelines/streaming/producer.py   (publishes synthetic events to the stream)
  2. Check the objects in s3://${BRONZE_BUCKET}/streaming/
  3. ./infrastructure/destroy_stream.sh        (removes the stream so you stop paying per shard-hour)
EOF
