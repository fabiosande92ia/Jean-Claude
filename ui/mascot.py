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


class Mascot:
    """
    Janela da mascote: Toplevel sem moldura, sempre por cima, com a cor-chave
    transparente (e click-through) no Windows. Anima no loop do Tk via after()
    — nunca toca em threads nem no StateBus; recebe tudo já na thread do Tk.
    """

    def __init__(self, root, on_click):
        self._on_click = on_click
        self._estado = "idle"
        self._frame_idx = 0
        self._extra = None          # frames de um extra a decorrer, ou None
        self._tick_id = None
        self._balao_id = None
        self._balao_win = None
        self._drag_orig = None

        lado = sprites.LARGURA * ESCALA
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        try:
            self.win.wm_attributes("-transparentcolor", sprites.COR_CHAVE)
        except tk.TclError:
            # Plataforma/Tk sem cor-chave: sem transparência a mascote seria um
            # quadrado magenta no ecrã. Melhor não existir — quem cria decide.
            self.win.destroy()
            raise

        self.canvas = tk.Canvas(
            self.win, width=lado, height=lado,
            bg=sprites.COR_CHAVE, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        self.win.geometry(f"{lado}x{lado}{carregar_pos() or POS_DEFAULT}")

        self.canvas.bind("<Button-1>", self._pressiona)
        self.canvas.bind("<B1-Motion>", self._arrasta)
        self.canvas.bind("<ButtonRelease-1>", self._solta)

        self._tick()

    # --- API pública (chamada pelo App, na thread do Tk) ----------------------
    def set_state(self, estado):
        estado = estado if estado in _ESTADOS else "idle"
        if estado == self._estado:
            return   # repetido: não reiniciar o frame, senão a animação congela
        self._estado = estado
        self._frame_idx = 0
        self._extra = None

    def balao(self, texto):
        if self._balao_id is not None:
            self.win.after_cancel(self._balao_id)
        self._mostra_balao(truncar_balao(texto))
        self._balao_id = self.win.after(6000, self._esconde_balao)

    def destroy(self):
        for aid in (self._tick_id, self._balao_id):
            if aid is not None:
                try:
                    self.win.after_cancel(aid)
                except tk.TclError:
                    pass
        self._esconde_balao()
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # --- animação --------------------------------------------------------------
    def _frames_atuais(self):
        if self._extra is not None:
            return self._extra
        return sprites.FRAMES.get(self._estado, sprites.FRAMES["idle"])

    def _proximo_frame(self):
        frames = self._frames_atuais()
        frame = frames[self._frame_idx % len(frames)]
        self._frame_idx = (self._frame_idx + 1) % len(frames)
        return frame

    def _tick(self):
        if self._estado == "idle" and self._extra is None:
            if random.random() < PROB_EXTRA:
                self._extra = sprites.EXTRAS[random.choice(list(sprites.EXTRAS))]
                self._frame_idx = 0
        self._desenha(self._proximo_frame())
        # o extra corre uma passagem: quando o índice dá a volta, acabou
        if self._extra is not None and self._frame_idx == 0:
            self._extra = None
        self._tick_id = self.win.after(INTERVALO_MS, self._tick)

    def _desenha(self, frame):
        self.canvas.delete("sprite")
        for y, linha in enumerate(frame):
            for x, ch in enumerate(linha):
                cor = sprites.PALETA.get(ch)
                if cor is None:
                    continue
                x0, y0 = x * ESCALA, y * ESCALA
                self.canvas.create_rectangle(
                    x0, y0, x0 + ESCALA, y0 + ESCALA,
                    fill=cor, width=0, tags="sprite",
                )

    # --- balão de fala -----------------------------------------------------------
    def _mostra_balao(self, texto):
        self._esconde_balao()
        self._balao_win = tk.Toplevel(self.win)
        self._balao_win.overrideredirect(True)
        self._balao_win.wm_attributes("-topmost", True)
        tk.Label(
            self._balao_win, text=texto, bg="#2b2d31", fg="#e4e6eb",
            font=("Segoe UI", 9), wraplength=200, justify="left",
            padx=8, pady=6,
        ).pack()
        # por cima da mascote; nunca acima do topo do ecrã
        self.win.update_idletasks()
        self._balao_win.update_idletasks()
        x = self.win.winfo_x()
        y = self.win.winfo_y() - self._balao_win.winfo_reqheight() - 4
        self._balao_win.geometry(f"+{x}+{max(0, y)}")

    def _esconde_balao(self):
        if self._balao_win is not None:
            try:
                self._balao_win.destroy()
            except tk.TclError:
                pass
            self._balao_win = None

    # --- arrasto / clique --------------------------------------------------------
    def _pressiona(self, ev):
        self._drag_orig = (ev.x_root, ev.y_root, self.win.winfo_x(), self.win.winfo_y())

    def _arrasta(self, ev):
        if self._drag_orig is None:
            return
        ox, oy, wx, wy = self._drag_orig
        self.win.geometry(f"+{wx + (ev.x_root - ox)}+{wy + (ev.y_root - oy)}")

    def _solta(self, ev):
        if self._drag_orig is None:
            return
        ox, oy, _, _ = self._drag_orig
        dx, dy = ev.x_root - ox, ev.y_root - oy
        self._drag_orig = None
        if foi_clique(dx, dy):
            if self._on_click:
                self._on_click()
        else:
            guardar_pos(f"+{self.win.winfo_x()}+{self.win.winfo_y()}")
