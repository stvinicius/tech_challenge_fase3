import pytest

from src.preprocessing.data_preparation import DataPreparator
from tests.helpers import municipal_panel


def _prepared(df=None) -> DataPreparator:
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = (df if df is not None else municipal_panel()).copy()
    return (
        prep.create_target(method="meta")
        .remove_leakage_features()
        .prepare_features()
        .split_data(strategy="temporal")
    )


def test_target_is_meta_2024_not_saeb():
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = municipal_panel()
    prep.create_target(method="meta")
    row = prep.df.iloc[0]
    expected = int(row["taxa_alfabetizacao"] >= 60.0)
    assert row["target"] == expected


def test_threshold_743_rejected():
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = municipal_panel()
    with pytest.raises(ValueError, match="SAEB"):
        prep.create_target(method="threshold", threshold=743)


def test_taxa_and_municipal_meta_out_of_X():
    prep = _prepared()
    for col in ("taxa_alfabetizacao", "media_portugues", "meta_municipio_alfabetizacao_2024"):
        assert col not in prep.X_train.columns
        assert col not in prep.X_test.columns


def test_temporal_split_years_and_groups():
    prep = _prepared()
    assert set(prep.df.loc[prep.X_train.index, "ano"].unique()) == {2023}
    assert set(prep.df.loc[prep.X_test.index, "ano"].unique()) == {2024}
    assert prep.groups_train is not None
    assert prep.groups_train.nunique() == prep.X_train.shape[0]


def test_random_split_forbidden():
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = municipal_panel()
    prep.create_target(method="meta").remove_leakage_features().prepare_features()
    with pytest.raises(ValueError, match="temporal"):
        prep.split_data(strategy="random")


def test_prepare_features_accepts_pandas_string_columns():
    df = municipal_panel()
    df["regiao"] = df["regiao"].astype("string")
    df["nome_uf"] = df["nome_uf"].astype("string")
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = df
    prep.create_target(method="meta").remove_leakage_features().prepare_features()
    cat_cols = prep.preprocessor.transformers[1][2]
    assert "regiao" in cat_cols
    assert "nome_uf" in cat_cols
