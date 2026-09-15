"""Avaliação do classificador municipal (na meta / fora da meta)."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    auc,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

LABELS = ['Fora da meta', 'Na meta']


class ModelEvaluator:
    """Métricas e gráficos do modelo já escolhido no notebook 03 (teste 2024)."""

    def __init__(self, model, X_test, y_test):
        self.model = model
        self.X_test = X_test
        self.y_test = y_test
        self.y_pred = None
        self.y_pred_proba = None
        self.metrics = {}

    def predict(self):
        print('Gerando palpites no teste 2024...')
        self.y_pred = self.model.predict(self.X_test)
        if hasattr(self.model, 'predict_proba'):
            self.y_pred_proba = self.model.predict_proba(self.X_test)[:, 1]
        print(f'   {len(self.y_pred):,} municípios.')
        return self

    def calculate_metrics(self):
        if self.y_pred is None:
            self.predict()

        print('\n' + '=' * 80)
        print('METRICAS NO TESTE 2024 (municipio na meta de alfabetizacao)')
        print('=' * 80)

        self.metrics = {
            'Acuracia': accuracy_score(self.y_test, self.y_pred),
            'Acerto equilibrado': balanced_accuracy_score(self.y_test, self.y_pred),
            'Precisao': precision_score(self.y_test, self.y_pred, zero_division=0),
            'Recall': recall_score(self.y_test, self.y_pred, zero_division=0),
            'F1': f1_score(self.y_test, self.y_pred, zero_division=0),
        }
        if self.y_pred_proba is not None:
            self.metrics['ROC-AUC'] = roc_auc_score(self.y_test, self.y_pred_proba)

        for name, value in self.metrics.items():
            print(f'   {name:22s}: {value:.4f}')
        print(
            '\n   Lembrete: acuracia ~0,50 e F1 ~0,45 perdem do chute '
            '"sempre na meta" (~53% / F1 ~0,70). O acerto equilibrado '
            'perto de 0,50 e a leitura honesta.'
        )
        return self

    def plot_confusion_matrix(self, save_path='../reports/figures/confusion_matrix.png'):
        if self.y_pred is None:
            self.predict()

        cm = confusion_matrix(self.y_test, self.y_pred)
        tn, fp, fn, tp = cm.ravel()

        plt.figure(figsize=(7, 6))
        sns.heatmap(
            cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=LABELS, yticklabels=LABELS,
        )
        plt.xlabel('O que o palpite disse')
        plt.ylabel('O que aconteceu de verdade em 2024')
        plt.title('Onde o palpite acerta e onde erra (teste 2024)')
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'Matriz salva em {save_path}')
        plt.show()

        n = tn + fp + fn + tp
        print('\nLeitura da matriz (5.232 municipios de 2024):')
        print(f'   Acertou "fora da meta" (TN):     {tn:5d}')
        print(f'   Errou: disse na meta, era fora (FP): {fp:5d}')
        print(f'   Errou: disse fora, era na meta (FN): {fn:5d}  <- o erro mais comum')
        print(f'   Acertou "na meta" (TP):          {tp:5d}')
        print(f'   Acertos: {tn + tp} ({(tn + tp) / n:.1%}) | Erros: {fp + fn} ({(fp + fn) / n:.1%})')
        return self

    def plot_roc_curve(self, save_path='../reports/figures/roc_curve.png'):
        if self.y_pred_proba is None:
            print('Este palpite nao devolve probabilidade. Sem curva ROC.')
            return self

        fpr, tpr, _ = roc_curve(self.y_test, self.y_pred_proba)
        roc_auc = auc(fpr, tpr)

        plt.figure(figsize=(7, 6))
        plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'Nosso palpite (area = {roc_auc:.2f})')
        plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--', label='Cara-ou-coroa (area = 0,50)')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('Quando estava FORA da meta, com que frequencia o palpite disse "na meta"?')
        plt.ylabel('Quando estava NA meta, com que frequencia o palpite acertou?')
        plt.title('Curva ROC — teste 2024')
        plt.legend(loc='lower right')
        plt.grid(alpha=0.3)
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'Curva ROC salva em {save_path}  |  area = {roc_auc:.3f}')
        plt.show()
        return self

    def plot_feature_importance(self, top_n=20, save_path='../reports/figures/feature_importance.png'):
        """Arvore: importancia. Logistica: coeficientes (sinal = empurra para na meta ou fora)."""
        classifier = self.model.named_steps.get('classifier')
        try:
            feature_names = self.model.named_steps['preprocessor'].get_feature_names_out()
        except Exception:
            feature_names = None

        if hasattr(classifier, 'coef_'):
            values = classifier.coef_.ravel()
            if feature_names is None:
                feature_names = [f'col_{i}' for i in range(len(values))]
            df = pd.DataFrame({'feature': feature_names, 'peso': values})
            df['abs'] = df['peso'].abs()
            df = df.sort_values('abs', ascending=False).head(top_n)
            colors = ['#2ca02c' if v > 0 else '#d62728' for v in df['peso']]
            plt.figure(figsize=(10, max(4, 0.35 * len(df))))
            plt.barh(df['feature'][::-1], df['peso'][::-1], color=colors[::-1])
            plt.axvline(0, color='black', lw=0.8)
            plt.xlabel('Peso na reta (verde = puxa para "na meta", vermelho = puxa para "fora")')
            plt.title('O que a regressao logistica usa (teste nao entra neste grafico)')
            print('\nMaiores pesos (valor absoluto):')
            for _, row in df.iterrows():
                lado = 'na meta' if row['peso'] > 0 else 'fora da meta'
                print(f"   {row['feature'][:50]:50s}  {row['peso']:+.3f}  ({lado})")
        elif hasattr(classifier, 'feature_importances_'):
            values = classifier.feature_importances_
            if feature_names is None:
                feature_names = [f'col_{i}' for i in range(len(values))]
            df = pd.DataFrame({'feature': feature_names, 'peso': values}).sort_values(
                'peso', ascending=False
            ).head(top_n)
            plt.figure(figsize=(10, 8))
            plt.barh(df['feature'][::-1], df['peso'][::-1])
            plt.xlabel('Importancia (soma 1)')
            plt.title('Colunas que a arvore mais usou')
        else:
            print('Este palpite nao expoe pesos nem importancia de coluna.')
            return self

        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'Grafico salvo em {save_path}')
        plt.show()
        return self

    def generate_classification_report(self, save_path='../reports/classification_report.txt'):
        if self.y_pred is None:
            self.predict()
        report = classification_report(
            self.y_test, self.y_pred,
            target_names=LABELS, digits=4, zero_division=0,
        )
        print('\n' + report)
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w', encoding='utf-8') as handle:
            handle.write('Relatorio de classificacao — teste 2024\n')
            handle.write('Classes: Fora da meta (0) / Na meta (1)\n\n')
            handle.write(report)
            handle.write('\nMetricas gerais\n')
            for name, value in self.metrics.items():
                handle.write(f'{name:22s}: {value:.4f}\n')
        print(f'Relatorio salvo em {save_path}')
        return self

    def get_metrics(self):
        if not self.metrics:
            self.calculate_metrics()
        return self.metrics
