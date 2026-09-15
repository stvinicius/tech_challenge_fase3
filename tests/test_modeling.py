import pandas as pd
import pytest
from sklearn.model_selection import GroupKFold

from src.modeling.lag1 import (
    classification_from_predicted_rate,
    fit_lag1_ols,
    pair_consecutive_years,
    regression_metrics,
)
from src.modeling.train_model import ModelTrainer
from tests.helpers import municipal_panel


def test_groupkfold_receives_municipality_groups():
    prep_groups = pd.Series(["a", "a", "b", "b", "c", "c", "d", "d"])
    trainer = ModelTrainer(preprocessor=None, groups=prep_groups, cv_splits=4)
    assert isinstance(trainer.cv, GroupKFold)
    assert trainer.cv.get_n_splits() == 4


def test_lag1_ols_beats_persistence_on_constant_shift():
    df = municipal_panel(n=10)
    paired = pair_consecutive_years(df)
    assert len(paired) == 10
    assert paired["taxa_lag"].corr(paired["taxa_alvo"]) == pytest.approx(1.0)
    persist = paired["taxa_lag"]
    model = fit_lag1_ols(paired["taxa_lag"], paired["taxa_alvo"])
    ols_pred = model.predict(paired[["taxa_lag"]])
    persist_mae = regression_metrics(paired["taxa_alvo"], persist)["MAE"]
    ols_mae = regression_metrics(paired["taxa_alvo"], ols_pred)["MAE"]
    assert ols_mae < persist_mae


def test_lag1_ols_and_classification_vs_dummy():
    df = municipal_panel(n=10)
    paired = pair_consecutive_years(df)
    model = fit_lag1_ols(paired["taxa_lag"], paired["taxa_alvo"])
    pred = model.predict(paired[["taxa_lag"]])
    clf = classification_from_predicted_rate(
        paired["taxa_alvo"], pd.Series(pred), paired["meta_2024"]
    )
    assert "F1" in clf
    assert 0.0 <= clf["F1"] <= 1.0
