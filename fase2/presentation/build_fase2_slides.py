#!/usr/bin/env python3
"""Gera presentation/Executive_presentation.pdf — slides da Fase 2 (pipeline)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "Executive_presentation.pdf"
FIGSIZE = (13.33, 7.5)
GITHUB = "https://github.com/stvinicius/tech_challenge_fase3"

NAVY = "#0F2744"
TEAL = "#1F6F8B"
PAPER = "#F6F3EE"
INK = "#1C1C1C"
MUTED = "#5A6470"
WHITE = "#FFFFFF"


def _chrome(fig, page: int, n_pages: int) -> None:
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0.935), 1, 0.065, transform=ax.transAxes, color=NAVY, zorder=0))
    ax.add_patch(Rectangle((0, 0), 1, 0.055, transform=ax.transAxes, color=NAVY, zorder=0))
    fig.text(0.04, 0.967, "Fase 2  ·  Pipeline de dados  ·  Alfabetização no Brasil",
             color=WHITE, fontsize=10, va="center", transform=ax.transAxes)
    fig.text(0.04, 0.027, GITHUB, color=WHITE, fontsize=9, va="center",
             transform=ax.transAxes)
    fig.text(0.96, 0.027, f"{page} / {n_pages}", color=WHITE, fontsize=9,
             va="center", ha="right", transform=ax.transAxes)


def _title(fig, title: str) -> None:
    fig.text(0.05, 0.86, title, fontsize=24, fontweight="bold", color=NAVY, va="top")
    fig.add_artist(Rectangle((0.05, 0.822), 0.10, 0.007, transform=fig.transFigure, color=TEAL))


def _bullets(fig, lines: list[str], y0: float = 0.74, step: float = 0.11, size: int = 15) -> None:
    y = y0
    for line in lines:
        fig.text(0.06, y, "●", fontsize=11, color=TEAL, va="top")
        fig.text(0.09, y, line, fontsize=size, color=INK, va="top", linespacing=1.35)
        y -= step


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_pages = 7
    with PdfPages(OUT) as pdf:
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 1, n_pages)
        fig.text(0.08, 0.72, "Apresentação executiva — Fase 2", fontsize=13, color=TEAL, fontweight="bold")
        fig.text(
            0.08, 0.48,
            "Como os dados de alfabetização\nchegam limpos até o analista",
            fontsize=30, fontweight="bold", color=NAVY, va="center", linespacing=1.22,
        )
        fig.text(0.08, 0.22, "Vinicius Santos  ·  FIAP Pós Tech  ·  Bronze / Silver / Gold na AWS",
                 fontsize=14, color=MUTED)
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 2, n_pages)
        _title(fig, "O problema de dados, não o de modelo")
        _bullets(fig, [
            "INEP e Compromisso Criança Alfabetizada publicam metas e taxas\npor município e por estado — em arquivos separados.",
            "Sem um lake, cada analista junta as tabelas no notebook e o número muda.",
            "A Fase 2 entrega uma tabela única: município + ano, já conferida.",
            "A Fase 3 (modelo) só começa depois desta tabela existir.",
        ], step=0.13)
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 3, n_pages)
        _title(fig, "Três camadas, dois caminhos")
        _bullets(fig, [
            "Bronze: o CSV como veio da Base dos Dados (só o nome da coluna padronizado).",
            "Silver: rede municipal, chaves IBGE, metas nacional/UF/município e o indicador\noficial da UF — uma linha por cidade e ano.",
            "Gold: três tabelas prontas para o Athena (indicador, meta vs resultado, série).",
            "Batch lê os CSVs. Streaming (Kinesis) é demonstração: o INEP não publica\nem tempo real.",
        ], step=0.13)
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 4, n_pages)
        _title(fig, "Qualidade antes de gravar o Silver")
        _bullets(fig, [
            "Cinco checagens: nulo, chave única, taxa entre 0 e 100, UF válida,\nmunicípio existente no diretório IBGE.",
            "Se alguma falhar, o Silver não é escrito. O relatório JSON/HTML fica\ncomo rastro do porquê.",
            "Isso evita que um join torto vire “dado oficial” na camada analítica.",
        ], step=0.14)
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 5, n_pages)
        _title(fig, "Dá para testar sem conta AWS")
        _bullets(fig, [
            "python pipelines/orchestrator.py --dry-run",
            "O ingest grava Bronze em disco. O Silver lê esse Bronze. O Gold lê o Silver.",
            "Nenhum bucket é tocado. Os CSVs de origem estão versionados em raw_downloads/.",
            "A Fase 3 consome esse Silver local (colunas traduzidas para português).",
        ], step=0.13)
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 6, n_pages)
        _title(fig, "Custo: nada ligado o mês inteiro")
        _bullets(fig, [
            "S3 + Parquet + Athena (paga o que lê). Sem cluster Spark/Redshift.",
            "Kinesis só existe durante a demo (minutos), depois o script apaga o stream.",
            "Pandas cabe na memória: são ~5.500 municípios × dois anos, não bilhões de linhas.",
        ], step=0.14)
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 7, n_pages)
        _title(fig, "O que entregar para a equipe")
        _bullets(fig, [
            "Tabela Silver com município, ano, taxa, metas e indicador oficial da UF.",
            "Três tabelas Gold no Athena, com partição por ano e estado.",
            "Código e testes no GitHub: " + GITHUB,
            "Modelo (Fase 3): não usar esta tabela para colar a taxa do próprio ano.",
        ], step=0.13)
        pdf.savefig(fig)
        plt.close(fig)

    print(OUT)


if __name__ == "__main__":
    main()
