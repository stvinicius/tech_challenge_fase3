"""Regressão lag-1: taxa do ano anterior → taxa do ano seguinte.

O classificador contemporâneo (notebooks 03–04) não usa a taxa do próprio ano.
Aqui a taxa de 2023 é informação que um gestor já teria no início de 2024.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


def pair_consecutive_years(
    df: pd.DataFrame,
    *,
    id_col: str = "id_municipio",
    year_col: str = "ano",
    rate_col: str = "taxa_alfabetizacao",
    meta_col: str = "meta_municipio_alfabetizacao_2024",
    lag_year: int = 2023,
    target_year: int = 2024,
) -> pd.DataFrame:
    """Uma linha por município com taxa_lag, taxa_alvo e meta (se existir)."""
    need = [id_col, year_col, rate_col]
    absent = [c for c in need if c not in df.columns]
    if absent:
        raise KeyError(f"Colunas obrigatórias ausentes: {absent}")

    extra = [c for c in (meta_col, "regiao", "nome_uf") if c in df.columns]
    lag = (
        df.loc[df[year_col] == lag_year, [id_col, rate_col, *extra]]
        .rename(columns={rate_col: "taxa_lag"})
    )
    fut = (
        df.loc[df[year_col] == target_year, [id_col, rate_col, *extra]]
        .rename(columns={rate_col: "taxa_alvo"})
    )
    if meta_col in fut.columns:
        fut = fut.rename(columns={meta_col: "meta_2024"})
        if meta_col in lag.columns:
            lag = lag.drop(columns=[meta_col])
    paired = lag.merge(fut, on=id_col, suffixes=("_lag", ""))
    paired = paired.dropna(subset=["taxa_lag", "taxa_alvo"])
    return paired.reset_index(drop=True)


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
        "corr": float(np.corrcoef(y_true, y_pred)[0, 1]) if len(y_true) > 1 else float("nan"),
    }


def fit_lag1_ols(taxa_lag: pd.Series, taxa_alvo: pd.Series) -> LinearRegression:
    model = LinearRegression()
    model.fit(taxa_lag.to_frame(), taxa_alvo)
    return model


def classify_vs_meta(rate: pd.Series, meta: pd.Series) -> pd.Series:
    return (rate >= meta).astype(int)


def classification_from_predicted_rate(
    y_true_rate: pd.Series,
    y_pred_rate: pd.Series,
    meta: pd.Series,
) -> dict[str, float]:
    y_true = classify_vs_meta(y_true_rate, meta)
    y_pred = classify_vs_meta(y_pred_rate, meta)
    dummy_one = np.ones(len(y_true), dtype=int)
    return {
        "F1": float(f1_score(y_true, y_pred, zero_division=0)),
        "balanced_acc": float(balanced_accuracy_score(y_true, y_pred)),
        "Dummy_sempre_1_F1": float(f1_score(y_true, dummy_one, zero_division=0)),
        "Dummy_sempre_1_balanced_acc": float(balanced_accuracy_score(y_true, dummy_one)),
    }
