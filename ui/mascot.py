# ui/mascot.py
"""
Mascote pixel art numa janela transparente sempre-por-cima.

A janela (Toplevel) e a animação vivem na classe Mascot; as funções livres no
topo são a lógica testável sem abrir Tk (clique vs arrasto, balão, posição).
"""
import random
import tkinter as tk

from ui import sprites

POS_DEFAULT = "+40+40"
LIMIAR_ARRASTO = 5      # px: soltar abaixo disto é clique, acima é arrasto
MAX_BALAO = 120         # carateres do balão antes de truncar
ESCALA = 4              # px por célula: 16 células * 4 = 64 px
INTERVALO_MS = 150      # ms por frame de animação
PROB_EXTRA = 1 / 200    # hipótese de disparar um extra por tick de idle

_ESTADOS = set(sprites.FRAMES)


def foi_clique(dx: int, dy: int) -> bool:
    return abs(dx) < LIMIAR_ARRASTO and abs(dy) < LIMIAR_ARRASTO


def truncar_balao(texto: str) -> str:
    limpo = " ".join(str(texto).split())
    if len(limpo) <= MAX_BALAO:
        return limpo
    return limpo[:MAX_BALAO] + "…"


# Import de ui.app adiado para dentro das funções: ui.app importa este módulo
# no topo, e um import recíproco no topo daqui fechava o ciclo com ImportError.
def carregar_pos() -> str | None:
    from ui import app
    return app.carregar_ui_state().get("mascot_pos")


def guardar_pos(pos: str) -> None:
    from ui import app
    dados = app.carregar_ui_state()
    dados["mascot_pos"] = pos
    app.guardar_ui_state(dados)
