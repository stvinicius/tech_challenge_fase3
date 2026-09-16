# Model Card — classificação municipal de alfabetização (Fase 3)

## Detalhes do modelo

- **Nome:** `fase3/models/best_model.pkl`
- **Tipo:** `sklearn.pipeline.Pipeline` com `ColumnTransformer` + `LogisticRegression` (`C=0.1`, `class_weight='balanced'`)
- **Versão do scikit-learn no treino:** `1.7.2` (`fase3/models/sklearn_version.txt`). O pickle só é estável nessa versão: `fase3/requirements-test.txt` pina `scikit-learn==1.7.2` e `numpy>=1.24,<2`
- **Data da entrega:** 2026-09-15
- **Repositório:** https://github.com/stvinicius/tech_challenge_fase3

## Uso pretendido

Classificar se o **município** (rede municipal, um ano) atingiu a **meta municipal de alfabetização de 2024**:

`target = 1` se `taxa_alfabetizacao >= meta_municipio_alfabetizacao_2024`

Uso acadêmico / diagnóstico. **Não** alocar recurso público só com este palpite.

## Fora de escopo

- Prever aluno alfabetizado (não há linha de estudante neste Silver).
- Usar o corte 743 da escala SAEB (a taxa já está em 0–100%).
- Usar a taxa ou a média de português do **próprio ano** como feature (leakage).

## Dados

Painel município × ano (2023 treino, 2024 teste único), rede municipal.
Fonte: INEP via Base dos Dados, Silver da Fase 2.

## Features de entrada (lista única)

Definidas em `src.preprocessing.data_preparation.HONEST_FEATURE_COLUMNS`:

- `nome_uf`, `regiao`, `codigo_regiao`
- `meta_municipio_percentual_participacao`
- `meta_uf_percentual_participacao`
- `meta_uf_alfabetizacao_2024`

## Métricas (teste 2024, uma vez)

| | Valor |
|---|---|
| F1 | ~0,45 |
| Acerto equilibrado | ~0,51 |
| ROC-AUC | ~0,57 |
| Dummy sempre-1 no 2024 (F1) | ~0,70 |

O modelo é **honesto e fraco**. Geografia não antecipa quem cruza a meta no ano seguinte.

## Protocolo

Treino 2023 / teste 2024. `GroupKFold` por `id_municipio`. Seleção por F1 só no treino.
O notebook 03 **não** abre o 2024; o notebook 04 avalia uma vez.

## Limitações

- Deslocamento de prevalência: classe 1 ~18% (2023) → ~53% (2024).
- OLS lag-1 (notebook 05) descreve o par 2023→2024; **não há 2025** neste Silver.
- Pickle sklearn/NumPy não é estável entre versões: instale `scikit-learn==1.7.2` e NumPy 1.x (`numpy>=1.24,<2`) pelo `requirements-test.txt` ou retreine o notebook 03.

## Ética

Um “99% de acerto” neste problema quase sempre é cola (taxa do próprio ano).
Não usar como semáforo de transferência de recurso.
