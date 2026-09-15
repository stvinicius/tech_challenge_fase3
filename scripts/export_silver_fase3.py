#!/usr/bin/env python3
"""
Copia o Silver da Fase 2 (inglês, `fase2/output/silver`)
para o layout dos notebooks da Fase 3: data/silver/indicador_alfabetizacao.

  python scripts/export_silver_fase3.py
  python scripts/export_silver_fase3.py --source ../fase2/output/silver
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FASE3_ROOT = Path(__file__).resolve().parent.parent
FASE2_ROOT = FASE3_ROOT.parent / "fase2"
sys.path.insert(0, str(FASE3_ROOT))

from src.preprocessing.silver_schema import (  # noqa: E402
    NOTEBOOK_TABLE,
    PIPELINE_TABLE,
    export_notebook_silver,
)


def _pick_source(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    candidates = [
        FASE3_ROOT / "data" / "silver" / NOTEBOOK_TABLE,
        FASE2_ROOT / "output" / "silver",
        FASE2_ROOT / "data" / "silver" / PIPELINE_TABLE,
        FASE2_ROOT / "data" / "silver",
        FASE3_ROOT / "data" / "silver" / PIPELINE_TABLE,
        FASE3_ROOT / "data" / "silver",
    ]
    for path in candidates:
        if path.exists() and any(path.rglob("*.parquet")):
            return path
    raise FileNotFoundError(
        "Nenhum Silver encontrado. Em fase2/ rode "
        "`python pipelines/batch/process_silver.py --dry-run` "
        "e depois este script."
    )


def export(source: Path, dest: Path) -> int:
    n_files = export_notebook_silver(source, dest)
    print(f"Exportadas {n_files} partição(ões) → {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Pasta Hive do Silver de origem")
    parser.add_argument(
        "--dest",
        type=Path,
        default=FASE3_ROOT / "data" / "silver" / NOTEBOOK_TABLE,
        help="Destino no schema dos notebooks",
    )
    args = parser.parse_args()
    source = _pick_source(args.source)
    print(f"Origem: {source}")
    return export(source, args.dest)


if __name__ == "__main__":
    raise SystemExit(main())
