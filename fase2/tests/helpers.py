"""CSV mínimo para exercitar ingest + silver + gold em --dry-run (sem AWS)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TARGET_YEARS = tuple(range(2024, 2031))


def _meta_cols(base: float) -> dict[str, float]:
    return {f"meta_alfabetizacao_{year}": base + (year - 2024) for year in TARGET_YEARS}


def write_min_csvs(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {"sigla": "RO", "nome": "Rondonia", "regiao": "Norte"},
            {"sigla": "BA", "nome": "Bahia", "regiao": "Nordeste"},
        ]
    ).to_csv(input_dir / "sigla_uf.csv", index=False)

    pd.DataFrame(
        [
            {
                "id_municipio": "1100015",
                "sigla_uf": "RO",
                "nome": "Alta Floresta",
                "nome_uf": "Rondonia",
                "nome_regiao": "Norte",
            },
            {
                "id_municipio": "2900108",
                "sigla_uf": "BA",
                "nome": "Abaíra",
                "nome_uf": "Bahia",
                "nome_regiao": "Nordeste",
            },
        ]
    ).to_csv(input_dir / "municipios.csv", index=False)

    national_rows = []
    for ano, taxa in ((2023, 56.0), (2024, 58.0)):
        national_rows.append(
            {
                "ano": ano,
                "taxa_alfabetizacao": taxa,
                "percentual_participacao": 90.0,
                **_meta_cols(60.0),
            }
        )
    pd.DataFrame(national_rows).to_csv(input_dir / "metas_nacionais.csv", index=False)

    state_rows = []
    for uf, base in (("RO", 61.0), ("BA", 55.0)):
        for ano in (2023, 2024):
            state_rows.append(
                {
                    "sigla_uf": uf,
                    "ano": ano,
                    "taxa_alfabetizacao": base,
                    "percentual_participacao": 88.0,
                    **_meta_cols(base),
                }
            )
    pd.DataFrame(state_rows).to_csv(input_dir / "metas_uf.csv", index=False)

    mun_rows = []
    for mun, taxa in (("1100015", 62.0), ("2900108", 48.0)):
        for ano in (2023, 2024):
            mun_rows.append(
                {
                    "id_municipio": mun,
                    "ano": ano,
                    "taxa_alfabetizacao": taxa,
                    "percentual_participacao": 80.0,
                    "nivel_alfabetizacao": "2",
                    **_meta_cols(taxa + 2),
                }
            )
    pd.DataFrame(mun_rows).to_csv(input_dir / "metas_municipio.csv", index=False)

    ind_rows = []
    for mun, taxa23, taxa24 in (("1100015", 62.0, 66.0), ("2900108", 48.0, 52.0)):
        for ano, taxa in ((2023, taxa23), (2024, taxa24)):
            for rede in ("3", "2"):
                row = {
                    "ano": ano,
                    "id_municipio": mun,
                    "serie": "2",
                    "rede": rede,
                    "taxa_alfabetizacao": taxa if rede == "3" else taxa - 5,
                    "media_portugues": taxa + 700,
                    **{f"proporcao_aluno_nivel_{i}": (0.1 if ano == 2024 else "") for i in range(9)},
                }
                ind_rows.append(row)
    pd.DataFrame(ind_rows).to_csv(input_dir / "indicador_crianca_alfabetizada.csv", index=False)

    uf_rows = []
    for uf, taxa23, taxa24 in (("RO", 61.0, 64.0), ("BA", 50.0, 54.0)):
        for ano, taxa in ((2023, taxa23), (2024, taxa24)):
            uf_rows.append(
                {
                    "ano": ano,
                    "sigla_uf": uf,
                    "serie": "2",
                    "rede": "3",
                    "taxa_alfabetizacao": taxa,
                    "media_portugues": taxa + 700,
                    **{f"proporcao_aluno_nivel_{i}": "" for i in range(9)},
                }
            )
    pd.DataFrame(uf_rows).to_csv(input_dir / "indicador_crianca_alfabetizada_uf.csv", index=False)
