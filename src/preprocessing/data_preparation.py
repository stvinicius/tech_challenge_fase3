"""
Módulo de preparação de dados para modelagem
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer

from .silver_schema import PIPELINE_TABLE, read_partitioned_parquet


class DataPreparator:
    """
    Classe para preparar dados de alfabetização para modelagem.
    
    Esta classe:
    - Carrega dados das camadas Gold/Silver
    - Cria a variável target
    - Remove data leakage
    - Cria features derivadas
    - Define pipeline de pré-processamento
    - Divide dados em treino/teste
    """
    
    def __init__(self, gold_path: str, silver_path: str = None):
        """
        Inicializa o preparador de dados.
        
        Args:
            gold_path: Caminho para os dados da camada Gold
            silver_path: Caminho para os dados da camada Silver (opcional)
        """
        self.gold_path = Path(gold_path)
        self.silver_path = Path(silver_path) if silver_path else None
        self.df = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.preprocessor = None
        self.derived_features = []
        self.groups_train = None
        self.feature_exclude = {
            'target', 'ano', 'id_municipio', 'nome_municipio', 'fonte',
        }
        
    def _read_partitioned_parquet(self, data_path: Path) -> pd.DataFrame:
        """Lê parquet Hive (ano=/year=) e normaliza o schema para português."""
        parquet_files = list(data_path.rglob('*.parquet'))
        if not parquet_files:
            raise FileNotFoundError(f"Nenhum arquivo .parquet encontrado em {data_path}")

        print(f"   Encontrados {len(parquet_files)} arquivos particionados em {data_path}")
        return read_partitioned_parquet(data_path)

    def load_data(self, table: str = 'indicador_alfabetizacao'):
        """Carrega a tabela Silver (PT ou EN da Fase 2) ou, se faltar, tenta Gold."""
        candidates = []
        if self.silver_path:
            candidates.append(self.silver_path / table)
            if table != PIPELINE_TABLE:
                candidates.append(self.silver_path / PIPELINE_TABLE)
            candidates.append(self.silver_path)
        if self.gold_path:
            candidates.append(self.gold_path / table)
            candidates.append(self.gold_path / 'indicador_municipio')
            candidates.append(self.gold_path / 'municipality_indicator')
        if self.silver_path and self.silver_path.name == 'silver':
            fase3 = self.silver_path.parent.parent
            fase2 = fase3.parent / 'fase2'
            candidates.append(fase2 / 'output' / 'silver')
            candidates.append(fase3 / 'output' / 'silver')

        last_error = None
        for path in candidates:
            if not path.exists():
                continue
            try:
                print(f"📂 Carregando dados de {path}")
                self.df = self._read_partitioned_parquet(path)
                print(
                    f"   ✅ Dataset carregado: {self.df.shape[0]:,} linhas, "
                    f"{self.df.shape[1]} colunas"
                )
                return self
            except FileNotFoundError as exc:
                last_error = exc

        raise FileNotFoundError(
            last_error or f"Nenhum arquivo .parquet encontrado em {self.gold_path}"
        )
    
    def create_target(self, method='meta', threshold=None):
        """
        Cria o target municipal (não há linha de aluno neste Silver).

        method='meta': 1 se taxa_alfabetizacao >= meta municipal 2024
        method='threshold': 1 se taxa_alfabetizacao >= threshold (taxa 0-100, não 743 SAEB)
        """
        print(f"\n🎯 Criando variável target (método: {method})")

        taxa_col = next(
            (c for c in ('taxa_alfabetizacao', 'literacy_rate') if c in self.df.columns),
            None,
        )
        meta_col = next(
            (
                c for c in (
                    'meta_municipio_alfabetizacao_2024',
                    'municipality_target_literacy_2024',
                    'target_municipality',
                ) if c in self.df.columns
            ),
            None,
        )

        if taxa_col is None:
            raise KeyError(
                "Coluna de taxa não encontrada (esperado 'taxa_alfabetizacao')."
            )

        if method == 'meta':
            if meta_col is None:
                raise KeyError(
                    "Coluna de meta 2024 não encontrada "
                    "(esperado 'meta_municipio_alfabetizacao_2024')."
                )
            print(f"   1 se {taxa_col} >= {meta_col}")
            comparavel = self.df[taxa_col].notna() & self.df[meta_col].notna()
            self.df['target'] = pd.Series(pd.NA, index=self.df.index, dtype='Int64')
            self.df.loc[comparavel, 'target'] = (
                self.df.loc[comparavel, taxa_col] >= self.df.loc[comparavel, meta_col]
            ).astype(int)
        elif method == 'threshold':
            if threshold is None:
                threshold = float(self.df[taxa_col].median())
                print(f"   Threshold não informado; usando mediana da taxa ({threshold:.2f})")
            if threshold > 100:
                raise ValueError(
                    f"threshold={threshold} parece escala SAEB. "
                    "A taxa está em 0-100. Use method='meta' ou um limiar de taxa "
                    "(ex.: 62)."
                )
            print(f"   1 se {taxa_col} >= {threshold}")
            self.df['target'] = (self.df[taxa_col] >= threshold).astype('Int64')
        else:
            raise ValueError(f"method inválido: {method}. Use 'meta' ou 'threshold'.")

        before = len(self.df)
        self.df = self.df.dropna(subset=['target'])
        self.df['target'] = self.df['target'].astype(int)
        dropped = before - len(self.df)
        if dropped:
            print(f"   Removidas {dropped:,} linhas sem taxa/meta para o target")

        target_counts = self.df['target'].value_counts()
        n = len(self.df)
        print("\n   📊 Distribuição do target (município na meta / fora da meta):")
        print(
            f"      Classe 0: {target_counts.get(0, 0):,} "
            f"({target_counts.get(0, 0) / n * 100:.1f}%)"
        )
        print(
            f"      Classe 1: {target_counts.get(1, 0):,} "
            f"({target_counts.get(1, 0) / n * 100:.1f}%)"
        )

        return self
    
    def remove_leakage_features(self):
        """
        Remove features que causam data leakage.
        
        Data leakage = usar informações que não estariam disponíveis
        no momento da predição real.
        """
        print("\n⚠️  Removendo features com data leakage...")
        
        # Features que SÃO o resultado ou são calculadas a partir dele
        leakage_features = [
            'literacy_rate',
            'taxa_alfabetizacao',
            'media_portugues',
            'avg_portuguese_score',
            'meta_municipio_taxa_base',
            'meta_municipio_nivel_alfabetizacao',
            'gap_municipality',
            'gap_state',
            'gap_national',
            'reached_target',
            'status',
            'performance',
        ]
        leakage_prefixes = (
            'meta_municipio_alfabetizacao_',
            'municipality_target_literacy_',
            'proporcao_aluno_nivel_',
            'proficiency_level_',
        )

        removed = []
        for feat in leakage_features:
            if feat in self.df.columns and feat != 'target':
                self.df = self.df.drop(columns=[feat])
                removed.append(feat)
        prefix_hits = [
            c for c in self.df.columns
            if c != 'target' and any(c.startswith(p) for p in leakage_prefixes)
        ]
        if prefix_hits:
            self.df = self.df.drop(columns=prefix_hits)
            removed.extend(prefix_hits)
        
        if removed:
            print(f"   ❌ Removidas {len(removed)} features:")
            for feat in removed:
                print(f"      - {feat}")
        else:
            print("   ✅ Nenhuma feature de leakage encontrada")
        
        return self
    
    def create_derived_features(self):
        """Cria features alinhadas ao EDA (nomes do Silver em português)."""
        print("\n🔧 Criando features derivadas...")

        created = []
        df = self.df

        nivel_cols = sorted(
            [c for c in df.columns if c.startswith('proporcao_aluno_nivel_')],
            key=lambda c: int(c.split('_')[-1]),
        )
        if nivel_cols:
            # Parquet traz proporções como string; sem isso o pipeline
            # trata 0–8 como categóricas e a soma vira concatenação.
            for col in nivel_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['tem_nivel'] = df[nivel_cols].notna().all(axis=1).astype(int)
            created.append('tem_nivel')
            baixos = [c for c in nivel_cols if int(c.split('_')[-1]) <= 3]
            altos = [c for c in nivel_cols if int(c.split('_')[-1]) >= 6]
            if baixos:
                df['prop_niveis_baixos'] = df[baixos].sum(axis=1, min_count=1)
                created.append('prop_niveis_baixos')
            if altos:
                df['prop_niveis_altos'] = df[altos].sum(axis=1, min_count=1)
                created.append('prop_niveis_altos')

        meta_mun = 'meta_municipio_alfabetizacao_2024'
        meta_uf = 'meta_uf_alfabetizacao_2024'
        if meta_mun in df.columns and meta_uf in df.columns:
            df['diff_meta_mun_uf'] = df[meta_mun] - df[meta_uf]
            created.append('diff_meta_mun_uf')
        if meta_mun in df.columns:
            df['tem_meta_2024'] = df[meta_mun].notna().astype(int)
            created.append('tem_meta_2024')

        if 'regiao' in df.columns:
            region_map = {
                'Norte': 1,
                'Nordeste': 2,
                'Centro-Oeste': 3,
                'Sudeste': 4,
                'Sul': 5,
            }
            df['codigo_regiao'] = df['regiao'].map(region_map)
            created.append('codigo_regiao')

        self.df = df
        self.derived_features = created

        if created:
            print(f"   ✅ Criadas {len(created)} features derivadas:")
            for feat in created:
                print(f"      + {feat}")
        else:
            print("   ⚠️  Nenhuma feature derivada (colunas esperadas ausentes)")

        return self
    
    def prepare_features(self):
        """
        Prepara features para modelagem:
        - Identifica features numéricas e categóricas
        - Cria pipeline de pré-processamento
        """
        print("\n🔨 Preparando pipeline de pré-processamento...")
        
        # Separar features e target
        feature_cols = [
            col for col in self.df.columns if col not in self.feature_exclude
        ]
        
        # Identificar tipos de features
        numeric_features = self.df[feature_cols].select_dtypes(
            include=['int64', 'float64']
        ).columns.tolist()
        
        # pandas maps 'str' to numpy <U and raises TypeError
        categorical_features = self.df[feature_cols].select_dtypes(
            include=['object', 'category', 'string']
        ).columns.tolist()
        
        constants = [
            c for c in feature_cols
            if self.df[c].nunique(dropna=False) <= 1
        ]
        print(f"\n   📊 Features identificadas:")
        print(f"      Numéricas ({len(numeric_features)}): {numeric_features[:5]}{'...' if len(numeric_features) > 5 else ''}")
        print(f"      Categóricas ({len(categorical_features)}): {categorical_features}")
        if constants:
            print(
                f"   ⚠️  Features constantes (não informam o modelo): {constants}"
            )
        
        # Pipeline para features numéricas
        numeric_pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])
        
        # Pipeline para features categóricas
        categorical_pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
            ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
        ])
        
        # Combinar pipelines
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_pipeline, numeric_features),
                ('cat', categorical_pipeline, categorical_features)
            ],
            remainder='drop'
        )
        
        print(f"   ✅ Pipeline criado com sucesso!")
        
        return self
    
    def split_data(
        self,
        strategy: str = 'temporal',
        train_year: int = 2023,
        test_year: int = 2024,
    ):
        """
        Backtest temporal: treino no passado, teste no futuro.

        Apenas strategy='temporal'. Split 80/20 por linha vaza município e mistura anos.
        """
        if strategy != 'temporal':
            raise ValueError(
                "Apenas strategy='temporal' (treino 2023 / teste 2024). "
                "Split aleatório 80/20 não é o protocolo deste projeto."
            )

        feature_cols = [
            col for col in self.df.columns if col not in self.feature_exclude
        ]
        X = self.df[feature_cols]
        y = self.df['target']

        if 'ano' not in self.df.columns:
            raise KeyError(
                "Coluna 'ano' ausente. Recarregue os dados para ler a partição Hive."
            )
        train_mask = self.df['ano'] == train_year
        test_mask = self.df['ano'] == test_year
        if not train_mask.any() or not test_mask.any():
            raise ValueError(
                f"Split temporal vazio: treino {train_year}="
                f"{int(train_mask.sum())} linhas, teste {test_year}="
                f"{int(test_mask.sum())} linhas."
            )
        print(
            f"\n✂️  Backtest temporal: treino {train_year} / teste {test_year}"
        )
        print("   Validação = CV no treino (notebook 03). Teste não entra no tuning.")
        self.X_train, self.y_train = X.loc[train_mask], y.loc[train_mask]
        self.X_test, self.y_test = X.loc[test_mask], y.loc[test_mask]
        if 'id_municipio' in self.df.columns:
            self.groups_train = self.df.loc[train_mask, 'id_municipio']
        n_overlap = 0
        if 'id_municipio' in self.df.columns:
            n_overlap = len(
                set(self.df.loc[train_mask, 'id_municipio'])
                & set(self.df.loc[test_mask, 'id_municipio'])
            )
        print(
            f"   Municípios em treino e teste (esperado no backtest): {n_overlap:,}"
        )

        print("   ✅ Divisão concluída:")
        print(f"      Treino: {len(self.X_train):,} amostras")
        print(f"      Teste:  {len(self.X_test):,} amostras")

        train_dist = self.y_train.value_counts(normalize=True)
        test_dist = self.y_test.value_counts(normalize=True)
        print("\n   📊 Distribuição do target:")
        print(
            f"      Treino - Classe 0: {train_dist.get(0, 0)*100:.1f}% | "
            f"Classe 1: {train_dist.get(1, 0)*100:.1f}%"
        )
        print(
            f"      Teste  - Classe 0: {test_dist.get(0, 0)*100:.1f}% | "
            f"Classe 1: {test_dist.get(1, 0)*100:.1f}%"
        )
        return self
    
    def get_data(self):
        """Retorna os dados preparados"""
        return self.X_train, self.X_test, self.y_train, self.y_test, self.preprocessor
    
    def prepare_all(self, target_method='meta', target_threshold=None):
        """
        Executa todo o pipeline de preparação de dados.
        
        Args:
            target_method: Método para criar target
            target_threshold: Threshold para classificação
        """
        print("=" * 80)
        print("🚀 INICIANDO PREPARAÇÃO DE DADOS")
        print("=" * 80)
        
        (self
         .load_data()
         .create_target(method=target_method, threshold=target_threshold)
         .remove_leakage_features()
         .create_derived_features()
         .prepare_features()
         .split_data())
        
        print("\n" + "=" * 80)
        print("✅ PREPARAÇÃO DE DADOS CONCLUÍDA COM SUCESSO!")
        print("=" * 80)
        
        return self
