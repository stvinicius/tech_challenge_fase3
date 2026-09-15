#!/usr/bin/env bash
# Renders infrastructure/athena_ddl.sql.in using PROJECT_NAME from config.sh.
# Usage:
#   ./infrastructure/render_athena_ddl.sh
#   PROJECT_NAME=meu-projeto ./infrastructure/render_athena_ddl.sh /tmp/athena.sql
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=config.sh
source "${ROOT}/config.sh"
TEMPLATE="${ROOT}/athena_ddl.sql.in"
OUT="${1:-${ROOT}/athena_ddl.generated.sql}"
if [[ ! -f "${TEMPLATE}" ]]; then
  echo "Template not found: ${TEMPLATE}" >&2
  exit 1
fi
sed -e "s/__GLUE_DATABASE__/${GLUE_DATABASE}/g" \
    -e "s/__GOLD_BUCKET__/${GOLD_BUCKET}/g" \
    "${TEMPLATE}" > "${OUT}"
echo "Wrote ${OUT} (database=${GLUE_DATABASE} bucket=${GOLD_BUCKET})"
