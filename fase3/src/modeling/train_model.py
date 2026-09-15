"""
Treinamento de modelos no protocolo do notebook 02:
treino 2023, validação = CV (GroupKFold por município), teste 2024 só no final.
"""

from pathlib import Path
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    make_scorer,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GridSearchCV, GroupKFold, StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier


def _n_jobs() -> int:
    """1 por padrão (CI/sandbox). SKLEARN_N_JOBS=-1 usa todos os núcleos."""
    return int(os.environ.get('SKLEARN_N_JOBS', '1'))


class ModelTrainer:
    """Compara modelos só com CV no treino; o holdout entra uma vez, depois da escolha."""

    def __init__(self, preprocessor, groups=None, cv_splits=5, scoring='f1'):
        self.preprocessor = preprocessor
        self.groups = groups
        self.scoring = scoring
        self.cv_splits = cv_splits
        if groups is not None:
            n_groups = pd.Series(groups).nunique()
            n_splits = min(cv_splits, n_groups)
            self.cv = GroupKFold(n_splits=n_splits)
            self.cv_name = f'GroupKFold({n_splits}) por município'
        else:
            self.cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)
            self.cv_name = f'StratifiedKFold({cv_splits})'
        self.models = {}
        self.results = []
        self.best_model = None
        self.best_model_name = None
        self.test_metrics = None

    def _pipeline(self, classifier):
        return Pipeline([
            ('preprocessor', clone(self.preprocessor)),
            ('classifier', classifier),
        ])

    def get_candidate_models(self):
        """Dummy = chão. class_weight='balanced' no treino (classe 1 ~18% em 2023)."""
        return {
            'Dummy (majority)': DummyClassifier(strategy='most_frequent'),
            'Logistic Regression': LogisticRegression(
                random_state=42, max_iter=1000, class_weight='balanced',
            ),
            'Decision Tree': DecisionTreeClassifier(
                random_state=42, class_weight='balanced',
            ),
            'Random Forest': RandomForestClassifier(
                random_state=42, n_jobs=_n_jobs(), class_weight='balanced',
            ),
            'Gradient Boosting': GradientBoostingClassifier(random_state=42),
        }

    def _cv_kwargs(self):
        kwargs = {'cv': self.cv, 'scoring': {
            'f1': make_scorer(f1_score, zero_division=0),
            'balanced_accuracy': 'balanced_accuracy',
            'precision': make_scorer(precision_score, zero_division=0),
            'recall': make_scorer(recall_score, zero_division=0),
        }}
        if self.groups is not None:
            kwargs['groups'] = self.groups
        return kwargs

    def evaluate_cv(self, X_train, y_train, models_to_train=None):
        """Treina e compara só com CV no 2023. Não recebe X_test / y_test."""
        print('\n' + '=' * 80)
        print(f'VALIDAÇÃO CRUZADA NO TREINO — {self.cv_name}')
        print('Métrica de escolha: F1 da classe 1. O teste 2024 não entra aqui.')
        print('=' * 80)

        candidates = self.get_candidate_models()
        if models_to_train:
            candidates = {k: v for k, v in candidates.items() if k in models_to_train}

        self.results = []
        self.models = {}
        cv_kwargs = self._cv_kwargs()

        for name, classifier in candidates.items():
            print(f'\n{name}')
            print('-' * 80)
            model = self._pipeline(classifier)
            start = time.time()
            try:
                scores = cross_validate(
                    model, X_train, y_train,
                    n_jobs=_n_jobs(),
                    return_train_score=False,
                    **cv_kwargs,
                )
                elapsed = time.time() - start
                row = {
                    'Model': name,
                    'CV F1': scores['test_f1'].mean(),
                    'CV F1 std': scores['test_f1'].std(),
                    'CV balanced acc': scores['test_balanced_accuracy'].mean(),
                    'CV precision': scores['test_precision'].mean(),
                    'CV recall': scores['test_recall'].mean(),
                    'CV time (s)': elapsed,
                }
                print(
                    f"   F1: {row['CV F1']:.4f} (+/- {row['CV F1 std']:.4f})  |  "
                    f"balanced acc: {row['CV balanced acc']:.4f}  |  "
                    f"{elapsed:.1f}s"
                )
                # Refit no 2023 inteiro (ainda sem olhar 2024)
                model.fit(X_train, y_train)
                self.models[name] = model
                self.results.append(row)
            except Exception as exc:
                print(f'   Erro: {exc}')

        return self

    def optimize_hyperparameters(
        self,
        X_train,
        y_train,
        model_name='Random Forest',
        param_grid=None,
        scoring=None,
    ):
        """Grid Search + o mesmo CV do treino. O 2024 não entra."""
        print('\n' + '=' * 80)
        print(f'GRID SEARCH: {model_name}  |  CV = {self.cv_name}')
        print('=' * 80)

        if model_name not in self.models and model_name not in self.get_candidate_models():
            print(f"Modelo '{model_name}' não encontrado.")
            return self

        if param_grid is None:
            param_grid = self._default_param_grid(model_name)
            if param_grid is None:
                print(f'Grid padrão não definido para {model_name}.')
                return self

        n_combos = int(np.prod([len(v) for v in param_grid.values()]))
        print(f'Combinações: {n_combos}  |  parâmetros: {list(param_grid.keys())}')

        if model_name in self.models:
            estimator = clone(self.models[model_name])
        else:
            estimator = self._pipeline(self.get_candidate_models()[model_name])

        scorer = scoring or make_scorer(f1_score, zero_division=0)
        grid = GridSearchCV(
            estimator,
            param_grid,
            cv=self.cv,
            scoring=scorer,
            n_jobs=_n_jobs(),
            refit=True,
            verbose=1,
        )
        fit_kwargs = {}
        if self.groups is not None:
            fit_kwargs['groups'] = self.groups

        start = time.time()
        grid.fit(X_train, y_train, **fit_kwargs)
        elapsed = time.time() - start

        print(f'\nGrid Search em {elapsed:.1f}s')
        print('Melhores parâmetros:')
        for key, value in grid.best_params_.items():
            print(f'   {key}: {value}')
        print(f'CV F1 do vencedor: {grid.best_score_:.4f}')

        tuned_name = f'{model_name} (Grid Search)'
        self.models[tuned_name] = grid.best_estimator_
        self.results.append({
            'Model': tuned_name,
            'CV F1': grid.best_score_,
            'CV F1 std': np.nan,
            'CV balanced acc': np.nan,
            'CV precision': np.nan,
            'CV recall': np.nan,
            'CV time (s)': elapsed,
        })
        self.best_model = grid.best_estimator_
        self.best_model_name = tuned_name
        return self

    @staticmethod
    def _default_param_grid(model_name):
        grids = {
            'Random Forest': {
                'classifier__n_estimators': [100, 200],
                'classifier__max_depth': [10, 20, None],
                'classifier__min_samples_leaf': [1, 4],
            },
            'Gradient Boosting': {
                'classifier__n_estimators': [100, 200],
                'classifier__learning_rate': [0.05, 0.1],
                'classifier__max_depth': [2, 3],
            },
            'Logistic Regression': {
                'classifier__C': [0.1, 1, 10],
            },
            'Decision Tree': {
                'classifier__max_depth': [5, 10, 20, None],
                'classifier__min_samples_leaf': [1, 4, 10],
            },
        }
        return grids.get(model_name)

    def select_best_model(self, metric='CV F1'):
        if not self.results:
            print('Nenhum modelo avaliado ainda.')
            return None

        results_df = self.get_results_df()
        best_row = results_df.loc[results_df[metric].idxmax()]
        self.best_model_name = best_row['Model']
        self.best_model = self.models[self.best_model_name]

        print('\n' + '=' * 80)
        print('MELHOR MODELO (escolhido pela CV no 2023)')
        print('=' * 80)
        print(f"   {self.best_model_name}")
        print(f"   {metric}: {best_row[metric]:.4f}")
        print('   O teste 2024 ainda não foi usado.')
        return self.best_model

    def evaluate_test(self, X_test, y_test):
        """Única avaliação no 2024. Chamar depois de select_best_model."""
        if self.best_model is None:
            print('Selecione o melhor modelo pela CV antes de olhar o teste.')
            return None

        print('\n' + '=' * 80)
        print('AVALIAÇÃO FINAL NO TESTE 2024 (uma vez)')
        print('=' * 80)
        y_pred = self.best_model.predict(X_test)
        self.test_metrics = {
            'Model': self.best_model_name,
            'F1': f1_score(y_test, y_pred, zero_division=0),
            'Balanced accuracy': balanced_accuracy_score(y_test, y_pred),
            'Precision': precision_score(y_test, y_pred, zero_division=0),
            'Recall': recall_score(y_test, y_pred, zero_division=0),
            'Accuracy': accuracy_score(y_test, y_pred),
        }
        print(f"   Modelo: {self.best_model_name}")
        for key, value in self.test_metrics.items():
            if key == 'Model':
                continue
            print(f'   {key:20s}: {value:.4f}')
        print(
            '\n   Accuracy no 2024 engana: um chute sempre-1 acerta ~53%. '
            'Use F1 / balanced accuracy.'
        )
        return self.test_metrics

    def get_results_df(self):
        df = pd.DataFrame(self.results)
        if not df.empty:
            df = df.sort_values('CV F1', ascending=False)
        return df

    def save_model(self, filepath='models/best_model.pkl'):
        if self.best_model is None:
            print('Nenhum modelo escolhido. Rode select_best_model() primeiro.')
            return self

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.best_model, filepath)
        print(f'\nModelo salvo em {filepath}')

        results_path = filepath.parent / 'model_comparison_results.csv'
        self.get_results_df().to_csv(results_path, index=False)
        print(f'Resultados de CV salvos em {results_path}')
        return self

    @staticmethod
    def load_model(filepath='models/best_model.pkl'):
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f'Modelo não encontrado em {filepath}')
        print(f'Carregando modelo de {filepath}...')
        return joblib.load(filepath)
