#!/usr/bin/env bash
# Destroys the on-demand streaming resources created by create_stream.sh:
#   1. Removes the event source mapping (Kinesis -> Lambda)
#   2. Removes the Lambda function
#   3. Removes the Kinesis stream
#
# The IAM role (${LAMBDA_ROLE_NAME}) is kept -- it has no cost and is reused
# the next time create_stream.sh runs. Instructions to remove it too are
# shown at the end, in case you want a full cleanup.
#
# Usage: ./infrastructure/destroy_stream.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./config.sh
source "${SCRIPT_DIR}/config.sh"

echo "== Destroying on-demand streaming resources =="
echo

command -v aws >/dev/null 2>&1 || { echo "ERROR: AWS CLI not found." >&2; exit 1; }

echo "-- 1/3: Event source mappings --"
MAPPING_UUIDS="$(aws lambda list-event-source-mappings --function-name "${LAMBDA_FUNCTION_NAME}" \
  --region "${AWS_REGION}" --query 'EventSourceMappings[].UUID' --output text 2>/dev/null || true)"
if [[ -n "${MAPPING_UUIDS}" ]]; then
  for uuid in ${MAPPING_UUIDS}; do
    echo "  Removing mapping ${uuid}..."
    aws lambda delete-event-source-mapping --uuid "${uuid}" --region "${AWS_REGION}" >/dev/null || true
  done
else
  echo "  [OK] no mapping found"
fi
echo

echo "-- 2/3: Lambda function (${LAMBDA_FUNCTION_NAME}) --"
if aws lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  aws lambda delete-function --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}"
  echo "  [OK] function removed"
else
  echo "  [OK] function no longer exists"
fi
echo

echo "-- 3/3: Kinesis stream (${KINESIS_STREAM_NAME}) --"
if aws kinesis describe-stream-summary --stream-name "${KINESIS_STREAM_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  aws kinesis delete-stream --stream-name "${KINESIS_STREAM_NAME}" --region "${AWS_REGION}" --enforce-consumer-deletion
  echo "  Waiting for full removal..."
  aws kinesis wait stream-not-exists --stream-name "${KINESIS_STREAM_NAME}" --region "${AWS_REGION}"
  echo "  [OK] stream removed"
else
  echo "  [OK] stream no longer exists"
fi
echo

cat <<EOF
== Streaming resources destroyed ==

The IAM role '${LAMBDA_ROLE_NAME}' was kept (no cost) for reuse the next time
create_stream.sh runs. To remove it too (full cleanup):

  aws iam delete-role-policy --role-name ${LAMBDA_ROLE_NAME} --policy-name ${LAMBDA_S3_POLICY_NAME}
  aws iam detach-role-policy --role-name ${LAMBDA_ROLE_NAME} --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaKinesisExecutionRole
  aws iam delete-role --role-name ${LAMBDA_ROLE_NAME}
EOF
