"""Painel municipal mínimo para testes (sem data/ no git)."""

from __future__ import annotations

import pandas as pd


def municipal_panel(n: int = 8) -> pd.DataFrame:
    rows = []
    for i in range(n):
        mun = 1100000 + i
        taxa_23 = 50.0 + i
        taxa_24 = taxa_23 + 4.0
        meta = 60.0
        for ano, taxa in ((2023, taxa_23), (2024, taxa_24)):
            rows.append(
                {
                    "id_municipio": mun,
                    "ano": ano,
                    "taxa_alfabetizacao": taxa,
                    "media_portugues": taxa + 5,
                    "meta_municipio_alfabetizacao_2024": meta,
                    "meta_municipio_alfabetizacao_2025": meta + 2,
                    "meta_municipio_taxa_base": taxa - 1,
                    "meta_uf_alfabetizacao_2024": 62.0,
                    "meta_municipio_percentual_participacao": 80.0 + i,
                    "nome_uf": "RO" if i % 2 == 0 else "BA",
                    "regiao": "Norte" if i % 2 == 0 else "Nordeste",
                    "nome_municipio": f"Mun {i}",
                    "fonte": "teste",
                    "proporcao_aluno_nivel_0": 0.1 if ano == 2024 else float("nan"),
                }
            )
    return pd.DataFrame(rows)
