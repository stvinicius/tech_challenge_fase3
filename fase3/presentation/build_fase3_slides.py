#!/usr/bin/env python3
"""Gera presentation/Fase3_executive.pdf (matplotlib, sem ReportLab)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "Fase3_executive.pdf"
FIGSIZE = (13.33, 7.5)


def slide(fig, title: str, bullets: list[str]) -> None:
    ax = fig.add_axes([0.07, 0.08, 0.86, 0.82])
    ax.axis("off")
    ax.text(0, 1.02, title, fontsize=22, fontweight="bold", va="top", transform=ax.transAxes)
    y = 0.88
    for line in bullets:
        ax.text(0, y, line, fontsize=15, va="top", wrap=True, transform=ax.transAxes)
        y -= 0.12


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT) as pdf:
        fig = plt.figure(figsize=FIGSIZE)
        slide(
            fig,
            "Fase 3 — o município bateu a meta de 2024?",
            [
                "Não há aluno nesta tabela. Cada linha é município + ano (rede municipal).",
                "Target: taxa_alfabetizacao ≥ meta municipal de 2024. O corte SAEB 743 não se aplica.",
                "Protocolo: treino 2023, GroupKFold, F1; teste 2024 uma vez.",
                "Continuidade da pipeline Bronze/Silver/Gold da Fase 2.",
            ],
        )
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        slide(
            fig,
            "O classificador honesto empata com cara ou coroa",
            [
                "Logística C=0,1 (vencedora da CV): F1 0,45 · acerto equilibrado 0,51 · AUC 0,57.",
                "Dummy “sempre na meta” no teste 2024 tem F1 ~0,70 — a classe 1 virou 53%.",
                "Geografia e participação não antecipam quem cruza a meta no ano seguinte.",
                "Isso não é código quebrado: é o limite de classificar a meta sem a taxa do ano.",
            ],
        )
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        slide(
            fig,
            "O que a banca deve levar",
            [
                "Leakage medido (taxa base r≈1, português r≈0,93, trajetória de meta municipal).",
                "Sem split 80/20. Sem treinar no teste. Dummy no treino e no teste.",
                "Próximo desenho (notebook 05): taxa_2023 → taxa_2024, depois comparar com a meta.",
                "Clone: pytest; python scripts/prepare_fase3.sh se o Silver local existir.",
            ],
        )
        pdf.savefig(fig)
        plt.close(fig)

    print(OUT)


if __name__ == "__main__":
    main()
