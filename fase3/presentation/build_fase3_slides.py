#!/usr/bin/env python3
"""Gera presentation/Fase3_executive.pdf — linguagem clara para público não técnico."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "Fase3_executive.pdf"
FIGSIZE = (13.33, 7.5)
GITHUB = "https://github.com/stvinicius/tech_challenge_fase3"
VIDEO = "https://youtu.be/H-mDgqTfOLI"

NAVY = "#0F2744"
TEAL = "#1F6F8B"
ACCENT = "#C45C26"
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
    ax.text(
        0.04, 0.967,
        "Apresentação executiva  ·  Tech Challenge Fase 3  ·  Alfabetização no Brasil",
        color=WHITE, fontsize=10, va="center", transform=ax.transAxes,
    )
    ax.text(0.04, 0.027, GITHUB, color=WHITE, fontsize=9, va="center",
            transform=ax.transAxes, url=GITHUB)
    ax.text(0.96, 0.027, f"{page} / {n_pages}", color=WHITE, fontsize=9,
            va="center", ha="right", transform=ax.transAxes)


def _title(fig, title: str) -> None:
    fig.text(0.05, 0.86, title, fontsize=24, fontweight="bold", color=NAVY, va="top")
    fig.add_artist(Rectangle((0.05, 0.822), 0.10, 0.007, transform=fig.transFigure, color=TEAL))


def _bullets(fig, lines: list[str], y0: float = 0.74, step: float = 0.11, size: int = 16) -> None:
    y = y0
    for line in lines:
        fig.text(0.06, y, "●", fontsize=11, color=TEAL, va="top")
        fig.text(0.09, y, line, fontsize=size, color=INK, va="top", linespacing=1.35)
        y -= step


def _kpi(ax, x, y, w, h, header: str, value: str, caption: str, edge=TEAL) -> None:
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=WHITE, edgecolor=edge, linewidth=1.5, transform=ax.transAxes,
    ))
    ax.text(x + w / 2, y + h * 0.86, header, ha="center", va="top",
            fontsize=11, fontweight="bold", color=TEAL, transform=ax.transAxes)
    ax.text(x + w / 2, y + h * 0.52, value, ha="center", va="center",
            fontsize=36, fontweight="bold", color=NAVY, transform=ax.transAxes)
    ax.text(x + w / 2, y + h * 0.16, caption, ha="center", va="center",
            fontsize=12, color=MUTED, transform=ax.transAxes, linespacing=1.3)


def _box(ax, x, y, w, h, title: str, body: str) -> None:
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=WHITE, edgecolor=TEAL, linewidth=1.3, transform=ax.transAxes,
    ))
    ax.text(x + 0.04, y + h - 0.045, title, fontsize=14, fontweight="bold",
            color=NAVY, va="top", transform=ax.transAxes)
    ax.text(x + 0.04, y + h - 0.12, body, fontsize=13, color=INK, va="top",
            transform=ax.transAxes, linespacing=1.45)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_pages = 8

    with PdfPages(OUT) as pdf:
        # 1. Capa
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 1, n_pages)
        fig.text(0.08, 0.74, "FIAP Pós Tech  ·  Vinicius Santos", fontsize=13,
                 color=TEAL, fontweight="bold")
        fig.text(
            0.08, 0.54,
            "O modelo antecipa quem bate\na meta de alfabetização em 2024?",
            fontsize=28, fontweight="bold", color=NAVY, va="center", linespacing=1.22,
        )
        fig.add_artist(Rectangle((0.08, 0.38), 0.16, 0.008, transform=fig.transFigure, color=ACCENT))
        fig.text(
            0.08, 0.30,
            "Não. Ele tira 51 — empata com cara ou coroa — e 45 na prova.\n"
            "Um chute “todas as cidades bateram” tira 70 e ganha.\n"
            "Não é erro de software. O mapa não antecipa a meta.",
            fontsize=16, color=INK, va="top", linespacing=1.45,
        )
        fig.text(
            0.08, 0.155,
            "Fonte: INEP / Base dos Dados  ·  5.232 municípios  ·  rede municipal, 2023 e 2024",
            fontsize=12, color=MUTED,
        )
        fig.text(
            0.08, 0.115,
            "Vídeo da apresentação:  " + VIDEO,
            fontsize=13, color=TEAL, fontweight="bold", url=VIDEO,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 2. O que o modelo faz
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 2, n_pages)
        _title(fig, "O que o modelo tenta fazer")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        _box(
            ax, 0.06, 0.42, 0.42, 0.32,
            "A pergunta (sim ou não)",
            "Este município bate a meta\nde alfabetização de 2024?\n\nPergunta de janeiro.\nO resultado do ano ainda não saiu.",
        )
        _box(
            ax, 0.52, 0.42, 0.42, 0.32,
            "O que ele pode olhar",
            "Só o mapa: região, estado\ne quantas crianças fizeram a prova.\n\nNão olha a taxa do ano.\nOlhar a taxa seria colar.",
        )
        fig.text(
            0.06, 0.28,
            "São 5.232 municípios, só a rede municipal. Não é o aluno, não é a escola.\n"
            "Não cruzamos renda. A taxa já veio de 0 a 100%. O corte 743 da prova do aluno não entra.",
            fontsize=15, color=INK, va="top", linespacing=1.4,
        )
        fig.text(
            0.06, 0.12,
            "Estudou 2023. Foi cobrado em 2024, uma vez, sem colar.",
            fontsize=13, color=MUTED,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 3. Os três números
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 3, n_pages)
        _title(fig, "Três números do modelo. Nenhum é a meta da cidade.")
        fig.text(
            0.05, 0.78,
            "Leia como um boletim de 0 a 100. Quanto maior, melhor o palpite — não a alfabetização.",
            fontsize=14, color=MUTED, va="top",
        )
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        _kpi(
            ax, 0.05, 0.36, 0.28, 0.36,
            "CARA OU COROA",
            "51",
            "o modelo empata\ncom uma moeda",
        )
        _kpi(
            ax, 0.36, 0.36, 0.28, 0.36,
            "NOTA DO MODELO",
            "45",
            "o sim ou não\nna prova de 2024",
        )
        _kpi(
            ax, 0.67, 0.36, 0.28, 0.36,
            "UM CHUTE",
            "70",
            "“todas bateram”\nganha do modelo",
            edge=ACCENT,
        )
        ax.add_patch(FancyBboxPatch(
            (0.05, 0.10), 0.90, 0.20, boxstyle="round,pad=0.015,rounding_size=0.06",
            facecolor=WHITE, edgecolor=ACCENT, linewidth=1.6, transform=ax.transAxes,
        ))
        ax.text(
            0.50, 0.24,
            "A meta da cidade é a taxa de alfabetização. Não é 70.",
            ha="center", va="center", fontsize=16, fontweight="bold", color=NAVY,
            transform=ax.transAxes,
        )
        ax.text(
            0.50, 0.155,
            "51, 45 e 70 medem só o palpite. 70 é a nota de quem chuta, não a barra da política.",
            ha="center", va="center", fontsize=14, color=INK, transform=ax.transAxes,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 4. Por que 51 = moeda
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 4, n_pages)
        _title(fig, "Por que 51 não é melhor que cara ou coroa")
        _bullets(fig, [
            "Existem duas filas: municípios que bateram a meta e municípios que não bateram.",
            "Uma moeda, jogada para cada cidade, acerta cerca de metade de cada fila.\nIsso dá 50.",
            "O modelo acertou 51. É o mesmo que a moeda.\nEle não separa quem vai passar de quem não vai.",
            "Se o número fosse 80 ou 90, aí sim o mapa estaria antecipando a meta.\n51 quer dizer: o mapa não ajuda.",
        ], step=0.13, size=16)
        pdf.savefig(fig)
        plt.close(fig)

        # 5. 45 vs 70
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 5, n_pages)
        _title(fig, "Por que 45 perde para 70")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        _box(
            ax, 0.06, 0.38, 0.42, 0.36,
            "45 — o modelo",
            "É a nota do sim ou não\nna prova de 2024.\n\nNum boletim de 0 a 100,\n45 é fraco.",
        )
        _box(
            ax, 0.52, 0.38, 0.42, 0.36,
            "70 — o chute",
            "Ninguém olha o mapa.\nSó fala: “todas bateram”.\n\nEm 2024, 53% já estavam\nna meta. O chute acerta mais.",
        )
        fig.text(
            0.06, 0.24,
            "Ganha quem tem a nota maior. O chute ganha. O modelo perde.\n"
            "70 não é a meta de alfabetização. É a nota de um palpite burro que, neste ano, funcionou.",
            fontsize=15, color=INK, va="top", linespacing=1.4,
        )
        fig.text(
            0.06, 0.12,
            "45 também não é “acertou 45% das cidades”. É a nota do palpite, não um percentual da meta.",
            fontsize=13, color=MUTED,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 6. Tem algo errado?
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 6, n_pages)
        _title(fig, "Tem algo errado? Não.")
        _bullets(fig, [
            "O cálculo está certo. O modelo estudou 2023 e foi cobrado em 2024, uma vez.",
            "Ele só viu região, estado e participação na prova.\nCom isso, não dá para saber quem cruza a meta no ano seguinte.",
            "O resultado honesto é este: 51 (moeda), 45 (modelo), 70 (chute).\nNão é falha de programa. É o que o mapa consegue antecipar — quase nada.",
            "O sinal de problema seria um modelo que “acerta 99%”.\nQuase sempre ele colou: leu a taxa do próprio ano.",
        ], step=0.13, size=16)
        pdf.savefig(fig)
        plt.close(fig)

        # 7. Por que aconteceu
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 7, n_pages)
        _title(fig, "Por que o chute ganhou neste ano")
        axb = fig.add_axes([0.07, 0.16, 0.34, 0.58])
        axb.set_facecolor(PAPER)
        bars = axb.bar(
            ["2023", "2024"], [18, 53],
            color=[TEAL, ACCENT], width=0.55, zorder=2,
        )
        axb.set_ylim(0, 70)
        axb.set_ylabel("Municípios na meta (%)", color=MUTED, fontsize=11)
        axb.tick_params(colors=NAVY, labelsize=13)
        for spine in axb.spines.values():
            spine.set_color("#D9D3C9")
        axb.spines["top"].set_visible(False)
        axb.spines["right"].set_visible(False)
        axb.yaxis.grid(True, color="#E6E1D8", zorder=0)
        axb.set_axisbelow(True)
        for bar, val in zip(bars, (18, 53)):
            axb.text(
                bar.get_x() + bar.get_width() / 2, val + 2, f"{val}%",
                ha="center", va="bottom", fontsize=14, fontweight="bold", color=NAVY,
            )
        fig.text(0.48, 0.70, "A meta de 2024 não mudou.\nO Brasil andou um pouco.",
                 fontsize=16, color=INK, va="top", linespacing=1.4)
        fig.text(0.48, 0.50, "Em 2023, 18 em 100 municípios\nestavam na meta. Era exceção.",
                 fontsize=16, color=INK, va="top", linespacing=1.4)
        fig.text(0.48, 0.30, "Em 2024, 53 em 100. Já era maioria.\nChutar “sim” passou a funcionar.",
                 fontsize=16, color=INK, va="top", linespacing=1.4)
        fig.text(
            0.48, 0.12,
            "Norte e Nordeste seguem atrás; Sul, Sudeste e Centro-Oeste, à frente.\nIsso descreve desigualdade. Não antecipa o ano seguinte.",
            fontsize=13, color=MUTED, va="top", linespacing=1.35,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 8. O que fazer
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 8, n_pages)
        _title(fig, "O que fazer com isso")
        _bullets(fig, [
            "Não use o modelo como semáforo para soltar recurso.\n51 é cara ou coroa. 45 perde de um chute.",
            "Na segunda-feira: faça uma fila. Quem estava mais longe da meta\nno ano passado recebe apoio primeiro. Isso não é colar.",
            "Desconfie de modelo que “acerta 99%”.\nO resultado honesto, aqui, é parecer fraco.",
            "Código e detalhe técnico:\n" + GITHUB,
        ], step=0.13, size=16)
        fig.text(
            0.09, 0.20,
            "Vídeo:  " + VIDEO,
            fontsize=16, color=TEAL, url=VIDEO,
        )
        pdf.savefig(fig)
        plt.close(fig)

    print(OUT)


if __name__ == "__main__":
    main()
