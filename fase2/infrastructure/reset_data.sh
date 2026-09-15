#!/usr/bin/env bash
# Cleans up the DATA written by pipeline runs (Bronze streaming, Silver,
# Gold and, optionally, Bronze batch + quality reports) -- without deleting
# the buckets or the permanent infrastructure (Glue database, Athena
# workgroup) created by setup_aws.sh.
#
# Why this is needed to test orchestrator.py repeatedly:
# `process_silver.py` and `build_gold.py` write each run as a new Parquet
# file (uuid in the name) inside each Hive partition (year=.../state_code=...).
# Running the pipeline again without cleaning up first ADDS the data to the
# existing partitions instead of replacing it -- duplicating rows and
# skewing any analysis done later in Athena.
#
# Usage:
#   ./infrastructure/reset_data.sh                 # cleans streaming + silver + gold (the essentials for reprocessing)
#   ./infrastructure/reset_data.sh --all           # also cleans bronze/batch and quality-reports
#   ./infrastructure/reset_data.sh --dry-run       # only shows what would be deleted, deletes nothing
#   ./infrastructure/reset_data.sh --all --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./config.sh
source "${SCRIPT_DIR}/config.sh"

ALL=false
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --all) ALL=true ;;
    --dry-run) DRY_RUN=true ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg (use --all, --dry-run or --help)" >&2
      exit 1
      ;;
  esac
done

command -v aws >/dev/null 2>&1 || {
  echo "ERROR: AWS CLI not found. Install it (https://aws.amazon.com/cli/) and run 'aws configure' before continuing." >&2
  exit 1
}

RM_FLAGS=(--recursive)
if $DRY_RUN; then
  RM_FLAGS+=(--dryrun)
fi

echo "== Cleaning up pipeline data (project: ${PROJECT_NAME}) =="
$DRY_RUN && echo "[dry-run] nothing will actually be deleted -- only listing what would be removed"
echo

empty_prefix() {
  local uri="$1"
  echo "-- ${uri} --"
  aws s3 rm "${uri}" "${RM_FLAGS[@]}"
  echo
}

empty_prefix "s3://${BRONZE_BUCKET}/streaming/"
empty_prefix "s3://${SILVER_BUCKET}/"
empty_prefix "s3://${GOLD_BUCKET}/"

if $ALL; then
  echo "-- --all: also cleaning bronze/batch and quality-reports --"
  empty_prefix "s3://${BRONZE_BUCKET}/batch/"
  empty_prefix "s3://${QUALITY_BUCKET}/"
fi

if $DRY_RUN; then
  echo "== [dry-run] Done -- nothing was deleted =="
  exit 0
fi

echo "== Data cleaned successfully =="
echo "Buckets and infrastructure (Glue database, Athena workgroup) remain intact."
if ! $ALL; then
  echo "(bronze/batch and quality-reports were NOT touched -- use --all to clean those too)"
fi
echo "Run pipelines/orchestrator.py again for a clean new test."
