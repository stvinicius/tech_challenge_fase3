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

HONEST_FEATURE_COLUMNS: tuple[str, ...] = (
    "nome_uf",
    "regiao",
    "meta_municipio_percentual_participacao",
    "meta_uf_percentual_participacao",
    "meta_uf_alfabetizacao_2024",
    "codigo_regiao",
)


def unusable_train_columns(X: pd.DataFrame) -> list[str]:
    """Colunas nulas/constantes no treino ou trajetória da meta municipal."""
    all_nan = X.columns[X.isna().all()].tolist()
    constants = [c for c in X.columns if X[c].nunique(dropna=False) <= 1]
    trajetoria = [
        c for c in X.columns
        if c.startswith("meta_municipio_alfabetizacao_")
        or c.startswith("municipality_target_literacy_")
        or c.startswith("proporcao_aluno_nivel_")
        or c.startswith("proficiency_level_")
        or c.startswith("prop_niveis_")
        or c in {"diff_meta_mun_uf", "meta_uf_taxa_base"}
        or (c.startswith("meta_uf_alfabetizacao_") and not c.endswith("_2024"))
    ]
    return sorted(set(all_nan) | set(constants) | set(trajetoria))


def apply_honest_feature_set(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Única fonte da lista usada nos notebooks 03 e 04."""
    drop_cols = unusable_train_columns(X_train)
    X_train = X_train.drop(columns=drop_cols, errors="ignore")
    X_test = X_test.drop(columns=drop_cols, errors="ignore")
    keep = [c for c in HONEST_FEATURE_COLUMNS if c in X_train.columns]
    if keep:
        extra = [c for c in X_train.columns if c not in keep]
        if extra:
            print("Fora do recorte honesto (nao listado em HONEST_FEATURE_COLUMNS):")
            for col in extra:
                print(f"      - {col}")
        X_train = X_train[keep]
        X_test = X_test[[c for c in keep if c in X_test.columns]]
    return X_train, X_test


def load_or_prepare_split(root: Path):
    """Carrega data/processed ou refaz o backtest a partir do Silver."""
    import joblib

    root = Path(root)
    processed = root / "data" / "processed"
    required = [
        "X_train.parquet",
        "X_test.parquet",
        "y_train.parquet",
        "y_test.parquet",
    ]
    if all((processed / name).exists() for name in required):
        print(f"Carregando {processed} (notebook 02)...")
        X_train = pd.read_parquet(processed / "X_train.parquet")
        X_test = pd.read_parquet(processed / "X_test.parquet")
        y_train = pd.read_parquet(processed / "y_train.parquet")["target"]
        y_test = pd.read_parquet(processed / "y_test.parquet")["target"]
        X_train, X_test = apply_honest_feature_set(X_train, X_test)
        preprocessor_path = processed / "preprocessor.pkl"
        preprocessor = joblib.load(preprocessor_path) if preprocessor_path.exists() else None
        groups_path = processed / "groups_train.parquet"
        if groups_path.exists():
            groups_train = pd.read_parquet(groups_path)["id_municipio"]
            groups_train.index = X_train.index
        else:
            groups_train = None
        return X_train, X_test, y_train, y_test, preprocessor, groups_train, "processed"

    print("processed ausente. Preparando do Silver (meta 2024 + backtest 2023/2024)...")
    prep = DataPreparator(
        gold_path=str(root / "data" / "gold"),
        silver_path=str(root / "data" / "silver"),
    )
    prep.prepare_all(target_method="meta")
    X_train, X_test, y_train, y_test, preprocessor = prep.get_data()
    return X_train, X_test, y_train, y_test, preprocessor, prep.groups_train, "silver"


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
                print(f"Carregando dados de {path}")
                self.df = self._read_partitioned_parquet(path)
                print(
                    f"   Dataset carregado: {self.df.shape[0]:,} linhas, "
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
        print(f"\nCriando variavel target (metodo: {method})")

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
        print("\n   Distribuicao do target (municipio na meta / fora da meta):")
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
        """Remove a cola óbvia (notebook 02).

        A trajetória de meta municipal e os níveis 0–8 saem depois, no
        backtest (notebook 03 / ``drop_unusable_train_features``), para
        as features derivadas ainda poderem usar essas colunas.
        """
        print("\nRemovendo features com data leakage...")

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

        removed = [
            feat for feat in leakage_features
            if feat in self.df.columns and feat != 'target'
        ]
        if removed:
            self.df = self.df.drop(columns=removed)
            print(f"   Removidas {len(removed)} features:")
            for feat in removed:
                print(f"      - {feat}")
        else:
            print("   Nenhuma feature de leakage encontrada")

        return self

    def drop_unusable_train_features(self):
        """Notebook 03: nulo no treino, constante, trajetória da meta municipal, recorte honesto."""
        if self.X_train is None or self.X_test is None:
            raise RuntimeError("Rode split_data() antes de drop_unusable_train_features().")

        drop_cols = unusable_train_columns(self.X_train)
        if drop_cols:
            print("\nFora do backtest honesto:")
            all_nan = self.X_train.columns[self.X_train.isna().all()].tolist()
            constants = [c for c in self.X_train.columns if self.X_train[c].nunique(dropna=False) <= 1]
            for col in drop_cols:
                if col in all_nan:
                    motivo = "nula no treino"
                elif col in constants:
                    motivo = "constante no treino"
                else:
                    motivo = "trajetoria municipal / mesma familia da taxa_base"
                print(f"      - {col} ({motivo})")
        self.X_train, self.X_test = apply_honest_feature_set(self.X_train, self.X_test)
        return self
    
    def create_derived_features(self):
        """Cria features alinhadas ao EDA (nomes do Silver em português)."""
        print("\nCriando features derivadas...")

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
            print(f"   Criadas {len(created)} features derivadas:")
            for feat in created:
                print(f"      + {feat}")
        else:
            print("   Nenhuma feature derivada (colunas esperadas ausentes)")

        return self
    
    def prepare_features(self):
        """
        Prepara features para modelagem:
        - Identifica features numéricas e categóricas
        - Cria pipeline de pré-processamento
        """
        print("\nPreparando pipeline de pre-processamento...")
        
        # Separar features e target
        if self.X_train is not None:
            frame = self.X_train
            feature_cols = list(frame.columns)
        else:
            feature_cols = [
                col for col in self.df.columns if col not in self.feature_exclude
            ]
            frame = self.df[feature_cols]

        numeric_features = frame.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = [
            c for c in feature_cols if c not in numeric_features
        ]
        
        constants = [
            c for c in feature_cols
            if frame[c].nunique(dropna=False) <= 1
        ]
        print(f"\n   Features identificadas:")
        print(f"      Numéricas ({len(numeric_features)}): {numeric_features[:5]}{'...' if len(numeric_features) > 5 else ''}")
        print(f"      Categóricas ({len(categorical_features)}): {categorical_features}")
        if constants:
            print(
                f"   Features constantes (nao informam o modelo): {constants}"
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
        
        print("   Pipeline criado.")
        
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
            f"\nBacktest temporal: treino {train_year} / teste {test_year}"
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

        print("   Divisao concluida:")
        print(f"      Treino: {len(self.X_train):,} amostras")
        print(f"      Teste:  {len(self.X_test):,} amostras")

        train_dist = self.y_train.value_counts(normalize=True)
        test_dist = self.y_test.value_counts(normalize=True)
        print("\n   Distribuicao do target:")
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
        print("INICIANDO PREPARACAO DE DADOS")
        print("=" * 80)
        
        (self
         .load_data()
         .create_target(method=target_method, threshold=target_threshold)
         .remove_leakage_features()
         .create_derived_features()
         .split_data()
         .drop_unusable_train_features()
         .prepare_features())
        
        print("\n" + "=" * 80)
        print("PREPARACAO DE DADOS CONCLUIDA")
        print("=" * 80)
        
        return self
