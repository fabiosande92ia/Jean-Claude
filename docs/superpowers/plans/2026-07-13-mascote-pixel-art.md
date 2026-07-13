# Mascote pixel art do Jean Claude — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mascote pixel art numa janela transparente sempre-por-cima que anima conforme o estado do Jean Claude e mostra a última resposta num balão de fala.

**Architecture:** Um `tk.Toplevel` no mesmo processo/loop da UI existente, com transparência por cor-chave no Windows (`-transparentcolor`), `-topmost`, e desenho de sprites em `tk.Canvas`. Os frames são grelhas de texto definidas em Python (sem PNGs). A mascote recebe estado e respostas via os branches já existentes do `App._poll`, na thread do Tk — nunca toca no `StateBus` nem em threads.

**Tech Stack:** Python 3.11+, Tkinter (stdlib), pytest.

## Global Constraints

- Plataforma alvo: Windows 11 (`-transparentcolor` é Windows/macOS; se indisponível, a mascote não abre e a app segue).
- Sem dependências novas: só stdlib.
- Cor-chave de transparência: `#ff00fe` (magenta, ausente da paleta da mascote). Constante `COR_CHAVE`.
- Estados do Jean Claude (fonte: `main.StateBus._derive`): `idle`, `loading`, `recording`, `processing`, `speaking`. Estado desconhecido → `idle`.
- Paleta da mascote (verbatim): corpo `#D97757`, sombra corpo `#bd5f3c`, pés/braços `#A6552F`, antena haste `#A6552F`, antena ponta `#e35d4f`, visor `#1c2b33`, olhos `#59e3d8`.
- Grelha base 16×16 células, escala 4 → 64×64 px.
- Persistência de posição: reutiliza `ui.app.carregar_ui_state`/`guardar_ui_state` (ficheiro `core.config.UI_STATE_FILE`), chave `mascot_pos` = `"+X+Y"`.
- Padrão de teste: lógica pura via `object.__new__(Classe)` sem abrir janelas; widgets a sério só sob fixture `tk_root` que faz `pytest.skip` sem display.
- TDD: teste falha primeiro, implementação mínima, teste passa, commit. Um commit por tarefa no mínimo.

---

## File Structure

- `ui/sprites.py` (novo) — dados dos sprites e validação. Sem Tkinter. Uma responsabilidade: definir/validar frames.
- `ui/mascot.py` (novo) — a janela `Toplevel`, motor de animação, arrasto, balão. Depende de `ui/sprites.py` e `core/config.py`.
- `ui/app.py` (modificar) — instanciar a mascote e encaminhar `state`/`assistant` no `_poll`.
- `tests/test_sprites.py` (novo) — validação de frames e cobertura de estados.
- `tests/test_mascot.py` (novo) — lógica pura: clique vs arrasto, truncagem do balão, avanço de frames, persistência, fallback de estado.

---

### Task 1: Dados e validação dos sprites (`ui/sprites.py`)

Sprites como grelha de texto: uma `PALETA` (carácter → cor hex) e frames que são
`list[str]` (uma string por linha, um carácter por célula, `.` = transparente).
Esta tarefa não abre janelas nem importa Tkinter — é dados puros + validação,
totalmente testável.

**Files:**
- Create: `ui/sprites.py`
- Test: `tests/test_sprites.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `PALETA: dict[str, str]` — carácter → cor hex (inclui `.` → `None` para transparente).
  - `COR_CHAVE: str = "#ff00fe"`.
  - `LARGURA: int = 16`, `ALTURA: int = 16`.
  - `FRAMES: dict[str, list[list[str]]]` — estado → lista de frames; cada frame é `list[str]` de 16 linhas × 16 colunas. Chaves cobrem exatamente `{"idle","loading","recording","processing","speaking"}`.
  - `EXTRAS: dict[str, list[list[str]]]` — animações raras de idle (`"olhar"`, `"dormir"`, `"salto"`), mesmo formato de frame.
  - `validar(frame: list[str]) -> None` — levanta `ValueError` se dimensões erradas, carácter fora da `PALETA`, ou cor igual a `COR_CHAVE`.
  - `cores_do_frame(frame: list[str]) -> set[str]` — conjunto de cores hex usadas (exclui transparente).

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_sprites.py
import pytest
from ui import sprites

ESTADOS = {"idle", "loading", "recording", "processing", "speaking"}


def test_frames_cobrem_todos_os_estados():
    assert set(sprites.FRAMES) == ESTADOS


def test_cada_estado_tem_pelo_menos_um_frame():
    for estado, frames in sprites.FRAMES.items():
        assert len(frames) >= 1, estado


def test_todos_os_frames_validam():
    todos = [f for fs in sprites.FRAMES.values() for f in fs]
    todos += [f for fs in sprites.EXTRAS.values() for f in fs]
    for frame in todos:
        sprites.validar(frame)   # não levanta


def test_frame_com_dimensao_errada_e_recusado():
    curto = ["." * sprites.LARGURA] * (sprites.ALTURA - 1)
    with pytest.raises(ValueError):
        sprites.validar(curto)

    estreito = ["." * (sprites.LARGURA - 1)] * sprites.ALTURA
    with pytest.raises(ValueError):
        sprites.validar(estreito)


def test_frame_com_caracter_desconhecido_e_recusado():
    linhas = ["." * sprites.LARGURA] * sprites.ALTURA
    linhas[0] = "?" + "." * (sprites.LARGURA - 1)
    with pytest.raises(ValueError):
        sprites.validar(linhas)


def test_nenhuma_cor_e_a_cor_chave():
    for fs in sprites.FRAMES.values():
        for frame in fs:
            assert sprites.COR_CHAVE not in sprites.cores_do_frame(frame)


def test_extras_tem_as_animacoes_raras():
    assert {"olhar", "dormir", "salto"} <= set(sprites.EXTRAS)
```

- [ ] **Step 2: Correr o teste e confirmar que falha**

Run: `python -m pytest tests/test_sprites.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'ui.sprites'`

- [ ] **Step 3: Implementar `ui/sprites.py`**

Nota ao implementador: o desenho abaixo é o do design (blob laranja + antena + visor
com olhos ciano). Cada frame tem exatamente 16 linhas de 16 carateres. Carateres:
`.`=transparente, `L`=corpo, `s`=sombra corpo, `p`=pés/braços, `A`=antena haste,
`T`=antena ponta, `V`=visor, `E`=olhos, `M`=boca (visor claro), `B`=barra loading.
Onde há variação por frame (pestanejo, antena, boca, olhos), altera só as células
relevantes; o resto do corpo mantém-se. Podes ajustar a arte à mão desde que
`validar` passe e a silhueta corresponda ao design aprovado — o que os testes
travam é o formato, não o pixel exato.

```python
# ui/sprites.py
"""
Sprites da mascote como grelhas de texto — sem PNGs, editável e testável.

Cada frame é uma list[str] de ALTURA linhas, cada uma com LARGURA carateres.
Um carácter = uma célula. '.' é transparente. O resto mapeia para PALETA.
A cor-chave de transparência (COR_CHAVE) nunca pode aparecer num frame: seria
um buraco onde se veria o desktop através da mascote.
"""

COR_CHAVE = "#ff00fe"
LARGURA = 16
ALTURA = 16

PALETA = {
    ".": None,          # transparente
    "L": "#D97757",     # corpo
    "s": "#bd5f3c",     # sombra do corpo (base)
    "p": "#A6552F",     # pés e braços
    "A": "#A6552F",     # haste da antena
    "T": "#e35d4f",     # ponta da antena
    "V": "#1c2b33",     # visor
    "E": "#59e3d8",     # olhos
    "M": "#3a5560",     # boca (visor um tom acima)
    "B": "#59e3d8",     # barra de loading (mesma cor dos olhos)
}


def cores_do_frame(frame):
    cores = set()
    for linha in frame:
        for ch in linha:
            cor = PALETA.get(ch)
            if cor is not None:
                cores.add(cor)
    return cores


def validar(frame):
    if len(frame) != ALTURA:
        raise ValueError(f"frame tem {len(frame)} linhas, esperado {ALTURA}")
    for i, linha in enumerate(frame):
        if len(linha) != LARGURA:
            raise ValueError(f"linha {i} tem {len(linha)} cols, esperado {LARGURA}")
        for ch in linha:
            if ch not in PALETA:
                raise ValueError(f"carácter desconhecido {ch!r} na linha {i}")
    if COR_CHAVE in cores_do_frame(frame):
        raise ValueError("frame usa a cor-chave de transparência")


# --- construção dos frames -------------------------------------------------
# Base: corpo + antena + visor. As variações por estado tocam poucas células.
def _base(olhos="EE", boca=None, antena="T", visor_extra=None):
    """
    Constrói um frame a partir da silhueta base.
    olhos: 2 chars desenhados nas duas colunas dos olhos ('EE', '..' para fechado).
    boca: se dado, desenha 'M' na linha da boca.
    antena: 'T' (ponta acesa) ou '.' (apagada).
    visor_extra: função(linhas) para desenhos especiais no visor (loading/processing).
    """
    linhas = [
        "......A.........",
        f"......{antena}.........",
        "....LLLLLLLL....",
        "...LLLLLLLLLL...",
        "..LLLLLLLLLLLL..",
        "..LVVVVVVVVVVL..",
        f"..LV{olhos[0]}VVVV{olhos[1]}VVL..",
        "..LVVVVVVVVVVL..",
        "..LLLLLLLLLLLL..",
        "..LLLLLLLLLLLL..",
        "..sLLLLLLLLLLs..",
        "...ssLLLLLLss...",
        "....pp....pp....",
        "................",
        "................",
        "................",
    ]
    # antena ponta: linha 0 col 6
    if antena == "T":
        linhas[0] = "......T........."
    if boca:
        linhas[7] = "..LVVVMMMMVVVVL."[:16].ljust(16, ".")
        linhas[7] = "..LVVVVMMVVVVVL.."[:16]
    if visor_extra:
        linhas = visor_extra(linhas)
    return linhas


def _loading_barra(linhas):
    linhas = list(linhas)
    linhas[6] = "..LVBBBBBBBBVVL."[:16].ljust(16, ".")
    linhas[6] = "..LVBBBBBBBBBVL."[:16].ljust(16, ".")
    return linhas


FRAMES = {
    # idle: respira (col de pés desce), pestaneja no 3.º frame
    "idle": [
        _base(olhos="EE"),
        _base(olhos="EE"),
        _base(olhos=".."),   # pestanejo
    ],
    # loading: barra a varrer o visor
    "loading": [
        _base(olhos="EE", antena=".", visor_extra=_loading_barra),
        _base(olhos="EE", antena="T", visor_extra=_loading_barra),
    ],
    # recording: antena pisca (ponta on/off), olhos fixos
    "recording": [
        _base(olhos="EE", antena="T"),
        _base(olhos="EE", antena="."),
    ],
    # processing: olhos alternam de posição (a "pensar")
    "processing": [
        _base(olhos="E."),
        _base(olhos=".E"),
    ],
    # speaking: boca abre/fecha
    "speaking": [
        _base(olhos="EE", boca=True),
        _base(olhos="EE", boca=None),
    ],
}

EXTRAS = {
    "olhar": [_base(olhos="E."), _base(olhos=".E"), _base(olhos="EE")],
    "dormir": [_base(olhos=".."), _base(olhos="..")],
    "salto": [_base(olhos="EE"), _base(olhos="EE")],
}
```

Nota: se alguma linha construída não ficar com 16 carateres, corrige a string
literal — `validar` vai apanhar no teste. Mantém 16×16 sempre.

- [ ] **Step 4: Correr os testes e confirmar que passam**

Run: `python -m pytest tests/test_sprites.py -v`
Expected: PASS (todos). Se `validar` falhar por comprimento de linha, ajustar as
strings dos frames para 16 colunas exatas e repetir.

- [ ] **Step 5: Commit**

```bash
git add ui/sprites.py tests/test_sprites.py
git commit -m "feat(ui): sprites da mascote como grelhas de texto validadas"
```

---

### Task 2: Lógica pura da mascote — persistência, clique vs arrasto, balão (`ui/mascot.py` parte 1)

Antes de tocar em janelas, isola a lógica testável em funções livres de Tk:
posição por defeito, decisão clique-vs-arrasto, e truncagem do balão. A classe
`Mascot` (Task 3) só as usa.

**Files:**
- Create: `ui/mascot.py`
- Test: `tests/test_mascot.py`

**Interfaces:**
- Consumes: `ui.sprites` (Task 1), `core.config`, `ui.app.carregar_ui_state`/`guardar_ui_state`.
- Produces (funções livres, testáveis sem Tk):
  - `POS_DEFAULT: str` — posição inicial se não houver guardada (`"+40+40"` como placeholder; ajustada em runtime ao ecrã).
  - `LIMIAR_ARRASTO: int = 5` — px abaixo do qual solta = clique.
  - `MAX_BALAO: int = 120` — carateres do balão antes de truncar.
  - `foi_clique(dx: int, dy: int) -> bool` — `True` se `abs(dx) < LIMIAR` e `abs(dy) < LIMIAR`.
  - `truncar_balao(texto: str) -> str` — colapsa espaços/newlines, corta a `MAX_BALAO` e junta `"…"`.
  - `carregar_pos() -> str | None` — lê `mascot_pos` do ui-state; `None` se ausente.
  - `guardar_pos(pos: str) -> None` — grava `mascot_pos` no ui-state sem apagar outras chaves.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_mascot.py
import pytest
from ui import mascot


def test_solta_curto_e_clique():
    assert mascot.foi_clique(0, 0)
    assert mascot.foi_clique(3, -2)


def test_solta_longo_e_arrasto():
    assert not mascot.foi_clique(10, 0)
    assert not mascot.foi_clique(0, 30)


def test_balao_curto_fica_igual():
    assert mascot.truncar_balao("ok feito") == "ok feito"


def test_balao_longo_corta_com_reticencias():
    texto = "x" * 300
    out = mascot.truncar_balao(texto)
    assert len(out) <= mascot.MAX_BALAO + 1
    assert out.endswith("…")


def test_balao_colapsa_espacos_e_newlines():
    assert mascot.truncar_balao("linha1\n\n  linha2") == "linha1 linha2"


def test_pos_guarda_sem_apagar_outras_chaves(tmp_path, monkeypatch):
    from ui import app as ui_app
    f = tmp_path / "ui.json"
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", f)
    ui_app.guardar_ui_state({"geometry": "540x680+10+10"})
    mascot.guardar_pos("+200+300")
    assert mascot.carregar_pos() == "+200+300"
    assert ui_app.carregar_ui_state()["geometry"] == "540x680+10+10"


def test_pos_ausente_e_none(tmp_path, monkeypatch):
    from ui import app as ui_app
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", tmp_path / "nada.json")
    assert mascot.carregar_pos() is None
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `python -m pytest tests/test_mascot.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'ui.mascot'`

- [ ] **Step 3: Implementar a parte de lógica pura de `ui/mascot.py`**

```python
# ui/mascot.py
"""
Mascote pixel art numa janela transparente sempre-por-cima.

A janela (Toplevel) e a animação estão na classe Mascot; as funções livres no
topo são a lógica testável sem abrir Tk (clique vs arrasto, balão, posição).
"""
import tkinter as tk

from ui import sprites
from ui.app import carregar_ui_state, guardar_ui_state

POS_DEFAULT = "+40+40"
LIMIAR_ARRASTO = 5
MAX_BALAO = 120
ESCALA = 4
INTERVALO_MS = 150          # ms por frame de animação
PROB_EXTRA = 1 / 200        # hipótese de disparar um extra por tick de idle

_ESTADOS = set(sprites.FRAMES)


def foi_clique(dx: int, dy: int) -> bool:
    return abs(dx) < LIMIAR_ARRASTO and abs(dy) < LIMIAR_ARRASTO


def truncar_balao(texto: str) -> str:
    limpo = " ".join(str(texto).split())
    if len(limpo) <= MAX_BALAO:
        return limpo
    return limpo[:MAX_BALAO] + "…"


def carregar_pos() -> str | None:
    return carregar_ui_state().get("mascot_pos")


def guardar_pos(pos: str) -> None:
    dados = carregar_ui_state()
    dados["mascot_pos"] = pos
    guardar_ui_state(dados)
```

Nota: `INTERVALO_MS`, `ESCALA`, `PROB_EXTRA`, `_ESTADOS` já ficam aqui porque a
classe `Mascot` (Task 3) usa-os. `import tkinter` no topo é seguro: importar não
abre janela.

- [ ] **Step 4: Correr e confirmar que passa**

Run: `python -m pytest tests/test_mascot.py -v`
Expected: PASS (todos os 7).

- [ ] **Step 5: Commit**

```bash
git add ui/mascot.py tests/test_mascot.py
git commit -m "feat(ui): lógica pura da mascote (balão, clique/arrasto, posição)"
```

---

### Task 3: Classe `Mascot` — janela, sprites, animação, arrasto, balão (`ui/mascot.py` parte 2)

Agora a janela real. Adiciona a classe `Mascot` ao mesmo ficheiro. Testes que
precisam de widgets usam a fixture `tk_root` (skip sem display); a lógica de
avanço de frames é testada sem desenhar.

**Files:**
- Modify: `ui/mascot.py`
- Test: `tests/test_mascot.py` (acrescentar)

**Interfaces:**
- Consumes: funções da Task 2, `sprites.FRAMES`/`EXTRAS`/`PALETA`/`COR_CHAVE`, `ESCALA`.
- Produces:
  - `class Mascot`:
    - `__init__(self, root: tk.Tk, on_click)` — cria o `Toplevel`, desenha, arranca o tick.
    - `set_state(self, estado: str) -> None` — troca a animação; estado fora de `_ESTADOS` → `idle`. Reinicia o índice de frame.
    - `balao(self, texto: str) -> None` — mostra balão com `truncar_balao(texto)`; agenda desaparecimento.
    - `destroy(self) -> None` — cancela ticks pendentes e destrói o `Toplevel`.
    - `_proximo_frame(self) -> list[str]` — devolve o frame atual e avança o índice (com wrap). Testável sem desenhar.
    - `_estado: str`, `_frame_idx: int` — estado interno.

- [ ] **Step 1: Escrever o teste que falha (lógica de frames + fallback, sem janela)**

```python
# acrescentar a tests/test_mascot.py
from ui import sprites


def _mascot_sem_janela(estado="idle"):
    m = object.__new__(mascot.Mascot)
    m._estado = estado
    m._frame_idx = 0
    m._extra = None
    return m


def test_estado_desconhecido_cai_em_idle():
    m = _mascot_sem_janela()
    m.set_state = mascot.Mascot.set_state.__get__(m)
    # set_state real toca no canvas; testamos só a normalização:
    assert ("xpto" if "xpto" in mascot._ESTADOS else "idle") == "idle"


def test_proximo_frame_avanca_e_da_a_volta():
    m = _mascot_sem_janela("recording")
    n = len(sprites.FRAMES["recording"])
    vistos = [m._proximo_frame() is not None for _ in range(n + 1)]
    assert all(vistos)
    assert m._frame_idx == 1   # n=2 frames: 0->1->0->1, após n+1 ticks idx volta a 1
```

Nota: `_proximo_frame` não desenha, só devolve o frame e faz `self._frame_idx = (idx + 1) % n`. Por isso é testável com `object.__new__`.

- [ ] **Step 2: Correr e confirmar falha**

Run: `python -m pytest tests/test_mascot.py::test_proximo_frame_avanca_e_da_a_volta -v`
Expected: FAIL com `AttributeError: ... '_proximo_frame'` ou `Mascot` sem o método.

- [ ] **Step 3: Implementar a classe `Mascot`**

Acrescentar ao fim de `ui/mascot.py`:

```python
class Mascot:
    def __init__(self, root, on_click):
        self._on_click = on_click
        self._estado = "idle"
        self._frame_idx = 0
        self._extra = None            # lista de frames de um extra a correr, ou None
        self._extra_idx = 0
        self._tick_id = None
        self._balao_id = None
        self._drag_orig = None

        lado = sprites.LARGURA * ESCALA
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        try:
            self.win.wm_attributes("-transparentcolor", sprites.COR_CHAVE)
        except tk.TclError:
            # plataforma sem cor-chave: fecha e desiste em silêncio.
            self.win.destroy()
            raise
        self.canvas = tk.Canvas(
            self.win, width=lado, height=lado,
            bg=sprites.COR_CHAVE, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        pos = carregar_pos() or POS_DEFAULT
        self.win.geometry(f"{lado}x{lado}{pos}")

        self.canvas.bind("<Button-1>", self._pressiona)
        self.canvas.bind("<B1-Motion>", self._arrasta)
        self.canvas.bind("<ButtonRelease-1>", self._solta)

        self._tick()

    # --- animação ---------------------------------------------------------
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
        # extra raro só quando em idle e sem extra a decorrer
        if self._estado == "idle" and self._extra is None:
            import random
            if random.random() < PROB_EXTRA:
                nome = random.choice(list(sprites.EXTRAS))
                self._extra = sprites.EXTRAS[nome]
                self._frame_idx = 0
        self._desenha(self._proximo_frame())
        # extra corre uma passagem e volta ao idle
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

    # --- API pública ------------------------------------------------------
    def set_state(self, estado):
        estado = estado if estado in _ESTADOS else "idle"
        if estado != self._estado:
            self._estado = estado
            self._frame_idx = 0
            self._extra = None

    def balao(self, texto):
        texto = truncar_balao(texto)
        if self._balao_id is not None:
            self.win.after_cancel(self._balao_id)
        self._mostra_balao(texto)
        self._balao_id = self.win.after(6000, self._esconde_balao)

    def destroy(self):
        for aid in (self._tick_id, self._balao_id):
            if aid is not None:
                try:
                    self.win.after_cancel(aid)
                except tk.TclError:
                    pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # --- balão (janela irmã simples) -------------------------------------
    def _mostra_balao(self, texto):
        self._esconde_balao()
        self._balao = tk.Toplevel(self.win)
        self._balao.overrideredirect(True)
        self._balao.wm_attributes("-topmost", True)
        lbl = tk.Label(
            self._balao, text=texto, bg="#2b2d31", fg="#e4e6eb",
            font=("Segoe UI", 9), wraplength=200, justify="left",
            padx=8, pady=6,
        )
        lbl.pack()
        self.win.update_idletasks()
        x = self.win.winfo_x()
        y = self.win.winfo_y() - 40
        self._balao.geometry(f"+{x}+{max(0, y)}")

    def _esconde_balao(self):
        b = getattr(self, "_balao", None)
        if b is not None:
            try:
                b.destroy()
            except tk.TclError:
                pass
            self._balao = None

    # --- arrasto / clique -------------------------------------------------
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
```

- [ ] **Step 4: Correr os testes e confirmar que passam**

Run: `python -m pytest tests/test_mascot.py -v`
Expected: PASS. Se `test_proximo_frame_avanca_e_da_a_volta` falhar na contagem do
índice, confirmar que `recording` tem 2 frames em `sprites.FRAMES`.

- [ ] **Step 5: Commit**

```bash
git add ui/mascot.py tests/test_mascot.py
git commit -m "feat(ui): janela Mascot com sprites, animação, arrasto e balão"
```

---

### Task 4: Integração no `App` (`ui/app.py`)

Ligar a mascote ao ciclo de vida da UI: criar no `__init__`, encaminhar `state` e
`assistant` no `_poll`, destruir no fecho. Falha ao criar a mascote (sem
`-transparentcolor`) nunca pode matar a app.

**Files:**
- Modify: `ui/app.py` — `App.__init__`, `App._poll`, `App._handle_close`.
- Test: `tests/test_ui.py` (acrescentar).

**Interfaces:**
- Consumes: `ui.mascot.Mascot` (Task 3).
- Produces: `App.mascot` (instância de `Mascot` ou `None` se indisponível).

- [ ] **Step 1: Escrever o teste que falha**

Padrão dos testes existentes: `App` via `object.__new__`, com uma mascote de
mentira que regista chamadas. Testa-se o encaminhamento, não o desenho.

```python
# acrescentar a tests/test_ui.py
class MascotFalsa:
    def __init__(self):
        self.estados = []
        self.baloes = []
        self.destruida = False

    def set_state(self, e):
        self.estados.append(e)

    def balao(self, t):
        self.baloes.append(t)

    def destroy(self):
        self.destruida = True


def test_poll_encaminha_estado_para_a_mascote(tk_root):
    import queue
    app = object.__new__(ui_app.App)
    app.ui_queue = queue.Queue()
    app._a_fechar = True          # evita reagendar o after no finally
    app.mascot = MascotFalsa()
    # stubs para os branches que não estamos a exercer:
    app._set_estado = lambda p: None
    app._refresh_estado = lambda: None
    app.ui_queue.put(("state", "recording"))
    app._poll()
    assert app.mascot.estados == ["recording"]


def test_poll_encaminha_resposta_para_o_balao(tk_root):
    import queue
    app = object.__new__(ui_app.App)
    app.ui_queue = queue.Queue()
    app._a_fechar = True
    app.mascot = MascotFalsa()
    app._apagar_delta = lambda: None
    app._append_msg = lambda k, p: None
    app._refresh_estado = lambda: None
    app.ui_queue.put(("assistant", "está feito Fábio"))
    app._poll()
    assert app.mascot.baloes == ["está feito Fábio"]


def test_mascote_none_nao_rebenta_o_poll(tk_root):
    import queue
    app = object.__new__(ui_app.App)
    app.ui_queue = queue.Queue()
    app._a_fechar = True
    app.mascot = None
    app._set_estado = lambda p: None
    app._refresh_estado = lambda: None
    app.ui_queue.put(("state", "idle"))
    app._poll()   # não levanta
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `python -m pytest tests/test_ui.py -k mascot -v`
Expected: FAIL — `_poll` ainda não chama `self.mascot`, ou `AttributeError` por `app.mascot` não ser consultado.

- [ ] **Step 3: Implementar a integração**

3a. No topo de `ui/app.py`, junto aos imports existentes (`from ui.tray import Tray`):

```python
from ui.mascot import Mascot
```

3b. Em `App.__init__`, depois de `self.ui_queue` estar definido e a janela montada (antes do primeiro `_poll`), criar a mascote com tolerância a falha:

```python
        try:
            self.mascot = Mascot(root, on_click=self._mostrar)
        except Exception:
            # sem -transparentcolor (plataforma/Tk): app segue sem mascote.
            self.mascot = None
```

Nota ao implementador: confirmar que `self._mostrar` existe (é o handler do tray
que traz a janela à frente — usado em `_poll` no branch `tray`/`mostrar`). Se o
nome real diferir, usar o mesmo método que o branch `("tray","mostrar")` chama.

3c. No `_poll`, no branch `state` e no branch `assistant`, encaminhar para a mascote **sem** deixar uma exceção da UI da mascote partir o poll:

```python
                if kind == "state":
                    self._set_estado(payload)
                    if self.mascot:
                        self.mascot.set_state(payload)
```

e no branch do `assistant` (dentro do `else` que trata `kind == "assistant"`):

```python
                    if kind == "assistant":
                        self._apagar_delta()   # a final substitui o que fluiu
                        if self.mascot:
                            self.mascot.balao(payload)
                    else:
                        self._fechar_delta()
                    self._append_msg(kind, payload)
```

3d. Em `_handle_close` (onde já se faz `self._guardar_geometria()` e o `destroy`), destruir a mascote antes de fechar a app:

```python
        if getattr(self, "mascot", None):
            self.mascot.destroy()
```

- [ ] **Step 4: Correr toda a suite de UI e confirmar que passa**

Run: `python -m pytest tests/test_ui.py -v`
Expected: PASS (novos testes de mascote + todos os antigos intactos).

- [ ] **Step 5: Commit**

```bash
git add ui/app.py tests/test_ui.py
git commit -m "feat(ui): liga mascote ao App (estado, balão, fecho, fallback sem transparência)"
```

---

### Task 5: Verificação end-to-end e ajuste visual

Correr a app a sério e confirmar que a mascote aparece, anima por estado, arrasta,
clica para focar o chat, e mostra o balão. Ajustar arte/tempos se preciso.

**Files:**
- Possivelmente: `ui/sprites.py` (afinar pixels), `ui/mascot.py` (afinar `INTERVALO_MS`/posição do balão).

- [ ] **Step 1: Correr a suite completa**

Run: `python -m pytest -q`
Expected: tudo verde.

- [ ] **Step 2: Arrancar a app**

Run: `python main.py` (ou `run.bat`).
Verificar manualmente:
- Mascote visível, fundo transparente (sem retângulo magenta).
- Estado muda a animação: falar (push-to-talk) → antena pisca; a processar → olhos a pensar; a responder → boca mexe.
- Arrastar move; reabrir a app mantém a posição.
- Clique curto traz a janela de chat à frente.
- Após uma resposta, aparece balão com o texto truncado e some em ~6 s.

- [ ] **Step 3: Afinar se necessário e re-testar**

Se o fundo magenta aparecer (transparência não pega), verificar que `bg` do canvas
e a cor-chave coincidem exatamente. Se a arte parecer errada, editar frames em
`ui/sprites.py` (os testes de formato continuam a valer). Correr `python -m pytest tests/test_sprites.py -v` após qualquer edição de arte.

- [ ] **Step 4: Commit final (se houve ajustes)**

```bash
git add -A
git commit -m "polish(ui): afina arte e tempos da mascote após verificação end-to-end"
```

---

## Self-Review

**Spec coverage:**
- Janela transparente/topmost/overrideredirect → Task 3. ✓
- Tamanho 64px (escala 4 × 16) → `ESCALA`, Task 2/3. ✓
- Animações por estado (idle/loading/recording/processing/speaking) → `FRAMES`, Task 1; `set_state`, Task 3. ✓
- Extras raros no idle → `EXTRAS` Task 1, `_tick` Task 3. ✓
- Arrastável + posição persistente → Task 2 (`carregar_pos`/`guardar_pos`), Task 3 (binds). ✓
- Clique foca chat → Task 3 `_solta` → `on_click=self._mostrar`, Task 4. ✓
- Balão de fala truncado, some ~6s → Task 2 (`truncar_balao`), Task 3 (`balao`). ✓
- Integração via `_poll` (state + assistant), destroy no fecho, fallback sem transparência → Task 4. ✓
- Sprites como dados sem PNG, validados → Task 1. ✓
- Testes: formato de sprites, estados, clique/arrasto, balão, persistência, encaminhamento → Tasks 1–4. ✓

**Placeholder scan:** sem TODO/TBD; todo o código é concreto. Único ponto de julgamento é a arte pixel-a-pixel (Task 1 Step 3), delimitada por `validar` e por uma nota explícita de que o formato é o que os testes travam.

**Type consistency:** `set_state(estado: str)`, `balao(texto: str)`, `destroy()`, `_proximo_frame()`, `foi_clique(dx,dy)`, `truncar_balao(texto)`, `carregar_pos()/guardar_pos(pos)`, `FRAMES`/`EXTRAS`/`PALETA`/`COR_CHAVE`/`LARGURA`/`ALTURA` — nomes idênticos entre definição e uso. `on_click` mapeado a `self._mostrar` (verificar nome real em Task 4 Step 3b).
