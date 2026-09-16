# Tech Challenge Fase 3 — Classificação municipal de alfabetização

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Scikit-learn](https://img.shields.io/badge/Scikit--learn-1.7.2-orange.svg)
![Status](https://img.shields.io/badge/Status-Modelo%20honesto%20fraco-yellow.svg)

Continuação da [Fase 2](../fase2/README.md) (pipeline Bronze / Silver / Gold). Aqui o Silver vira um **modelo supervisionado**. A unidade **não é o aluno**: cada linha é **município + ano** (rede municipal). O corte SAEB de **743 pontos** não se aplica a esta tabela — a taxa já veio em **0 a 100%**.

---

## Objetivo

Classificar se o município **atingiu a meta municipal de alfabetização de 2024**:

`target = 1` se `taxa_alfabetizacao >= meta_municipio_alfabetizacao_2024`

O modelo **não** usa a taxa do próprio ano (isso seria copiar o gabarito). Depois de remover leakage, as features honestas são sobretudo **geografia e metas de UF / participação**.

---



## Resultados reais (não inventados)

Seleção **só no treino 2023**, métrica **F1**, `GroupKFold` por município. Prova única em **2024**.


|                                         | CV F1 (treino 2023) | Teste 2024 F1 | Acerto equilibrado | ROC-AUC |
| --------------------------------------- | ------------------- | ------------- | ------------------ | ------- |
| **LogisticRegression C=0.1** (vencedor) | ~0,49               | 0,45          | 0,51               | 0,57    |
| Dummy maioria no treino (sempre 0)      | 0,00                | —             | 0,50               | —       |
| Dummy “sempre 1” no teste 2024          | —                   | ~0,70         | —                  | —       |


No teste a acurácia fica ~50% e o F1 perde para um chute “todo mundo na meta”, porque a classe 1 sobe de **~18% em 2023** para **~53% em 2024** (a mesma barra de meta, taxa média um pouco maior). O modelo é **honesto e fraco**: geografia não antecipa quem cruza a meta no ano seguinte.

Arquivos: `models/best_model.pkl`, `models/model_comparison_results.csv`, `reports/classification_report.txt`.

---



## Protocolo

1. **Backtest temporal:** treino = 2023, teste = 2024. Sem `train_test_split` 80/20 aleatório.
2. **CV + GridSearch só no treino**, com `GroupKFold` por `id_municipio`.
3. **F1** escolhe o modelo (classe 1 rara no treino). Acurácia sozinha mente.
4. O teste 2024 entra **uma vez**, no notebook 04. O notebook 03 **não** calcula métricas de 2024.

Não dá para “testar os outros algoritmos no teste para ver se melhoram”: isso vira escolha no gabarito.

---



## Dados e schema Silver

`data/` está no `.gitignore`. Dois layouts existem neste repositório:


|         | Pipeline Fase 2                         | Notebooks 01–05                       |
| ------- | --------------------------------------- | ------------------------------------- |
| Pasta   | `literacy_indicator` ou `output/silver` | `data/silver/indicador_alfabetizacao` |
| Colunas | `literacy_rate`, `municipality_id`      | `taxa_alfabetizacao`, `id_municipio`  |
| Hive    | `year=` / `state_code=`                 | `ano=` / `sigla_uf=`                  |


A ponte:

```bash
# Na pasta fase2:
python pipelines/batch/process_silver.py --dry-run   # grava fase2/output/silver
# Na pasta fase3:
python scripts/export_silver_fase3.py
# ou: bash scripts/prepare_fase3.sh
```

Os notebooks e o `DataPreparator` **aceitam os dois**: `src/preprocessing/silver_schema.py` traduz inglês → português na leitura.

---



## Como reproduzir

```bash
cd fase3
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook
```

Ordem:

1. `notebooks/01_exploratory_analysis.ipynb` — EDA municipal, leakage visível
2. `notebooks/02_feature_engineering.ipynb` — target meta 2024, drop leakage, split 2023/2024
3. `notebooks/03_modeling.ipynb` — Dummy, LR, DT, RF, GB; GridSearch no treino
4. `notebooks/04_evaluation_interpretation.ipynb` — teste 2024, coeficientes, erros por região
5. `notebooks/05_lag1_regression.ipynb` — taxa_2023 → taxa_2024, depois classificar a taxa prevista contra a meta

Testes e Silver local:

```bash
pytest -q
bash scripts/prepare_fase3.sh   # exporta output/silver → data/silver/indicador_alfabetizacao
```

Slides executivos (linguagem não técnica, stakeholders): `presentation/Fase3_executive.pdf` (`python presentation/build_fase3_slides.py`). Roteiro: `presentation/SPEAKER_NOTES.md`. **Vídeo (~5 min):** [https://youtu.be/H-mDgqTfOLI](https://youtu.be/H-mDgqTfOLI). Repositório: [https://github.com/stvinicius/tech_challenge_fase3](https://github.com/stvinicius/tech_challenge_fase3)

Os notebooks 01, 03 e 04 **não dependem** de `data/processed` ter sido gravado: se a pasta faltar, `load_or_prepare_split` refaz o backtest a partir do Silver. A lista de colunas do modelo é `HONEST_FEATURE_COLUMNS` em `src/preprocessing/data_preparation.py`.

Usar o `.pkl` depois (`scikit-learn==1.7.2` e NumPy 1.x, pins de `requirements-test.txt`; ver `models/sklearn_version.txt` e `[MODEL_CARD.md](MODEL_CARD.md)`):

```python
import joblib
model = joblib.load("models/best_model.pkl")
# X precisa das mesmas colunas do treino (notebook 02), já sem taxa/meta municipal.
```

---



## Estrutura (Fase 3)

```
notebooks/01–05_*.ipynb
src/preprocessing/   DataPreparator + silver_schema
src/modeling/        ModelTrainer (GroupKFold, F1) + lag1
src/evaluation/      métricas e gráficos do teste
src/visualization/   EDA
tests/               pytest
scripts/prepare_fase3.sh
scripts/export_silver_fase3.py
models/  reports/  requirements.txt
```

---



## O que este projeto ensina (e o que não entrega)

- Unidade errada (aluno vs município) muda o problema inteiro.
- Leakage: `taxa_alfabetizacao`, `media_portugues` (r≈0,93), trajetória de meta municipal (r≈0,96–0,98).
- Split temporal vs 80/20: o município não pode aparecer nos dois lados.
- Um F1 de CV ~0,49 **não** vira política pública. O desenho seguinte é o **notebook 05**: regressão `taxa_2023 → taxa_2024`, depois comparar a taxa prevista com a meta já conhecida.

Pipeline AWS: [../fase2/README.md](../fase2/README.md). Testes: `pytest -q` nesta pasta. Slides: `presentation/Fase3_executive.pdf`. Vídeo: [https://youtu.be/H-mDgqTfOLI](https://youtu.be/H-mDgqTfOLI).