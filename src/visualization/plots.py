"""
Módulo de visualização de dados
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Configurar estilo
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10


class DataVisualizer:
    """
    Classe para criar visualizações dos dados de alfabetização.
    
    Esta classe:
    - Cria gráficos exploratórios
    - Analisa distribuições
    - Visualiza correlações
    - Gera gráficos para relatórios
    """
    
    def __init__(self, df):
        """
        Inicializa o visualizador.
        
        Args:
            df: DataFrame com os dados
        """
        self.df = df
    
    def plot_target_distribution(self, save_path='reports/figures/target_distribution.png'):
        """
        Plota distribuição da variável target.
        
        Args:
            save_path: Caminho para salvar a figura
        """
        if 'target' not in self.df.columns:
            print("⚠️  Coluna 'target' não encontrada no DataFrame.")
            return self
        
        print("📊 Plotando distribuição do target...")
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        # Gráfico de barras
        target_counts = self.df['target'].value_counts().reindex([0, 1], fill_value=0)
        labels = ['Fora da meta', 'Na meta']
        axes[0].bar(labels, target_counts.values, 
                   color=['#e74c3c', '#2ecc71'])
        axes[0].set_ylabel('Quantidade', fontsize=12)
        axes[0].set_title('Distribuição do Target (Contagem)', fontsize=14, fontweight='bold')
        
        # Adicionar valores nas barras
        for i, v in enumerate(target_counts.values):
            axes[0].text(i, v + 50, str(v), ha='center', fontweight='bold')
        
        # Gráfico de pizza
        axes[1].pie(target_counts.values, labels=labels,
                   autopct='%1.1f%%', colors=['#e74c3c', '#2ecc71'], startangle=90)
        axes[1].set_title('Distribuição do Target (Proporção)', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # Salvar
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"   ✅ Gráfico salvo em {save_path}")
        
        plt.show()
        
        return self
    
    def plot_numeric_distributions(self, columns=None, save_path='reports/figures/numeric_distributions.png'):
        """
        Plota distribuições de variáveis numéricas.
        
        Args:
            columns: Lista de colunas (None = todas numéricas)
            save_path: Caminho para salvar a figura
        """
        print("📊 Plotando distribuições numéricas...")
        
        if columns is None:
            columns = self.df.select_dtypes(include=['int64', 'float64']).columns.tolist()
            # Remover target se existir
            columns = [col for col in columns if col != 'target'][:6]  # Limitar a 6
        
        n_cols = len(columns)
        n_rows = (n_cols + 2) // 3
        
        fig, axes = plt.subplots(n_rows, 3, figsize=(15, n_rows * 4))
        axes = axes.flatten() if n_cols > 1 else [axes]
        
        for idx, col in enumerate(columns):
            if col in self.df.columns:
                self.df[col].hist(bins=30, ax=axes[idx], edgecolor='black', alpha=0.7)
                axes[idx].set_title(col, fontsize=12, fontweight='bold')
                axes[idx].set_xlabel('Valor')
                axes[idx].set_ylabel('Frequência')
        
        # Remover subplots vazios
        for idx in range(len(columns), len(axes)):
            fig.delaxes(axes[idx])
        
        plt.tight_layout()
        
        # Salvar
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"   ✅ Gráfico salvo em {save_path}")
        
        plt.show()
        
        return self
    
    def plot_correlation_matrix(self, columns=None, save_path='reports/figures/correlation_matrix.png'):
        """
        Plota matriz de correlação.
        
        Args:
            columns: Lista de colunas (None = todas numéricas)
            save_path: Caminho para salvar a figura
        """
        print("📊 Plotando matriz de correlação...")
        
        if columns is None:
            numeric_df = self.df.select_dtypes(include=['int64', 'float64'])
        else:
            numeric_df = self.df[columns]
        
        # Calcular correlação
        correlation = numeric_df.corr()
        
        # Plotar
        plt.figure(figsize=(12, 10))
        sns.heatmap(correlation, annot=True, fmt='.2f', cmap='coolwarm', 
                   center=0, square=True, linewidths=1, cbar_kws={"shrink": 0.8})
        plt.title('Matriz de Correlação', fontsize=16, fontweight='bold', pad=20)
        
        # Salvar
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"   ✅ Matriz salva em {save_path}")
        
        plt.show()
        
        return self
    
    def plot_categorical_vs_target(self, categorical_col, save_path=None):
        """
        Plota relação entre variável categórica e target.
        
        Args:
            categorical_col: Nome da coluna categórica
            save_path: Caminho para salvar (None = não salva)
        """
        if categorical_col not in self.df.columns:
            print(f"⚠️  Coluna '{categorical_col}' não encontrada.")
            return self
        
        if 'target' not in self.df.columns:
            print("⚠️  Coluna 'target' não encontrada.")
            return self
        
        print(f"📊 Plotando {categorical_col} vs target...")
        
        # Criar crosstab
        ct = pd.crosstab(self.df[categorical_col], self.df['target'], normalize='index')
        
        # Plotar
        ct.plot(kind='bar', stacked=False, figsize=(12, 6), 
               color=['#e74c3c', '#2ecc71'])
        plt.xlabel(categorical_col, fontsize=12)
        plt.ylabel('Proporção', fontsize=12)
        plt.title(f'{categorical_col} vs Target', fontsize=14, fontweight='bold')
        plt.legend(['Fora da meta', 'Na meta'])
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Salvar
        if save_path:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"   ✅ Gráfico salvo em {save_path}")
        
        plt.show()
        
        return self
    
    def plot_missing_values(self, save_path='reports/figures/missing_values.png'):
        """
        Plota análise de valores faltantes.
        
        Args:
            save_path: Caminho para salvar a figura
        """
        print("📊 Plotando valores faltantes...")
        
        # Calcular missing
        missing = self.df.isnull().sum()
        missing = missing[missing > 0].sort_values(ascending=False)
        
        if len(missing) == 0:
            print("   ✅ Não há valores faltantes no dataset!")
            return self
        
        # Calcular percentual
        missing_pct = (missing / len(self.df)) * 100
        
        # Criar DataFrame
        missing_df = pd.DataFrame({
            'Count': missing,
            'Percentage': missing_pct
        })
        
        # Plotar
        fig, ax = plt.subplots(figsize=(10, 6))
        missing_df['Percentage'].plot(kind='barh', ax=ax, color='coral')
        ax.set_xlabel('Percentual de Valores Faltantes (%)', fontsize=12)
        ax.set_ylabel('Variável', fontsize=12)
        ax.set_title('Análise de Valores Faltantes', fontsize=14, fontweight='bold')
        
        # Adicionar valores nas barras
        for idx, value in enumerate(missing_df['Percentage'].values):
            ax.text(value + 0.5, idx, f'{value:.1f}%', va='center')
        
        plt.tight_layout()
        
        # Salvar
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"   ✅ Gráfico salvo em {save_path}")
        
        plt.show()
        
        return self
