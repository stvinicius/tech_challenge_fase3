# Tech Challenge — Alfabetização no Brasil

Repositório de entrega: [stvinicius/tech_challenge_fase3](https://github.com/stvinicius/tech_challenge_fase3).

Um repositório, **duas pastas** (Fase 2 de engenharia de dados + Fase 3 de modelagem):

| Pasta | Fase | O que é | Comece em |
|---|---|---|---|
| [`fase2/`](fase2/README.md) | 2 | Pipeline AWS (Bronze / Silver / Gold, batch + streaming) | `fase2/README.md` |
| [`fase3/`](fase3/README.md) | 3 | Modelo supervisionado (município-ano, meta 2024) | `fase3/README.md`, notebooks `01`–`05` |

A Fase 2 **não importa** código da Fase 3. A Fase 3 lê o Silver da Fase 2 (inglês, `year=`) e traduz para o schema dos notebooks (`taxa_alfabetizacao`, `ano=`).

```bash
git clone https://github.com/stvinicius/tech_challenge_fase3.git
cd tech_challenge_fase3

# Fase 2 (100% local, sem AWS)
cd fase2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python pipelines/orchestrator.py --dry-run   # Bronze, Silver e Gold em output/

# Fase 3
cd ../fase3
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash scripts/prepare_fase3.sh                # → data/silver/indicador_alfabetizacao
pytest -q
jupyter notebook notebooks/01_exploratory_analysis.ipynb
```

CI: [`.github/workflows/tests.yml`](.github/workflows/tests.yml) roda pytest em **cada pasta** (Fase 3 instala só `requirements-test.txt`).

- Slides executivos Fase 3: [`fase3/presentation/Fase3_executive.pdf`](fase3/presentation/Fase3_executive.pdf) — roteiro de vídeo (~5 min): [`fase3/presentation/SPEAKER_NOTES.md`](fase3/presentation/SPEAKER_NOTES.md)
- Slides Fase 2: [`fase2/presentation/Executive_presentation.pdf`](fase2/presentation/Executive_presentation.pdf)
- Model Card: [`fase3/MODEL_CARD.md`](fase3/MODEL_CARD.md)
- Fontes de dados: [`CREDITS.md`](CREDITS.md)
- Licença: [`LICENSE`](LICENSE) (MIT)

`data/` de cada fase está no `.gitignore`. CSVs de origem da Fase 2 **estão versionados** em `fase2/raw_downloads/`. Material de curso em `fase3/fiap/` **não entra no git**.
