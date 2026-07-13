# ui/app.py
import contextlib
import json
import queue
import re
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from core import config
from ui.mascot import Mascot
from ui.tray import Tray

# --- tema (um só, coerente) ------------------------------------------------
# Antes: header colorido em cima de um ScrolledText branco default. Agora tudo
# escuro, e as cores de estado são o único ponto de cor.
BG = "#1e1f22"
BG_ALT = "#2b2d31"
BG_INPUT = "#313338"
FG = "#e4e6eb"
FG_DIM = "#8a8f98"
BORDA = "#3a3d43"

FG_CLARO = "#ffffff"
FG_ESCURO = "#1a1a1a"

COR_USER = "#6fa8ff"
COR_ASSIST = "#5fd18b"
COR_ERRO = "#ff6b60"
COR_INFO = "#c9a227"

COR_CODE_BG = "#17181b"   # um degrau abaixo do BG_ALT: o bloco lê-se como bloco
COR_CODE_FG = "#e8c07d"

VU_OK = "#5fd18b"
VU_CLIP = "#ff6b60"
VU_TRACK = BORDA        # trilho sempre desenhado: canvas vazio parecia partido
VU_ALTURA = 8

BOTAO_PARAR = "#8e2f2a"
BOTAO_PARAR_ATIVO = "#a33a34"
BOTAO_ENVIAR = "#3d5afe"
BOTAO_ENVIAR_ATIVO = "#5165ff"
BOTAO_OFF = "#34373c"   # botão desativado: apagado, não só cinzento no texto

FONTE = ("Segoe UI", 10)
FONTE_CHAT = ("Segoe UI", 10)
FONTE_ESTADO = ("Segoe UI", 12, "bold")
FONTE_CODE = ("Consolas", 10)

JANELA_MIN = (420, 480)
JANELA_DEFAULT = (540, 680)
# Pedaço da janela que tem de ficar dentro do ecrã para ser agarrável com o rato.
VISIVEL_MIN = (120, 60)

STATE_COLORS = {
    "idle": "#888888",
    "loading": "#6a4bc4",
    "recording": "#cc3333",
    "processing": "#cc9900",
    # Era #1a73e8: 4.5:1 com branco, em cima do limite. Um tom abaixo dá margem.
    "speaking": "#1668cf",
}
STATE_LABELS = {
    "idle": "idle",
    "loading": "a carregar modelos",
    "recording": "a gravar",
    "processing": "a processar",
    "speaking": "a falar",
}
UNKNOWN_COLOR = "#444444"

# Estados em que o tempo importa: "a processar" há 3s ou há 40s? Sem isto não se
# distingue trabalho de app pendurada.
ESTADOS_OCUPADOS = ("loading", "recording", "processing", "speaking")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Enviar aqui era enfileirar um pedido por cima de outro (ou perdê-lo em silêncio):
# o worker está a carregar modelos ou já a tratar de um job. Durante "recording" e
# "speaking" continua a valer — o job entra na fila e corre a seguir.
ESTADOS_SEM_ENVIO = ("loading", "processing")


# --- contraste -------------------------------------------------------------
# O header era sempre texto branco: sobre o amarelo do "a processar" dava 2.6:1 e
# sobre o cinzento do "idle" 3.5:1 — ilegível de lado, ao sol, ou com a vista
# cansada. Em vez de fixar a cor do texto, escolhe-se a que lê melhor sobre cada
# fundo. Um teste garante >= 4.5:1 (WCAG AA) em todos os estados.
def _luminancia(hexcor: str) -> float:
    h = hexcor.lstrip("#")
    canais = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        canais.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canais
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(cor_a: str, cor_b: str) -> float:
    """Rácio de contraste WCAG entre duas cores (1.0 = iguais, 21.0 = preto/branco)."""
    la, lb = _luminancia(cor_a), _luminancia(cor_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def cor_texto(fundo: str) -> str:
    """Branco ou quase-preto — o que ler melhor sobre `fundo`."""
    return FG_CLARO if contraste(FG_CLARO, fundo) >= contraste(FG_ESCURO, fundo) else FG_ESCURO


def _dpi_setup(root) -> float:
    """
    Torna o processo DPI-aware e devolve a escala.

    Sem isto, o Windows faz upscale de bitmap da janela em monitores com escala
    != 100%: tudo desfocado. Tem de ser antes de criar widgets.
    """
    try:
        from ctypes import windll

        try:
            windll.shcore.SetProcessDpiAwareness(1)   # PROCESS_SYSTEM_DPI_AWARE
        except Exception:
            windll.user32.SetProcessDPIAware()        # fallback: Windows < 8.1
        dpi = windll.user32.GetDpiForSystem()
        root.tk.call("tk", "scaling", dpi / 72.0)
        return dpi / 96.0
    except Exception:
        return 1.0   # não-Windows ou API ausente: escala neutra, sem estragar nada


def nivel_vu(rms: float) -> float:
    """
    RMS do bloco de áudio -> altura da barra, em [0, 1].

    O sqrt comprime a gama: fala normal (rms ~0.02-0.1) fica bem visível em vez de
    uma barrinha colada ao zero. Saturado (clip) acima de 0.95.
    """
    try:
        rms = max(0.0, float(rms))
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, (rms ** 0.5) * 3.0)


def compor_header(label: str, modelo: str | None) -> str:
    """Texto do header: estado, e o modelo do turno se houver."""
    return f"{label} · {modelo}" if modelo else label


def _hora(ts: str | None) -> str:
    if ts:
        try:
            return datetime.fromisoformat(ts).strftime("%H:%M")
        except ValueError:
            pass
    return datetime.now().strftime("%H:%M")


# --- código na chat ---------------------------------------------------------
def segmentos_code(texto: str) -> list[tuple[str, bool]]:
    """
    Parte o texto pelas cercas ``` -> [(trecho, é_código), ...].

    A linha da cerca (e a linguagem, ```python) desaparece: é sintaxe, não conteúdo.
    Cerca por fechar -> o resto é código; melhor um bloco a mais do que perder texto.
    """
    partes: list[tuple[str, bool]] = []
    dentro = False
    buf: list[str] = []
    for linha in str(texto).split("\n"):
        if linha.lstrip().startswith("```"):
            partes.append(("\n".join(buf), dentro))
            buf = []
            dentro = not dentro
            continue
        buf.append(linha)
    partes.append(("\n".join(buf), dentro))
    return [(t.strip("\n"), c) for t, c in partes if t.strip()]


# --- geometria da janela ----------------------------------------------------
_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)")


def parse_geometry(geo: str) -> tuple[int, int, int, int] | None:
    """'540x680+100+50' -> (w, h, x, y). None se não for uma geometry do Tk."""
    m = _GEOMETRY_RE.fullmatch(str(geo).strip())
    if not m:
        return None
    w, h, x, y = (int(g) for g in m.groups())
    return w, h, x, y


def geometry_cabe(geo: str, ecra: tuple[int, int, int, int]) -> bool:
    """
    A geometry guardada ainda serve no setup de monitores de agora?

    Sem isto, desligar o segundo monitor abria a janela a 1900px de distância, fora
    de todos os ecrãs: a app arrancava invisível e parecia morta. Exige barra de
    título dentro do ecrã e um pedaço horizontal agarrável.
    """
    p = parse_geometry(geo)
    if not p:
        return False
    w, h, x, y = p
    ex, ey, ew, eh = ecra
    if w < JANELA_MIN[0] or h < JANELA_MIN[1]:
        return False
    if w > ew or h > eh:
        return False
    if y < ey or y > ey + eh - VISIVEL_MIN[1]:
        return False   # barra de título acima do topo ou abaixo do fundo: não se agarra
    if x + w < ex + VISIVEL_MIN[0] or x > ex + ew - VISIVEL_MIN[0]:
        return False   # janela toda para lá da borda esquerda/direita
    return True


def carregar_ui_state() -> dict:
    try:
        dados = json.loads(config.UI_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}   # ficheiro ausente ou corrompido: arranca no default, não rebenta
    return dados if isinstance(dados, dict) else {}


def guardar_ui_state(dados: dict) -> None:
    try:
        config.UI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.UI_STATE_FILE.write_text(json.dumps(dados), encoding="utf-8")
    except OSError:
        pass   # não guardar a posição da janela não vale matar o fecho da app


def _ecra_virtual(root) -> tuple[int, int, int, int]:
    """(x, y, w, h) do desktop virtual — todos os monitores, não só o principal."""
    try:
        from ctypes import windll

        gsm = windll.user32.GetSystemMetrics
        x, y, w, h = gsm(76), gsm(77), gsm(78), gsm(79)   # SM_*VIRTUALSCREEN
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class App:
    def __init__(self, root, on_press, on_release, ui_queue, on_close, tts_enabled,
                 on_text=None, on_cancel=None, hotkey_label="?", historico=()):
        self.root = root
        self.ui_queue = ui_queue
        self.on_close = on_close
        self.tts_enabled = tts_enabled
        self.on_text = on_text
        self.on_cancel = on_cancel

        self._estado = "loading"
        self._desde = time.monotonic()
        self._cache_estado = None
        self._topo = False
        self._a_fechar = False
        self._hotkey_label = hotkey_label
        self._placeholder = f"escreve ou usa {hotkey_label}"
        self._placeholder_ativo = False
        self._delta_ativo = False
        self._modelo = None

        escala = _dpi_setup(root)
        root.title("Jean Claude")
        # Sem minsize, encolher a janela esmagava os botões e o input até sumirem.
        root.minsize(int(JANELA_MIN[0] * escala), int(JANELA_MIN[1] * escala))
        self._restaurar_geometria(root, escala)
        root.configure(bg=BG)
        self._estilo_ttk(root)

        cor_loading = STATE_COLORS["loading"]
        self.state_label = tk.Label(
            root, text=STATE_LABELS["loading"], bg=cor_loading, fg=cor_texto(cor_loading),
            font=FONTE_ESTADO, pady=8,
        )
        self.state_label.pack(fill="x")

        # VU meter: sem isto, um mic mudo ou o device errado só se descobre quando o
        # Whisper devolve vazio. Aqui vê-se logo se está a entrar sinal.
        self._vu_rms = 0.0
        self.vu = tk.Canvas(root, height=VU_ALTURA, bg=BG_ALT, highlightthickness=0)
        self.vu.pack(fill="x")
        # Sem isto a barra ficava com a largura da última leitura: esticar a janela
        # deixava-a a meio, encolher fazia-a transbordar.
        self.vu.bind("<Configure>", lambda e: self._draw_level(self._vu_rms))

        botoes = tk.Frame(root, bg=BG)
        botoes.pack(fill="x", padx=8, pady=8)

        self.button = tk.Button(
            botoes, text=f"Falar  ({hotkey_label})", font=("Segoe UI", 13), height=2,
            bg=BG_INPUT, fg=FG, activebackground=BORDA, activeforeground=FG,
            relief="flat", bd=0,
        )
        self.button.pack(fill="x")
        self.button.bind("<ButtonPress-1>", lambda e: on_press())
        self.button.bind("<ButtonRelease-1>", lambda e: on_release())

        linha = tk.Frame(root, bg=BG)
        linha.pack(fill="x", padx=8)

        self.stop_button = tk.Button(
            linha, text="Parar", font=FONTE, command=self._parar,
            bg=BOTAO_PARAR, fg="white",
            activebackground=BOTAO_PARAR_ATIVO, activeforeground="white",
            disabledforeground=FG_DIM, relief="flat", bd=0, pady=4,
        )
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.tts_button = tk.Button(
            linha, font=FONTE, command=self._toggle_tts, relief="flat", bd=0, pady=4,
        )
        self.tts_button.pack(side="left", fill="x", expand=True, padx=4)

        self.topo_button = tk.Button(
            linha, font=FONTE, command=self._toggle_topo, relief="flat", bd=0, pady=4,
        )
        self.topo_button.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self._refresh_tts_button()
        self._refresh_topo_button()

        # tk.Text + ttk.Scrollbar em vez de ScrolledText: o ScrolledText traz um
        # tk.Scrollbar default, uma barra branca berrante colada ao tema escuro.
        moldura_chat = tk.Frame(root, bg=BG_ALT)
        moldura_chat.pack(fill="both", expand=True, padx=8, pady=8)

        self.chat = tk.Text(
            moldura_chat, state="disabled", wrap="word", width=60, height=24,
            bg=BG_ALT, fg=FG, insertbackground=FG, font=FONTE_CHAT,
            relief="flat", bd=0, padx=8, pady=8,
        )
        self.chat_scroll = ttk.Scrollbar(
            moldura_chat, orient="vertical", style="JC.Vertical.TScrollbar",
            command=self.chat.yview,
        )
        self.chat.configure(yscrollcommand=self.chat_scroll.set)
        self.chat_scroll.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_config("user", foreground=COR_USER)
        self.chat.tag_config("assistant", foreground=COR_ASSIST)
        self.chat.tag_config("error", foreground=COR_ERRO)
        self.chat.tag_config("info", foreground=COR_INFO)
        self.chat.tag_config("hora", foreground=FG_DIM)
        # Comandos e código em texto corrido não se distinguiam da prosa — e um
        # comando mal lido é um comando mal colado no terminal.
        self.chat.tag_config(
            "code", font=FONTE_CODE, background=COR_CODE_BG, foreground=COR_CODE_FG,
            lmargin1=12, lmargin2=12, spacing1=3, spacing3=3,
        )

        # Escrever, não só falar. Mic morto, alguém ao lado, uma call a decorrer:
        # sem isto a app é inútil. O texto entra na pipeline direto (salta o STT).
        entrada = tk.Frame(root, bg=BG)
        entrada.pack(fill="x", padx=8, pady=(0, 8))

        self.entry = tk.Entry(
            entrada, font=FONTE, bg=BG_INPUT, fg=FG, insertbackground=FG,
            relief="flat", bd=0,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 4))
        self.entry.bind("<Return>", self._enviar)
        self.entry.bind("<Key>", self._on_key_entry)
        self.entry.bind("<FocusOut>", lambda e: self._placeholder_on())

        self.send_button = tk.Button(
            entrada, text="Enviar", font=FONTE, command=self._enviar,
            bg=BOTAO_ENVIAR, fg="white",
            activebackground=BOTAO_ENVIAR_ATIVO, activeforeground="white",
            disabledforeground=FG_DIM, relief="flat", bd=0, padx=12,
        )
        self.send_button.pack(side="left")

        self._placeholder_on()
        self._refresh_botoes()

        for m in historico:
            self._append_msg(m.get("role", ""), m.get("text", ""), m.get("ts"))
        if historico:
            self._append("", "— conversa anterior —", "info")
            self.chat.see("end")

        self.tray = Tray(ui_queue)
        self._tray_ok = self.tray.start()
        if self._tray_ok:
            root.bind("<Unmap>", self._on_unmap)
        else:
            # O _tray_ok era guardado e nunca dito a ninguém: minimizar deixava de
            # esconder para o relógio e parecia bug, não falha do pystray.
            self._append("", "sem bandeja do sistema — minimizar não esconde para o relógio", "info")

        # Esc = Parar. A mão já está no teclado; ir buscar o rato a meio de uma
        # resposta errada é tempo a mais.
        root.bind("<Escape>", self._parar)
        root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.entry.focus_set()

        try:
            self.mascot = Mascot(root, on_click=self._mostrar)
        except Exception:
            # Sem -transparentcolor (Tk/plataforma): app segue sem mascote.
            self.mascot = None

        self._poll()

    # --- janela -------------------------------------------------------------
    def _restaurar_geometria(self, root, escala):
        root.geometry(f"{int(JANELA_DEFAULT[0] * escala)}x{int(JANELA_DEFAULT[1] * escala)}")
        estado = carregar_ui_state()
        geo = estado.get("geometry")
        if geo and geometry_cabe(geo, _ecra_virtual(root)):
            root.geometry(geo)
        if estado.get("zoomed"):
            with contextlib.suppress(tk.TclError):
                root.state("zoomed")

    def _guardar_geometria(self):
        try:
            zoomed = self.root.state() == "zoomed"
            geo = self.root.geometry()
        except tk.TclError:
            return
        guardar_ui_state({"geometry": geo, "zoomed": zoomed})

    # --- tema ---------------------------------------------------------------
    def _estilo_ttk(self, root):
        """
        Scrollbar escuro.

        O tema nativo do Windows ("vista") desenha o scrollbar com bitmaps do SO e
        ignora troughcolor/background — daí a barra branca. O "clam" é desenhado
        pelo Tk e aceita cores. Só temos um widget ttk (este scrollbar), portanto
        trocar o tema global não mexe em mais nada.
        """
        estilo = ttk.Style(root)
        with contextlib.suppress(tk.TclError):
            estilo.theme_use("clam")
        estilo.configure(
            "JC.Vertical.TScrollbar",
            troughcolor=BG_ALT, background=BORDA, arrowcolor=FG_DIM,
            bordercolor=BG_ALT, darkcolor=BORDA, lightcolor=BORDA,
            relief="flat",
        )
        estilo.map("JC.Vertical.TScrollbar", background=[("active", FG_DIM)])

    # --- input --------------------------------------------------------------
    def _placeholder_on(self):
        """Dica cinzenta na caixa vazia. Sai à primeira tecla, não ao focar: com o
        foco a começar aqui, sair ao focar era nunca chegar a ver a dica."""
        if self._placeholder_ativo or self.entry.get():
            return
        self._placeholder_ativo = True
        self.entry.insert(0, self._placeholder)
        self.entry.config(fg=FG_DIM)

    def _placeholder_off(self):
        if not self._placeholder_ativo:
            return
        self._placeholder_ativo = False
        self.entry.delete(0, "end")
        self.entry.config(fg=FG)

    def _on_key_entry(self, event):
        # Só teclas que escrevem mesmo. Setas, Tab e Esc têm char vazio (ou são o
        # atalho de Parar) e não podem apagar a dica sem nada a substituí-la.
        if self._placeholder_ativo and event.char and event.keysym != "Escape":
            self._placeholder_off()

    # --- ações ------------------------------------------------------------
    def _pode_enviar(self) -> bool:
        return self._estado not in ESTADOS_SEM_ENVIO

    def _enviar(self, event=None):
        # O Enter salta o botão: o guard tem de estar aqui, não só no state="disabled".
        if not self._pode_enviar() or self._placeholder_ativo:
            return "break"
        texto = self.entry.get().strip()
        if not texto:
            return "break"
        self.entry.delete(0, "end")
        self._placeholder_on()
        if self.on_text:
            self.on_text(texto)   # o eco na chat vem do worker, via ui_queue: sem duplicados
        return "break"

    def _parar(self, event=None):
        # Em idle não há nada para parar: sem isto, o Esc distraído enchia a chat
        # de "parado." sobre uma app que não estava a fazer nada.
        if self._estado not in ESTADOS_OCUPADOS:
            return "break"
        if self.on_cancel:
            self.on_cancel()
        return "break"

    def _toggle_tts(self):
        if self.tts_enabled.is_set():
            self.tts_enabled.clear()
        else:
            self.tts_enabled.set()
        self._refresh_tts_button()

    def _refresh_tts_button(self):
        on = self.tts_enabled.is_set()
        self.tts_button.config(
            text="Voz: ligada" if on else "Voz: desligada",
            bg="#1f6f43" if on else "#4a4d52", fg="white",
            activebackground="#25834f" if on else "#5a5d63", activeforeground="white",
        )

    def _toggle_topo(self):
        self._topo = not self._topo
        self.root.attributes("-topmost", self._topo)
        self._refresh_topo_button()

    def _refresh_topo_button(self):
        self.topo_button.config(
            text="Topo: on" if self._topo else "Topo: off",
            bg="#1f6f43" if self._topo else "#4a4d52", fg="white",
            activebackground="#25834f" if self._topo else "#5a5d63", activeforeground="white",
        )

    def _on_unmap(self, event):
        # Minimizar esconde para a bandeja em vez de ocupar a barra de tarefas —
        # mas só se o ícone existe mesmo: o run() do pystray pode falhar depois do
        # start(), e uma janela escondida sem tray só voltava matando o processo.
        if event.widget is self.root and self.root.state() == "iconic" and self.tray.visivel():
            self.root.withdraw()

    def _mostrar(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _handle_close(self):
        if self._a_fechar:
            return   # X + "Sair" do tray quase em simultâneo: fechar duas vezes rebentava
        self._a_fechar = True
        self._guardar_geometria()   # antes do destroy: depois já não há geometry para ler
        if getattr(self, "mascot", None):
            self.mascot.destroy()
        self.tray.stop()
        self.on_close()
        self.root.destroy()

    # --- chat -------------------------------------------------------------
    def _at_bottom(self) -> bool:
        try:
            return self.chat.yview()[1] >= 0.999
        except tk.TclError:
            return True

    def _inserir_corpo(self, texto, tag):
        """Corpo da mensagem, com os blocos ``` em mono e fundo próprio."""
        partes = segmentos_code(texto)
        for i, (trecho, codigo) in enumerate(partes):
            if codigo:
                if i:
                    self.chat.insert("end", "\n")   # o bloco começa em linha própria
                self.chat.insert("end", trecho + "\n", "code")
            elif tag:
                self.chat.insert("end", trecho + "\n", tag)
            else:
                self.chat.insert("end", trecho + "\n")
        self.chat.insert("end", "\n")

    def _append(self, prefix, text, tag, ts=None):
        # Só faz auto-scroll se já estavas no fundo. Antes era see("end") incondicional:
        # estavas a ler o histórico, chegava resposta, saltava-te a vista para baixo.
        colado = self._at_bottom()
        self.chat.config(state="normal")
        self.chat.insert("end", f"[{_hora(ts)}] ", "hora")
        if prefix:
            self.chat.insert("end", prefix, tag)
            self._inserir_corpo(text, None)   # o corpo fica na cor base; a cor é do prefixo
        else:
            self._inserir_corpo(text, tag)
        self.chat.config(state="disabled")
        if colado:
            self.chat.see("end")

    # --- resposta a fluir (kind="delta") ------------------------------------
    # O backend emite ("delta", texto) na ui_queue à medida que gera; aqui vamos
    # acumulando o rascunho cru. Quando chega o ("assistant", texto) final,
    # _apagar_delta() limpa o rascunho e a resposta é repintada formatada.
    def _delta(self, payload):
        texto = str(payload)
        if not texto:
            return
        colado = self._at_bottom()
        self.chat.config(state="normal")
        if not self._delta_ativo:
            self._delta_ativo = True
            # Marca com gravidade à esquerda: fica onde está enquanto se insere à
            # frente dela, e serve para apagar o bloco todo quando a final chegar.
            self.chat.mark_set("delta_inicio", "end-1c")
            self.chat.mark_gravity("delta_inicio", "left")
            self.chat.insert("end", f"[{_hora(None)}] ", "hora")
            self.chat.insert("end", "Jean Claude: ", "assistant")
        self.chat.insert("end", texto)
        self.chat.config(state="disabled")
        if colado:
            self.chat.see("end")

    def _fechar_delta(self):
        """Fecha o bloco e deixa na chat o que já fluiu (ex.: job cancelado a meio)."""
        if not self._delta_ativo:
            return
        self._delta_ativo = False
        self.chat.config(state="normal")
        self.chat.insert("end", "\n\n")
        self.chat.config(state="disabled")

    def _apagar_delta(self):
        """Apaga o bloco a fluir: a mensagem final é autoritativa e vem formatada
        (blocos de código com tag). Os pedaços entram crus — uma cerca ``` parte-se
        entre deltas e não dá para segmentar a meio."""
        if not self._delta_ativo:
            return
        self._delta_ativo = False
        self.chat.config(state="normal")
        self.chat.delete("delta_inicio", "end-1c")
        self.chat.config(state="disabled")

    def _append_msg(self, role, text, ts=None):
        if role == "user":
            self._append("Fábio: ", text, "user", ts)
        elif role == "assistant":
            self._append("Jean Claude: ", text, "assistant", ts)
        elif role == "error":
            self._append("[erro] ", text, "error", ts)
        elif role == "info":
            self._append("", str(text), "info", ts)
        else:
            # Nada se perde em silêncio: um kind novo aparece na chat em vez de sumir.
            self._append(f"[{role}] ", str(text), "info", ts)

    # --- estado -----------------------------------------------------------
    def _set_estado(self, estado):
        if estado != self._estado:
            self._estado = estado
            self._desde = time.monotonic()
            self._refresh_botoes()
        if estado != "recording":
            self._draw_level(0.0)

    def _refresh_botoes(self):
        """Os botões dizem o que a app aceita agora. Antes mentiam os três: o Falar
        não mudava a gravar, o Parar estava ativo sem nada para parar, e o Enviar
        aceitava um pedido por cima de outro."""
        gravando = self._estado == "recording"
        cor_rec = STATE_COLORS["recording"]
        self.button.config(
            text="A GRAVAR — larga para enviar" if gravando else f"Falar  ({self._hotkey_label})",
            bg=cor_rec if gravando else BG_INPUT,
            fg=cor_texto(cor_rec) if gravando else FG,
            activebackground=cor_rec if gravando else BORDA,
            activeforeground=cor_texto(cor_rec) if gravando else FG,
        )

        ocupado = self._estado in ESTADOS_OCUPADOS
        self.stop_button.config(
            state="normal" if ocupado else "disabled",
            bg=BOTAO_PARAR if ocupado else BOTAO_OFF,
        )

        pode = self._pode_enviar()
        self.send_button.config(
            state="normal" if pode else "disabled",
            bg=BOTAO_ENVIAR if pode else BOTAO_OFF,
        )

    def _refresh_estado(self):
        label = compor_header(STATE_LABELS.get(self._estado, str(self._estado)), self._modelo)
        if self._estado in ESTADOS_OCUPADOS:
            passado = time.monotonic() - self._desde
            frame = SPINNER[int(passado * 10) % len(SPINNER)]
            texto = f"{frame}  {label}  {int(passado)}s"
        else:
            texto = label
        if texto != self._cache_estado:
            self._cache_estado = texto
            cor = STATE_COLORS.get(self._estado, UNKNOWN_COLOR)
            self.state_label.config(text=texto, bg=cor, fg=cor_texto(cor))

    def _draw_level(self, rms):
        self._vu_rms = rms   # guardado para o <Configure> poder redesenhar
        self.vu.delete("all")
        largura = self.vu.winfo_width()
        if largura <= 1:
            return
        # Trilho primeiro, sempre: com nível a zero o canvas ficava vazio e a app
        # parecia partida. Agora vê-se a calha, e a barra por cima quando há sinal.
        self.vu.create_rectangle(0, 0, largura, VU_ALTURA, fill=VU_TRACK, width=0, tags="track")
        nivel = nivel_vu(rms)
        if nivel > 0:
            cor = VU_CLIP if nivel > 0.95 else VU_OK
            self.vu.create_rectangle(
                0, 0, int(largura * nivel), VU_ALTURA, fill=cor, width=0, tags="bar"
            )

    # --- loop -------------------------------------------------------------
    def _poll(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "state":
                    self._set_estado(payload)
                    if self.mascot:
                        self.mascot.set_state(payload)
                elif kind == "level":
                    self._draw_level(payload)
                elif kind == "tray":
                    if payload == "mostrar":
                        self._mostrar()
                    elif payload == "sair":
                        self._handle_close()
                        return   # janela destruída: não reagendar o poll
                elif kind == "delta":
                    self._delta(payload)
                elif kind == "modelo":
                    self._modelo = payload
                    self._cache_estado = None   # força o header a redesenhar já
                else:
                    if kind == "assistant":
                        self._apagar_delta()   # a final substitui o que fluiu
                        if self.mascot:
                            self.mascot.balao(payload)
                    else:
                        self._fechar_delta()   # erro/info a meio: guarda o que já veio
                    # .get()/else e não índice direto: um kind desconhecido rebentava o
                    # _poll dentro do callback do Tk e a UI congelava para sempre.
                    self._append_msg(kind, payload)
        except queue.Empty:
            pass
        finally:
            if not self._a_fechar:
                self._refresh_estado()
                self.root.after(50, self._poll)


def launch(on_press, on_release, ui_queue, on_close, tts_enabled,
           on_text=None, on_cancel=None, hotkey_label="?", historico=()):
    root = tk.Tk()
    App(root, on_press, on_release, ui_queue, on_close, tts_enabled,
        on_text=on_text, on_cancel=on_cancel, hotkey_label=hotkey_label, historico=historico)
    root.mainloop()
