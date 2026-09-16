from pathlib import Path
import warnings

import pandas as pd

from src.preprocessing.silver_schema import (
    export_notebook_silver,
    hive_partition_value,
    normalize_silver_frame,
    read_partitioned_parquet,
)


def test_normalize_english_to_portuguese():
    df = pd.DataFrame(
        {
            "literacy_rate": [60.0],
            "municipality_id": [1100015],
            "year": [2023],
            "state_code": ["RO"],
            "proficiency_level_0_ratio": [0.1],
            "municipality_target_literacy_2024": [55.0],
        }
    )
    out = normalize_silver_frame(df)
    assert list(out.columns) == [
        "taxa_alfabetizacao",
        "id_municipio",
        "ano",
        "sigla_uf",
        "proporcao_aluno_nivel_0",
        "meta_municipio_alfabetizacao_2024",
    ]


def test_normalize_keeps_portuguese():
    df = pd.DataFrame({"taxa_alfabetizacao": [1.0], "id_municipio": [1], "ano": [2024]})
    out = normalize_silver_frame(df)
    assert "taxa_alfabetizacao" in out.columns
    assert "literacy_rate" not in out.columns


def test_hive_year_or_ano():
    path = Path("/tmp/year=2023/state_code=BA/part.parquet")
    assert hive_partition_value(path, "ano", "year") == "2023"
    assert hive_partition_value(path, "sigla_uf", "state_code") == "BA"


def test_export_notebook_silver_writes_ano_partitions(tmp_path: Path):
    src = tmp_path / "en"
    part = src / "year=2024" / "state_code=RO"
    part.mkdir(parents=True)
    pd.DataFrame(
        {"literacy_rate": [70.0], "municipality_id": [1100015]}
    ).to_parquet(part / "a.parquet", index=False)
    dest = tmp_path / "pt"
    n = export_notebook_silver(src, dest)
    assert n == 1
    out = read_partitioned_parquet(dest)
    assert "taxa_alfabetizacao" in out.columns
    assert int(out["ano"].iloc[0]) == 2024


def test_concat_skips_all_na_columns_without_futurewarning(tmp_path: Path):
    a = tmp_path / "ano=2023" / "sigla_uf=RO"
    b = tmp_path / "ano=2024" / "sigla_uf=RO"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    pd.DataFrame(
        {"taxa_alfabetizacao": [50.0], "proporcao_aluno_nivel_0": [pd.NA]}
    ).to_parquet(a / "x.parquet", index=False)
    pd.DataFrame(
        {"taxa_alfabetizacao": [70.0], "proporcao_aluno_nivel_0": [1.2]}
    ).to_parquet(b / "x.parquet", index=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        out = read_partitioned_parquet(tmp_path)
    assert len(out) == 2
    assert out["proporcao_aluno_nivel_0"].notna().sum() == 1
