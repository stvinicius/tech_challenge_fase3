#!/usr/bin/env bash
# Ponte Fase 2 → notebooks da Fase 3.
set -euo pipefail
FASE3="$(cd "$(dirname "$0")/.." && pwd)"
FASE2="$(cd "$FASE3/../fase2" && pwd)"
cd "$FASE3"

if [[ -d "$FASE2/output/silver" ]] && find "$FASE2/output/silver" -name '*.parquet' | grep -q .; then
  python scripts/export_silver_fase3.py --source "$FASE2/output/silver"
elif [[ -d "$FASE2/data/silver/literacy_indicator" ]] && find "$FASE2/data/silver/literacy_indicator" -name '*.parquet' | grep -q .; then
  python scripts/export_silver_fase3.py --source "$FASE2/data/silver/literacy_indicator"
elif [[ -d data/silver/indicador_alfabetizacao ]] && find data/silver/indicador_alfabetizacao -name '*.parquet' | grep -q .; then
  echo "Silver PT já existe em data/silver/indicador_alfabetizacao"
else
  echo "Nenhum Silver local encontrado."
  echo "1) cd ../fase2 && python pipelines/orchestrator.py --dry-run"
  echo "2) cd ../fase3 && python scripts/export_silver_fase3.py"
  exit 1
fi
