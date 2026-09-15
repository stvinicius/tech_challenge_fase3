#!/usr/bin/env bash
# Shared configuration for all infrastructure scripts.
# Every value can be overridden via environment variables before running
# the scripts, e.g.: PROJECT_NAME=my-project-abc123 ./setup_aws.sh
#
# This file is meant to be sourced, not executed directly.

export AWS_REGION="${AWS_REGION:-us-east-1}"

# S3 bucket names are globally unique in AWS. If "brazil-literacy-pipeline"
# is already taken by another account, set PROJECT_NAME with your own
# suffix (e.g. brazil-literacy-pipeline-vsc2026) and re-run the scripts.
export PROJECT_NAME="${PROJECT_NAME:-brazil-literacy-pipeline}"

# S3 -- Medallion Architecture
export BRONZE_BUCKET="${PROJECT_NAME}-bronze"
export SILVER_BUCKET="${PROJECT_NAME}-silver"
export GOLD_BUCKET="${PROJECT_NAME}-gold"
export QUALITY_BUCKET="${PROJECT_NAME}-quality-reports"
export ATHENA_RESULTS_BUCKET="${PROJECT_NAME}-athena-results"

# Glue Data Catalog / Athena (SQL database names don't accept hyphens)
export GLUE_DATABASE="${PROJECT_NAME//-/_}"
export ATHENA_WORKGROUP="${PROJECT_NAME}-wg"

# Kinesis + Lambda (created/destroyed on demand, see create_stream.sh / destroy_stream.sh)
export KINESIS_STREAM_NAME="${PROJECT_NAME}-stream"
export KINESIS_SHARD_COUNT="${KINESIS_SHARD_COUNT:-1}"
export LAMBDA_FUNCTION_NAME="${PROJECT_NAME}-consumer"
export LAMBDA_ROLE_NAME="${PROJECT_NAME}-lambda-role"
export LAMBDA_S3_POLICY_NAME="${PROJECT_NAME}-lambda-s3-put"
