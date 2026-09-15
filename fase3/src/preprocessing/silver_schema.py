"""
Schema único para os notebooks da Fase 3 (nomes em português).

O pipeline da Fase 2 grava Silver em inglês (`literacy_rate`, `year=`,
`literacy_indicator`). Os notebooks 01–04 usam português (`taxa_alfabetizacao`,
`ano=`, `indicador_alfabetizacao`). Esta camada traduz os dois para o schema
dos notebooks, sem reprocessar o lake.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PIPELINE_TABLE = "literacy_indicator"
NOTEBOOK_TABLE = "indicador_alfabetizacao"

ENGLISH_TO_PT: dict[str, str] = {
    "municipality_id": "id_municipio",
    "year": "ano",
    "literacy_rate": "taxa_alfabetizacao",
    "avg_portuguese_score": "media_portugues",
    "source": "fonte",
    "municipality_name": "nome_municipio",
    "state_code": "sigla_uf",
    "state_name": "nome_uf",
    "state_indicator_literacy_rate": "taxa_alfabetizacao_uf",
    "municipality_target_base_rate": "meta_municipio_taxa_base",
    "municipality_target_participation_rate": "meta_municipio_percentual_participacao",
    "municipality_target_literacy_level": "meta_municipio_nivel_alfabetizacao",
    "state_target_base_rate": "meta_uf_taxa_base",
    "state_target_participation_rate": "meta_uf_percentual_participacao",
    "national_target_base_rate": "meta_nacional_taxa_base",
    "national_target_participation_rate": "meta_nacional_percentual_participacao",
    **{f"proficiency_level_{i}_ratio": f"proporcao_aluno_nivel_{i}" for i in range(9)},
    **{f"municipality_target_literacy_{y}": f"meta_municipio_alfabetizacao_{y}" for y in range(2024, 2031)},
    **{f"state_target_literacy_{y}": f"meta_uf_alfabetizacao_{y}" for y in range(2024, 2031)},
    **{f"national_target_literacy_{y}": f"meta_nacional_alfabetizacao_{y}" for y in range(2024, 2031)},
}


def hive_partition_value(path: Path, *keys: str) -> str | None:
    for part in path.parts:
        for key in keys:
            if part.startswith(f"{key}="):
                return part.split("=", 1)[1]
    return None


def normalize_silver_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas da Fase 2 (inglês) para o schema dos notebooks."""
    rename = {src: dst for src, dst in ENGLISH_TO_PT.items() if src in df.columns and dst not in df.columns}
    if rename:
        df = df.rename(columns=rename)
    if "ano" not in df.columns and "year" in df.columns:
        df["ano"] = pd.to_numeric(df["year"], errors="coerce")
    return df


def read_partitioned_parquet(data_path: Path) -> pd.DataFrame:
    parquet_files = list(data_path.rglob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"Nenhum arquivo .parquet em {data_path}")

    frames = []
    for file in parquet_files:
        chunk = pd.read_parquet(file)
        ano = hive_partition_value(file, "ano", "year")
        if ano is not None and "ano" not in chunk.columns and "year" not in chunk.columns:
            chunk["ano"] = int(ano)
        uf = hive_partition_value(file, "sigla_uf", "state_code")
        if uf is not None and "sigla_uf" not in chunk.columns and "state_code" not in chunk.columns:
            chunk["sigla_uf"] = uf
        frames.append(chunk)
    return normalize_silver_frame(pd.concat(frames, ignore_index=True))


def resolve_silver_dir(silver_root: Path) -> Path:
    """Prefere a pasta dos notebooks; cai no Silver da Fase 2 se for o que existir."""
    root = Path(silver_root)
    fase3 = Path(__file__).resolve().parents[2]
    fase2 = fase3.parent / "fase2"
    ordered = [
        root / NOTEBOOK_TABLE,
        root / PIPELINE_TABLE,
        root,
        fase2 / "output" / "silver",
        fase2 / "data" / "silver" / PIPELINE_TABLE,
        fase2 / "data" / "silver",
        fase3 / "output" / "silver",
    ]
    seen: set[Path] = set()
    for path in ordered:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        if path.exists() and any(path.rglob("*.parquet")):
            return path
    raise FileNotFoundError(
        f"Silver não encontrado em {silver_root}. "
        "Em fase2/ rode process_silver.py --dry-run e em fase3/: "
        "python scripts/export_silver_fase3.py"
    )


def load_silver_table(silver_root: str | Path) -> tuple[pd.DataFrame, Path]:
    root = Path(silver_root)
    path = resolve_silver_dir(root)
    return read_partitioned_parquet(path), path


def export_notebook_silver(source: Path, dest: Path) -> int:
    """Grava Hive ano= com nomes em português para os notebooks 01–05."""
    df = read_partitioned_parquet(source)
    if "taxa_alfabetizacao" not in df.columns:
        raise ValueError(
            f"{source} não tem taxa_alfabetizacao nem literacy_rate traduzível."
        )
    if "ano" not in df.columns:
        raise ValueError("Coluna ano ausente depois da normalização.")
    dest.mkdir(parents=True, exist_ok=True)
    n_files = 0
    for ano, group in df.groupby("ano"):
        part = dest / f"ano={int(ano)}"
        part.mkdir(parents=True, exist_ok=True)
        group.to_parquet(part / "indicador.parquet", index=False)
        n_files += 1
    return n_files
