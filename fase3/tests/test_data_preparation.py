import pytest

from src.preprocessing.data_preparation import DataPreparator
from tests.helpers import municipal_panel


def _prepared(df=None) -> DataPreparator:
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = (df if df is not None else municipal_panel()).copy()
    return (
        prep.create_target(method="meta")
        .remove_leakage_features()
        .create_derived_features()
        .split_data(strategy="temporal")
        .drop_unusable_train_features()
        .prepare_features()
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


def test_obvious_leakage_leaves_meta_for_derived_features():
    prep = DataPreparator(gold_path=".", silver_path=None)
    prep.df = municipal_panel()
    prep.create_target(method="meta").remove_leakage_features()
    assert "taxa_alfabetizacao" not in prep.df.columns
    assert "media_portugues" not in prep.df.columns
    assert "meta_municipio_alfabetizacao_2024" in prep.df.columns
    assert "proporcao_aluno_nivel_0" in prep.df.columns


def test_taxa_and_municipal_meta_out_of_final_X():
    prep = _prepared()
    for col in (
        "taxa_alfabetizacao",
        "media_portugues",
        "meta_municipio_alfabetizacao_2024",
        "diff_meta_mun_uf",
        "proporcao_aluno_nivel_0",
    ):
        assert col not in prep.X_train.columns
        assert col not in prep.X_test.columns
    assert "codigo_regiao" in prep.X_train.columns


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
