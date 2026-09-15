from pathlib import Path

from src.preprocessing.data_preparation import (
    HONEST_FEATURE_COLUMNS,
    DataPreparator,
    load_or_prepare_split,
)
from src.visualization.plots import FIGURES_DIR, resolve_figure_path
from tests.helpers import municipal_panel


def _write_hive(root: Path) -> Path:
    df = municipal_panel()
    silver = root / "data" / "silver" / "indicador_alfabetizacao"
    for ano, group in df.groupby("ano"):
        part = silver / f"ano={int(ano)}"
        part.mkdir(parents=True, exist_ok=True)
        group.to_parquet(part / "indicador.parquet", index=False)
    return silver


def test_prepare_all_from_hive_parquet(tmp_path):
    _write_hive(tmp_path)
    prep = DataPreparator(
        gold_path=str(tmp_path / "data" / "gold"),
        silver_path=str(tmp_path / "data" / "silver"),
    )
    prep.prepare_all(target_method="meta")
    assert prep.X_train is not None and len(prep.X_train) > 0
    assert set(prep.df.loc[prep.X_train.index, "ano"].unique()) == {2023}
    assert set(prep.X_train.columns) <= set(HONEST_FEATURE_COLUMNS)


def test_load_or_prepare_split_from_silver(tmp_path):
    _write_hive(tmp_path)
    X_train, X_test, y_train, y_test, preprocessor, groups, source = load_or_prepare_split(
        tmp_path
    )
    assert source == "silver"
    assert len(X_train) == len(y_train)
    assert len(X_test) == len(y_test)
    assert preprocessor is not None
    assert groups is not None
    assert set(X_train.columns) <= set(HONEST_FEATURE_COLUMNS)


def test_figure_path_is_under_fase3_not_cwd():
    resolved = resolve_figure_path("reports/figures/missing_values.png")
    assert resolved == FIGURES_DIR / "missing_values.png"
    assert "notebooks" not in resolved.parts
