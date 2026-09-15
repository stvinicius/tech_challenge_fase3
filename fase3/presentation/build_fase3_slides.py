#!/usr/bin/env python3
"""Gera presentation/Fase3_executive.pdf — slides para stakeholders (linguagem não técnica)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "Fase3_executive.pdf"
FIGSIZE = (13.33, 7.5)
GITHUB = "https://github.com/stvinicius/tech_challenge_fase3"

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


def _bullets(fig, lines: list[str], y0: float = 0.74, step: float = 0.11, size: int = 15) -> None:
    y = y0
    for line in lines:
        fig.text(0.06, y, "●", fontsize=11, color=TEAL, va="top")
        fig.text(0.09, y, line, fontsize=size, color=INK, va="top", linespacing=1.35)
        y -= step


def _kpi(ax, x, y, w, h, value: str, caption: str) -> None:
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=WHITE, edgecolor=TEAL, linewidth=1.3, transform=ax.transAxes,
    ))
    ax.text(x + w / 2, y + h * 0.62, value, ha="center", va="center",
            fontsize=28, fontweight="bold", color=NAVY, transform=ax.transAxes)
    ax.text(x + w / 2, y + h * 0.22, caption, ha="center", va="center",
            fontsize=11, color=MUTED, transform=ax.transAxes, linespacing=1.3)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_pages = 8

    with PdfPages(OUT) as pdf:
        # 1. Capa
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 1, n_pages)
        fig.text(0.08, 0.72, "Apresentação executiva", fontsize=13, color=TEAL, fontweight="bold")
        fig.text(
            0.08, 0.52,
            "Dá para saber, com antecedência,\nse o município vai bater a meta\nde alfabetização de 2024?",
            fontsize=30, fontweight="bold", color=NAVY, va="center", linespacing=1.22,
        )
        fig.add_artist(Rectangle((0.08, 0.34), 0.16, 0.008, transform=fig.transFigure, color=ACCENT))
        fig.text(
            0.08, 0.27,
            "Resposta curta: com o que o gestor já sabe no início do ano, não.\n"
            "Geografia e participação na prova não antecipam quem cruza a meta.",
            fontsize=14, color=MUTED, va="top", linespacing=1.45,
        )
        fig.text(0.08, 0.12, "Vinicius Santos", fontsize=13, color=INK)
        pdf.savefig(fig)
        plt.close(fig)

        # 2. Contexto
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 2, n_pages)
        _title(fig, "O compromisso é com a criança. O número é do município.")
        _bullets(fig, [
            "O Brasil tem uma meta nacional: toda criança alfabetizada\naté o fim do 2º ano, até 2030.",
            "Cada município recebeu uma meta própria para 2024 — uma barra\nfixa, publicada com antecedência.",
            "Olhamos 5.232 municípios, nos anos 2023 e 2024,\nna rede municipal (não o aluno, não a escola).",
            "A taxa já veio em porcentagem (0 a 100%). Não usamos\no corte de 743 pontos da prova do aluno.",
        ], step=0.13, size=16)
        pdf.savefig(fig)
        plt.close(fig)

        # 3. Pergunta
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 3, n_pages)
        _title(fig, "A pergunta que o gestor faz em janeiro")
        _bullets(fig, [
            "“Quais municípios vão precisar de apoio para bater a meta deste ano?”",
            "Essa decisão precisa ser tomada antes de sair o resultado de 2024.",
            "Por isso recusamos olhar a taxa do próprio ano. Seria copiar\no gabarito da prova que ainda não aconteceu.",
            "O que restou para o palpite: região, estado, quanto da turma\nfez a prova, e a meta do estado — não a do município.",
        ], step=0.13, size=16)
        pdf.savefig(fig)
        plt.close(fig)

        # 4. Como medimos
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 4, n_pages)
        _title(fig, "Como testamos sem trapacear")
        ax = fig.add_axes([0.06, 0.18, 0.88, 0.56])
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 4)
        ax.axis("off")
        steps = [
            (0.3, "1. Estudar 2023", "O modelo só vê o passado.\nAprende com o simulado."),
            (3.5, "2. Escolher o palpite", "Comparamos vários métodos\nsó com 2023. 2024 está lacrado."),
            (6.7, "3. Prova de 2024", "Uma vez. Sem voltar atrás\npara escolher o método “que deu sorte”."),
        ]
        for x, title, body in steps:
            ax.add_patch(FancyBboxPatch(
                (x, 0.7), 2.9, 2.6, boxstyle="round,pad=0.04,rounding_size=0.12",
                facecolor=WHITE, edgecolor=TEAL, linewidth=1.4,
            ))
            ax.text(x + 1.45, 2.55, title, ha="center", va="center", fontsize=15,
                    fontweight="bold", color=NAVY)
            ax.text(x + 1.45, 1.55, body, ha="center", va="center", fontsize=12,
                    color=MUTED, linespacing=1.45)
            if x < 6:
                ax.annotate("", xy=(x + 3.25, 2.0), xytext=(x + 3.05, 2.0),
                            arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.5))
        fig.text(
            0.06, 0.12,
            "Analogia: ninguém escolhe o material de estudo olhando a prova do vestibular.",
            fontsize=13, color=MUTED,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 5. Resultado
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 5, n_pages)
        _title(fig, "O palpite honesto empata com cara ou coroa")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        _kpi(ax, 0.06, 0.38, 0.27, 0.32, "~50%", "acerto do modelo\nno ano de 2024")
        _kpi(ax, 0.365, 0.38, 0.27, 0.32, "53%", "dos municípios já estavam\nna meta em 2024")
        _kpi(ax, 0.67, 0.38, 0.27, 0.32, "Chute ganha", "dizer “todos na meta”\nacerta mais que o modelo")
        fig.text(
            0.06, 0.22,
            "Isso não é falha de software. Sem a taxa do ano, região e participação\n"
            "não dizem quem vai cruzar a barra. Um modelo “bonito” aqui seria suspeito.",
            fontsize=15, color=INK, va="top", linespacing=1.4,
        )
        pdf.savefig(fig)
        plt.close(fig)

        # 6. Por que
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 6, n_pages)
        _title(fig, "A barra ficou parada. O Brasil andou um pouco.")
        _bullets(fig, [
            "A meta de 2024 é um número de planejamento — não sobe no meio do ano.",
            "A taxa de alfabetização subiu o suficiente para muita gente cruzar\na mesma barra: de 18 em cada 100 municípios (2023) para 53 em 100 (2024).",
            "O palpite aprendeu um mundo em que “na meta” era exceção\ne foi cobrado num mundo em que “na meta” já era maioria.",
            "Norte e Nordeste seguem abaixo; Sul, Sudeste e Centro-Oeste, acima.\nIsso descreve desigualdade. Não antecipa quem cruza a meta no ano seguinte.",
        ], step=0.13, size=15)
        pdf.savefig(fig)
        plt.close(fig)

        # 7. O que funciona
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 7, n_pages)
        _title(fig, "O que o gestor já tem em janeiro funciona melhor")
        _bullets(fig, [
            "A taxa de 2023 já está na mesa quando 2024 começa.\nUsá-la não é cola: é informação do ano anterior.",
            "Copiar 2023 para estimar 2024 erra cerca de 12 pontos na taxa.\nUm ajuste simples cai para 11,7 pontos e explica 40% da variação.",
            "Não há 2025 neste estudo: o ajuste descreve 2023→2024.\nNão é previsão do ano que vem.",
            "Comparar essa taxa prevista com a meta já publicada acerta mais\ndo que classificar a meta às cegas — mas ainda perde de um chute “todo mundo na meta”.",
        ], step=0.13, size=15)
        pdf.savefig(fig)
        plt.close(fig)

        # 8. Recomendação
        fig = plt.figure(figsize=FIGSIZE)
        _chrome(fig, 8, n_pages)
        _title(fig, "O que recomendamos")
        _bullets(fig, [
            "Não alocar recurso com um “semáforo” baseado só em região e participação.\nO risco é parecer científico e ser cara ou coroa.",
            "Usar a taxa do ano anterior + a meta já publicada para priorizar apoio.\nÉ o que o gestor já tem no primeiro dia letivo.",
            "Tratar um modelo que “acerta 99%” com desconfiança:\nquase sempre ele está lendo o resultado do próprio ano.",
            "Detalhe técnico e código aberto para a equipe:\n" + GITHUB,
        ], step=0.13, size=15)
        pdf.savefig(fig)
        plt.close(fig)

    print(OUT)


if __name__ == "__main__":
    main()
