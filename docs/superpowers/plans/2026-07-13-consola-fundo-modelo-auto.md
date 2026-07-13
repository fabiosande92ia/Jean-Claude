# Consola em segundo plano + seleção de modelo automática — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correr a consola Claude Code escondida em segundo plano com progresso vivo numa aba da UI, reinício por botão, e escolher o modelo (Haiku/Sonnet/Opus) automaticamente por complexidade.

**Architecture:** Feature B (modelo automático) primeiro — funções puras em `brain/router.py`, ligadas ao agente e ao worker, com badge no header. Depois Feature A (consola) — `brain/consola.py` (`ConsoleRunner`) dono do subprocesso escondido (`CREATE_NO_WINDOW`, `--output-format stream-json` parseado por `parse_evento`), `abrir_consola` fica fino e delega, `main.py` liga o runner e o reinício passa a botão na nova aba `Consola` do `ttk.Notebook`.

**Tech Stack:** Python 3, tkinter/ttk, `claude_agent_sdk`, `subprocess`, `pytest`.

## Global Constraints

- **Plataforma da consola:** só Windows. `ConsoleRunner.start` devolve `(False, motivo)` fora de `win32`.
- **Segurança:** o texto do Fábio vai para a consola **por ficheiro** (`config.PEDIDO_CONSOLA`), nunca como argumento do comando (injeção de shell). Mantém-se.
- **Config isolada:** a consola arranca com env-limpo — remover `CLAUDE_CONFIG_DIR` só se apontar para `config.CONFIG_DIR`; se apontar para outro sítio, é escolha do Fábio e fica.
- **Uma consola de cada vez:** `start` recusa se já corre uma.
- **IDs de modelo (verbatim):** baixa `claude-haiku-4-5-20251001`; media `claude-sonnet-5`; alta `claude-opus-4-8`.
- **Opus:** nunca sai da conversa normal (`escolher_modelo` devolve só `"baixa"`/`"media"`); só a consola pode classificar `"alta"`.
- **Idioma:** comentários e strings de UI em português, como o resto do código.
- **Testes:** `pytest`; funções puras testadas; correr a suite toda no fim de cada task.

---

### Task 1: Mapa complexidade→modelo + heurística (`brain/router.py`)

**Files:**
- Create: `brain/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Produces:
  - `MODELO: dict[str, str]` — `{"baixa": "claude-haiku-4-5-20251001", "media": "claude-sonnet-5", "alta": "claude-opus-4-8"}`
  - `modelo_id(complexidade: str) -> str` (fallback `"media"`)
  - `nome_curto(model_id: str) -> str` → `"haiku"`/`"sonnet"`/`"opus"` (fallback: o próprio id)
  - `escolher_modelo(texto: str) -> str` → `"baixa"` ou `"media"` (nunca `"alta"`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router.py
import brain.router as router


def test_modelo_id_mapeia_complexidades():
    assert router.modelo_id("baixa") == "claude-haiku-4-5-20251001"
    assert router.modelo_id("media") == "claude-sonnet-5"
    assert router.modelo_id("alta") == "claude-opus-4-8"


def test_modelo_id_fallback_media():
    assert router.modelo_id("desconhecida") == "claude-sonnet-5"
    assert router.modelo_id("") == "claude-sonnet-5"


def test_nome_curto():
    assert router.nome_curto("claude-haiku-4-5-20251001") == "haiku"
    assert router.nome_curto("claude-sonnet-5") == "sonnet"
    assert router.nome_curto("claude-opus-4-8") == "opus"
    assert router.nome_curto("outro-qualquer") == "outro-qualquer"


def test_escolher_modelo_comando_curto_e_baixa():
    assert router.escolher_modelo("abre o spotify") == "baixa"
    assert router.escolher_modelo("aumenta o volume") == "baixa"
    assert router.escolher_modelo("que horas são") == "baixa"


def test_escolher_modelo_pedido_medio_e_media():
    assert router.escolher_modelo(
        "resume-me o que fizemos hoje no projeto, com detalhe, para o diario de bordo"
    ) == "media"
    assert router.escolher_modelo("porque é que o céu é azul?") == "media"


def test_escolher_modelo_vazio_e_media():
    assert router.escolher_modelo("") == "media"
    assert router.escolher_modelo("   ") == "media"


def test_escolher_modelo_nunca_devolve_alta():
    for t in ["abre o spotify", "refactor gigante a tudo", "analisa a arquitetura toda",
              "", "reescreve o main.py inteiro por favor com muito detalhe e cuidado"]:
        assert router.escolher_modelo(t) in ("baixa", "media")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_router.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'brain.router'`)

- [ ] **Step 3: Write minimal implementation**

```python
# brain/router.py
"""
Escolha de modelo por complexidade.

Fonte única do mapa complexidade->modelo (usado pela conversa e pela consola).
A conversa normal nunca sobe a Opus — refatorações grandes vão pela consola, que
é a única que classifica "alta".
"""

MODELO = {
    "baixa": "claude-haiku-4-5-20251001",
    "media": "claude-sonnet-5",
    "alta": "claude-opus-4-8",
}

_NOME_CURTO = {
    "claude-haiku-4-5-20251001": "haiku",
    "claude-sonnet-5": "sonnet",
    "claude-opus-4-8": "opus",
}

# Verbos de ação direta: pedido curto que começa por um destes é comando runtime
# (abrir app, mexer volume), não raciocínio — Haiku chega e é mais rápido.
_VERBOS_ACAO = (
    "abre", "abrir", "fecha", "fechar", "aumenta", "baixa", "sobe", "liga",
    "desliga", "diz", "poe", "põe", "mostra", "tira", "que horas", "que temperatura",
)
_LIMITE_PALAVRAS_BAIXA = 6


def modelo_id(complexidade: str) -> str:
    return MODELO.get(complexidade, MODELO["media"])


def nome_curto(model_id: str) -> str:
    return _NOME_CURTO.get(model_id, model_id)


def escolher_modelo(texto: str) -> str:
    """Complexidade da conversa normal: só "baixa" ou "media" (nunca "alta")."""
    t = texto.strip().lower()
    if not t:
        return "media"
    curto = len(t.split()) <= _LIMITE_PALAVRAS_BAIXA
    acao = any(t.startswith(v) or t.startswith(v + " ") or f" {v} " in t for v in _VERBOS_ACAO)
    if curto and acao:
        return "baixa"
    return "media"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_router.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add brain/router.py tests/test_router.py
git commit -m "feat(router): mapa complexidade->modelo + heuristica local (nunca Opus na conversa)"
```

---

### Task 2: Agente aceita `model` por pedido (`brain/agent.py`)

**Files:**
- Modify: `brain/agent.py` (`build_options`, `ask`)
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces:
  - `JeanClaude.build_options(model: str | None = None) -> ClaudeAgentOptions` — mete `model=` nas opções.
  - `JeanClaude.ask(prompt, on_delta=None, model=None) -> str`.

- [ ] **Step 1: Write the failing test**

Ver como `tests/test_agent.py` já testa `build_options` (abrir e seguir o padrão existente). Adicionar:

```python
def test_build_options_passa_o_modelo():
    jc = JeanClaude()
    opts = jc.build_options(model="claude-opus-4-8")
    assert opts.model == "claude-opus-4-8"


def test_build_options_sem_modelo_fica_none():
    jc = JeanClaude()
    opts = jc.build_options()
    assert opts.model is None
```

(Imports: reutiliza os do topo de `tests/test_agent.py`; se `JeanClaude` ainda não estiver importado lá, adiciona `from brain.agent import JeanClaude`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent.py -k modelo -v`
Expected: FAIL (`TypeError: build_options() got an unexpected keyword argument 'model'`)

- [ ] **Step 3: Write minimal implementation**

Em `brain/agent.py`, alterar a assinatura e a construção:

```python
    def build_options(self, model=None) -> ClaudeAgentOptions:
        # ... (corpo igual até ao return) ...
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(),
            allowed_tools=list(config.ALLOWED_TOOLS) + list(JC_TOOL_NAMES) + list(self.extra_tools),
            mcp_servers={"jc": screenshot_server},
            env={
                "CLAUDE_CONFIG_DIR": str(config.CONFIG_DIR),
                "CAVEMAN_DEFAULT_MODE": config.CAVEMAN_MODE,
            },
            plugins=plugins,
            setting_sources=[],
            cwd=str(config.PROJECT_ROOT),
            permission_mode="acceptEdits",
            include_partial_messages=True,
            max_buffer_size=20 * 1024 * 1024,
            model=model,                    # None => default do SDK (retrocompatível)
        )
```

E `ask`:

```python
    async def ask(self, prompt: str, on_delta=None, model=None) -> str:
        reply = []
        async with ClaudeSDKClient(options=self.build_options(model=model)) as client:
            # ... resto igual ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brain/agent.py tests/test_agent.py
git commit -m "feat(agent): ask/build_options aceitam model por pedido"
```

---

### Task 3: Worker escolhe modelo + badge no header (`main.py`, `ui/app.py`)

**Files:**
- Modify: `main.py` (`ask_cancelavel`, `worker_loop`, imports)
- Modify: `ui/app.py` (`_poll`, `_refresh_estado`, `__init__` estado `self._modelo`)
- Test: `tests/test_main.py` (criar se não existir) — só a parte pura testável

**Interfaces:**
- Consumes: `router.escolher_modelo`, `router.modelo_id`, `router.nome_curto` (Task 1); `JeanClaude.ask(..., model=)` (Task 2).
- Produces: mensagem `("modelo", nome_curto)` no `ui_queue`; header mostra `{estado} · {modelo}`.

- [ ] **Step 1: Escrever teste da composição do header (helper puro)**

Extrai a composição do texto do header para uma função pura em `ui/app.py`, testável sem tkinter:

```python
# tests/test_header.py
from ui.app import compor_header


def test_header_sem_modelo():
    assert compor_header("idle", None) == "idle"


def test_header_com_modelo():
    assert compor_header("a processar", "opus") == "a processar · opus"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_header.py -v`
Expected: FAIL (`ImportError: cannot import name 'compor_header'`)

- [ ] **Step 3: Implementar `compor_header` + ligar no `_refresh_estado`**

Em `ui/app.py`, no nível do módulo (junto às outras funções puras como `nivel_vu`):

```python
def compor_header(label: str, modelo: str | None) -> str:
    """Texto do header: estado, e o modelo do turno se houver."""
    return f"{label} · {modelo}" if modelo else label
```

No `App.__init__`, junto aos outros atributos de estado (perto de `self._delta_ativo = False`):

```python
        self._modelo = None
```

No `_refresh_estado`, aplicar o modelo ao texto base (antes do spinner/segundos):

```python
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
```

No `_poll`, tratar a mensagem nova (adicionar ramo antes do `else` final):

```python
                elif kind == "modelo":
                    self._modelo = payload
                    self._cache_estado = None   # força o header a redesenhar já
```

- [ ] **Step 4: Ligar no `main.py`**

No topo, adicionar import:

```python
from brain import router
```

Alterar `ask_cancelavel` para aceitar e passar o modelo:

```python
async def ask_cancelavel(jc: JeanClaude, prompt: str, cancel: threading.Event, on_delta=None, model=None) -> str:
    task = asyncio.create_task(jc.ask(prompt, on_delta=on_delta, model=model))
    # ... resto igual ...
```

Em `worker_loop`, dentro do `if texto.strip():`, logo antes de `resposta = asyncio.run(...)`:

```python
                comp = router.escolher_modelo(texto)
                model_id = router.modelo_id(comp)
                ui_queue.put(("modelo", router.nome_curto(model_id)))
                resposta = asyncio.run(
                    ask_cancelavel(jc, build_prompt(index, recentes, texto), cancel,
                                   on_delta=on_delta, model=model_id)
                )
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_header.py tests/test_router.py -v`
Expected: PASS

- [ ] **Step 6: Verificação visual**

Run: `python -m skills.ui_preview processing`
Esperado: header mostra o estado (sem crashar). O badge de modelo só aparece com jobs reais, mas a app tem de arrancar sem erros.

- [ ] **Step 7: Commit**

```bash
git add main.py ui/app.py tests/test_header.py
git commit -m "feat(modelo): worker escolhe modelo por complexidade + badge no header"
```

---

### Task 4: Parse do stream-json (`brain/consola.py` — função pura)

**Files:**
- Create: `brain/consola.py` (só `parse_evento` + `_alvo` + `_PROMPT_CONSOLA` neste passo)
- Test: `tests/test_consola.py`

**Interfaces:**
- Produces: `parse_evento(ev: dict) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consola.py
import brain.consola as consola


def test_parse_texto_do_assistant():
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": "olá"}]}}
    assert consola.parse_evento(ev) == "olá"


def test_parse_tool_use_mostra_ferramenta_e_alvo():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "brain/agent.py"}},
    ]}}
    assert consola.parse_evento(ev) == "🔧 Edit: brain/agent.py"


def test_parse_tool_use_bash_usa_command():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
    ]}}
    assert consola.parse_evento(ev) == "🔧 Bash: pytest"


def test_parse_junta_texto_e_tools():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "vou editar"},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "main.py"}},
    ]}}
    assert consola.parse_evento(ev) == "vou editar\n🔧 Edit: main.py"


def test_parse_result_e_linha_de_fecho():
    assert consola.parse_evento({"type": "result", "subtype": "success"}) == "— consola terminou —"


def test_parse_ignora_system_e_tool_result():
    assert consola.parse_evento({"type": "system", "subtype": "init"}) is None
    assert consola.parse_evento({"type": "user", "message": {"content": []}}) is None


def test_parse_assistant_vazio_e_none():
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": "  "}]}}
    assert consola.parse_evento(ev) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_consola.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'brain.consola'`)

- [ ] **Step 3: Write minimal implementation**

```python
# brain/consola.py
"""
Consola Claude Code em segundo plano.

`ConsoleRunner` é dono do subprocesso escondido: arranca-o, lê o stream-json numa
thread e empurra linhas amigáveis para o ui_queue; no fim lê o resumo e avisa a
app. `parse_evento` é puro (testável sem processo).
"""

# Prompt FIXO passado à consola: o texto do Fábio nunca entra no comando (injeção
# de shell); vai por ficheiro (.jc-config/pedido-consola.md) e a consola lê-o de lá.
_PROMPT_CONSOLA = (
    "Le o ficheiro .jc-config/pedido-consola.md e executa o pedido que la esta. "
    "No fim corre os testes e escreve um resumo final (o que mudou e se os testes "
    "passaram) no ficheiro .jc-config/consola-ultima.md — a app do Jean Claude "
    "mostra esse resumo ao Fabio e ele reinicia quando quiser."
)


def _alvo(inp: dict) -> str:
    for chave in ("file_path", "command", "pattern", "path", "url"):
        v = inp.get(chave)
        if v:
            return str(v)[:80]
    return ""


def parse_evento(ev: dict) -> str | None:
    """Evento do stream-json -> linha amigável, ou None se for para ignorar."""
    tipo = ev.get("type")
    if tipo == "assistant":
        linhas = []
        for bloco in ev.get("message", {}).get("content", []):
            bt = bloco.get("type")
            if bt == "text":
                txt = bloco.get("text", "").strip()
                if txt:
                    linhas.append(txt)
            elif bt == "tool_use":
                nome = bloco.get("name", "?")
                alvo = _alvo(bloco.get("input", {}))
                linhas.append(f"🔧 {nome}: {alvo}" if alvo else f"🔧 {nome}")
        return "\n".join(linhas) or None
    if tipo == "result":
        return "— consola terminou —"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_consola.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brain/consola.py tests/test_consola.py
git commit -m "feat(consola): parse_evento do stream-json (funcao pura)"
```

---

### Task 5: `ConsoleRunner` — ciclo de vida (`brain/consola.py`)

**Files:**
- Modify: `brain/consola.py` (adicionar a classe)
- Test: `tests/test_consola.py` (adicionar testes do runner)

**Interfaces:**
- Consumes: `parse_evento` (Task 4); `router.modelo_id`, `router.nome_curto` (Task 1); `config.PEDIDO_CONSOLA`, `config.CONFIG_DIR`, `config.PROJECT_ROOT`; `brain.tools.ler_resumo_consola_pendente` (import tardio, evita ciclo).
- Produces:
  - `ConsoleRunner(ui_queue, on_terminou)` 
  - `.start(pedido: str, complexidade: str) -> tuple[bool, str]`
  - `.is_running() -> bool`
  - Mensagens no ui_queue: `("consola_estado", {"run": True, "modelo": str})`, `("consola", linha)`, `("consola_estado", {"run": False})`, `("consola_fim", resumo)`.

- [ ] **Step 1: Write the failing test**

```python
# adicionar a tests/test_consola.py
import json
import threading
import brain.consola as consola
from core import config


class FakeProc:
    """Popen falso: stdout entrega linhas pré-definidas; wait() destranca quando o teste manda."""
    def __init__(self, linhas):
        self.stdout = iter(linhas)
        self._fim = threading.Event()

    def wait(self):
        self._fim.wait(timeout=1.0)
        self._fim.set()

    def terminar(self):
        self._fim.set()


class FilaFalsa:
    def __init__(self):
        self.itens = []
    def put(self, item):
        self.itens.append(item)


def _preparar(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEDIDO_CONSOLA", tmp_path / "pedido-consola.md")
    monkeypatch.setattr(config, "CONSOLA_ULTIMA", tmp_path / "consola-ultima.md")
    monkeypatch.setattr(config, "CONSOLA_LOG", tmp_path / "consola-log.txt")
    monkeypatch.setattr(consola.sys, "platform", "win32")
    monkeypatch.setattr(consola.shutil, "which", lambda _: "claude")


def test_start_escreve_pedido_e_lanca_com_modelo(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    chamadas = []
    linhas = [json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "oi"}]}}) + "\n",
              json.dumps({"type": "result", "subtype": "success"}) + "\n"]
    proc = FakeProc(linhas)
    monkeypatch.setattr(consola.subprocess, "Popen", lambda *a, **k: (chamadas.append((a, k)), proc)[1])
    config.CONSOLA_ULTIMA.write_text("mudei X, testes ok", encoding="utf-8")

    fila = FilaFalsa()
    terminou = threading.Event()
    runner = consola.ConsoleRunner(fila, on_terminou=terminou.set)

    ok, motivo = runner.start("muda a cor do botão", "alta")
    assert ok and motivo == ""
    assert "muda a cor do botão" in config.PEDIDO_CONSOLA.read_text(encoding="utf-8")

    (args, kwargs), = chamadas
    cmd = args[0]
    assert "--model" in cmd and "claude-opus-4-8" in cmd          # complexidade "alta"
    assert "--dangerously-skip-permissions" in cmd
    assert "--output-format" in cmd and "stream-json" in cmd
    assert kwargs["creationflags"] == consola.subprocess.CREATE_NO_WINDOW
    assert kwargs["stdout"] == consola.subprocess.PIPE
    assert kwargs["stdin"] == consola.subprocess.DEVNULL
    assert all("muda a cor" not in str(p) for p in cmd)           # pedido nunca no comando

    proc.terminar()
    assert terminou.wait(timeout=2)
    kinds = [m[0] for m in fila.itens]
    assert kinds[0] == "consola_estado" and fila.itens[0][1]["run"] is True
    assert fila.itens[0][1]["modelo"] == "opus"
    assert ("consola", "oi") in fila.itens
    assert ("consola_fim", "mudei X, testes ok") in fila.itens
    assert not runner.is_running()


def test_start_recusa_segunda_consola(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    proc = FakeProc([])                       # stdout vazio: reader fica logo no wait()
    monkeypatch.setattr(consola.subprocess, "Popen", lambda *a, **k: proc)
    runner = consola.ConsoleRunner(FilaFalsa(), on_terminou=lambda: None)

    ok1, _ = runner.start("pedido 1", "baixa")
    assert ok1 and runner.is_running()
    ok2, motivo = runner.start("pedido 2", "baixa")
    assert ok2 is False and "a correr" in motivo
    proc.terminar()


def test_start_fora_de_windows_recusa(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(consola.sys, "platform", "linux")
    runner = consola.ConsoleRunner(FilaFalsa(), on_terminou=lambda: None)
    ok, motivo = runner.start("x", "media")
    assert ok is False and "Windows" in motivo


def test_start_sem_claude_no_path_recusa(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(consola.shutil, "which", lambda _: None)
    runner = consola.ConsoleRunner(FilaFalsa(), on_terminou=lambda: None)
    ok, motivo = runner.start("x", "media")
    assert ok is False and "PATH" in motivo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_consola.py -k "start" -v`
Expected: FAIL (`AttributeError: module 'brain.consola' has no attribute 'ConsoleRunner'`)

- [ ] **Step 3: Write minimal implementation**

Adicionar imports no topo de `brain/consola.py` e a classe:

```python
import json
import os
import shutil
import subprocess
import sys
import threading

from core import config
from brain import router
```

```python
class ConsoleRunner:
    def __init__(self, ui_queue, on_terminou):
        self.ui_queue = ui_queue
        self.on_terminou = on_terminou
        self._lock = threading.Lock()
        self._proc = None

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None

    def start(self, pedido: str, complexidade: str) -> tuple[bool, str]:
        with self._lock:
            if self._proc is not None:
                return False, "Já há uma consola a correr. Espera que acabe."
        if sys.platform != "win32":
            return False, "A consola de desenvolvimento só está implementada em Windows."
        if shutil.which("claude") is None:
            return False, ("Claude Code não está no PATH — instala com: "
                           "npm install -g @anthropic-ai/claude-code")

        config.PEDIDO_CONSOLA.parent.mkdir(parents=True, exist_ok=True)
        config.PEDIDO_CONSOLA.write_text(
            "# Pedido do Fábio (entregue pelo Jean Claude em execução)\n\n" + pedido + "\n",
            encoding="utf-8",
        )
        # Env-limpo: a consola abre com a config GLOBAL do Fábio, não a isolada do JC.
        env = os.environ.copy()
        if env.get("CLAUDE_CONFIG_DIR") == str(config.CONFIG_DIR):
            del env["CLAUDE_CONFIG_DIR"]

        model = router.modelo_id(complexidade)
        try:
            proc = subprocess.Popen(
                ["cmd", "/c", "claude", "-p", "--model", model,
                 "--output-format", "stream-json", "--verbose",
                 "--dangerously-skip-permissions", _PROMPT_CONSOLA],
                cwd=str(config.PROJECT_ROOT),
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            return False, f"Falha a abrir a consola: {type(e).__name__}: {e}"

        with self._lock:
            self._proc = proc
        self.ui_queue.put(("consola_estado", {"run": True, "modelo": router.nome_curto(model)}))
        threading.Thread(target=self._ler, args=(proc,), daemon=True).start()
        return True, ""

    def _ler(self, proc) -> None:
        try:
            if proc.stdout is not None:
                for linha in proc.stdout:
                    linha = linha.rstrip("\n")
                    if not linha.strip():
                        continue
                    try:
                        amigavel = parse_evento(json.loads(linha))
                    except (json.JSONDecodeError, AttributeError):
                        amigavel = linha   # fallback: linha crua, nunca rebenta
                    if amigavel:
                        self.ui_queue.put(("consola", amigavel))
        finally:
            proc.wait()
            with self._lock:
                self._proc = None
            self.ui_queue.put(("consola_estado", {"run": False}))
            # Import tardio: evita ciclo brain.tools <-> brain.consola no arranque.
            from brain.tools import ler_resumo_consola_pendente
            resumo = ler_resumo_consola_pendente() or "(sem resumo)"
            self.ui_queue.put(("consola_fim", resumo))
            if self.on_terminou:
                self.on_terminou()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_consola.py -v`
Expected: PASS (parse + runner)

- [ ] **Step 5: Commit**

```bash
git add brain/consola.py tests/test_consola.py
git commit -m "feat(consola): ConsoleRunner escondido (stream-json, guard, resumo no fim)"
```

---

### Task 6: `abrir_consola` delega no runner + param `complexidade` (`brain/tools.py`)

**Files:**
- Modify: `brain/tools.py` (`abrir_consola`, remover Popen antigo e `configurar_reinicio`, adicionar `configurar_consola`)
- Test: `tests/test_tools.py` (reescrever os testes ligados ao Popen antigo)

**Interfaces:**
- Consumes: `ConsoleRunner` (Task 5) via `configurar_consola`.
- Produces:
  - `configurar_consola(runner) -> None`
  - `abrir_consola` (tool) com schema `{"pedido": str, "complexidade": str}`.
  - Mantém `ler_resumo_consola_pendente` (inalterado).

- [ ] **Step 1: Reescrever os testes do tool**

Substituir em `tests/test_tools.py` os testes que assumem o Popen/restart antigos (`test_abrir_consola_escreve_pedido...`, `test_abrir_consola_larga_config...`, `test_reinicio_so_dispara...`) por testes da delegação. **Manter** os testes de `ler_resumo_consola_pendente` (`test_resumo_*`) tal como estão.

```python
# tests/test_tools.py  (nova secção de topo; manter os test_resumo_* no fim)
import asyncio
import brain.tools as tools
from core import config


def _run(args):
    return asyncio.run(tools.abrir_consola.handler(args))


def _texto_de(resultado) -> str:
    return resultado["content"][0]["text"]


class RunnerFalso:
    def __init__(self, resultado=(True, "")):
        self.resultado = resultado
        self.chamadas = []
    def start(self, pedido, complexidade):
        self.chamadas.append((pedido, complexidade))
        return self.resultado


def test_abrir_consola_delega_no_runner_com_complexidade():
    runner = RunnerFalso((True, ""))
    tools.configurar_consola(runner)
    res = _run({"pedido": "muda a cor do botão", "complexidade": "alta"})
    assert "is_error" not in res
    assert runner.chamadas == [("muda a cor do botão", "alta")]


def test_abrir_consola_complexidade_default_media():
    runner = RunnerFalso((True, ""))
    tools.configurar_consola(runner)
    _run({"pedido": "faz x"})
    assert runner.chamadas == [("faz x", "media")]


def test_abrir_consola_sem_pedido_e_erro():
    tools.configurar_consola(RunnerFalso())
    res = _run({"pedido": "   "})
    assert res.get("is_error") is True


def test_abrir_consola_propaga_recusa_do_runner():
    runner = RunnerFalso((False, "Já há uma consola a correr. Espera que acabe."))
    tools.configurar_consola(runner)
    res = _run({"pedido": "faz x", "complexidade": "baixa"})
    assert res.get("is_error") is True
    assert "a correr" in _texto_de(res)


def test_abrir_consola_sem_runner_ligado_e_erro():
    tools.configurar_consola(None)
    res = _run({"pedido": "faz x"})
    assert res.get("is_error") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tools.py -v`
Expected: FAIL (`AttributeError: module 'brain.tools' has no attribute 'configurar_consola'`)

- [ ] **Step 3: Reescrever `abrir_consola` em `brain/tools.py`**

Remover: o bloco `_PROMPT_CONSOLA` (mudou-se para `consola.py`), `_restart_ctx`, `configurar_reinicio`, e todo o corpo antigo de `abrir_consola` (Popen + thread de reinício). Substituir por:

```python
_console_ctx = {"runner": None}


def configurar_consola(runner) -> None:
    """Liga `abrir_consola` ao ConsoleRunner criado em main.py."""
    _console_ctx["runner"] = runner


@tool(
    "abrir_consola",
    "Abre uma consola Claude Code em segundo plano que executa sozinha o pedido do Fábio, "
    "sem aprovações, sem mexer na app em execução. Usa isto quando o Fábio pedir mudanças "
    "reais ao código do próprio Jean Claude em brain/, core/, ui/ ou main.py. Para voice/, "
    "vision/ ou testes, PERGUNTA ao Fábio antes de abrir. Não uses para dúvidas, conversa, "
    "ou mudanças triviais. Passa em `pedido` o que ele quer com o contexto todo (a consola "
    "não vê esta conversa) e em `complexidade` uma de: 'baixa' (ajustes pequenos, renames), "
    "'media' (features, refactors médios), 'alta' (SÓ refatorações grandes: estrutural, "
    "multi-ficheiro, reescrita). O Fábio acompanha na aba Consola; avisa-o quando acabar.",
    {"pedido": str, "complexidade": str},
)
async def abrir_consola(args):
    pedido = (args.get("pedido") or "").strip()
    if not pedido:
        return _texto("Falta o `pedido`: descreve o que o Fábio quer mudar.", erro=True)
    complexidade = (args.get("complexidade") or "media").strip().lower()
    runner = _console_ctx["runner"]
    if runner is None:
        return _texto("Consola indisponível (a app não ligou o runner).", erro=True)
    ok, motivo = runner.start(pedido, complexidade)
    if not ok:
        return _texto(motivo, erro=True)
    return _texto(
        "Consola aberta em segundo plano, a trabalhar no pedido. O Fábio vê o progresso "
        "na aba Consola; avisa-o quando acabar."
    )
```

Nota: `shutil`, `os`, `subprocess`, `sys` deixam de ser usados em `tools.py` se mais nada os usar — verificar com o linter e remover imports órfãos (só se de facto ficarem sem uso; `screenshot` não os usa).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tools.py -v`
Expected: PASS (delegação + resumo)

- [ ] **Step 5: Commit**

```bash
git add brain/tools.py tests/test_tools.py
git commit -m "feat(tools): abrir_consola delega no ConsoleRunner + param complexidade"
```

---

### Task 7: Ligar o runner e o reinício-por-botão no `main.py`

**Files:**
- Modify: `main.py` (`main()` wiring; `worker_loop` já tratado na Task 3)

**Interfaces:**
- Consumes: `consola.ConsoleRunner` (Task 5); `brain_tools.configurar_consola` (Task 6); `ui_app.launch(..., on_reiniciar=...)` (parametro novo, implementado na Task 8).
- Produces: runner ligado; `reiniciar_event` disparado pelo botão da UI, não pela consola.

- [ ] **Step 1: Alterar imports e wiring em `main()`**

No topo de `main.py`, adicionar:

```python
from brain import consola
```

Em `main()`, substituir o bloco atual de `configurar_reinicio` + resumo (linhas ~284-294) por:

```python
    # Reinício: agora é o Fábio que carrega no botão da aba Consola quando quer
    # aplicar as mudanças. O evento é marcado no clique; o relance acontece no fim
    # do mainloop, como já era.
    reiniciar_event = threading.Event()

    runner = consola.ConsoleRunner(ui_queue, on_terminou=lambda: None)
    brain_tools.configurar_consola(runner)

    # Resumo pendente de um reinício anterior (se a app foi relançada com resumo por
    # mostrar) — consumido aqui, não repete no próximo arranque.
    resumo_consola = brain_tools.ler_resumo_consola_pendente()
    if resumo_consola:
        ui_queue.put(("info", f"[consola] {resumo_consola}"))
```

- [ ] **Step 2: Passar `on_reiniciar` ao `launch`**

Alterar a chamada `ui_app.launch(...)` (fim de `main()`) para incluir:

```python
    ui_app.launch(
        begin_recording, end_recording, ui_queue, on_close, tts_enabled,
        on_text=submit_text, on_cancel=cancelar, hotkey_label=tecla_label,
        historico=history.load(config.HISTORY_REPLAY),
        on_reiniciar=reiniciar_event.set,
    )
```

O bloco final que relança o processo (`if reiniciar_event.is_set(): subprocess.Popen(...)`) fica inalterado.

- [ ] **Step 3: Run tests (suite toda — nada partiu)**

Run: `python -m pytest -q`
Expected: PASS (test_tools, test_consola, test_router, test_agent, test_header e os já existentes)

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(main): liga ConsoleRunner + reinicio por botao (adeus auto-restart da consola)"
```

---

### Task 8: Aba Consola na UI — Notebook, badges, botão reiniciar (`ui/app.py`)

**Files:**
- Modify: `ui/app.py` (`__init__` restructure, `_poll`, novos métodos, `launch`)
- Modify: `skills/ui_preview.py` (injetar uma corrida de consola falsa para verificação visual)

**Interfaces:**
- Consumes: mensagens `("consola", …)`, `("consola_estado", …)`, `("consola_fim", …)` (Task 5); `on_reiniciar` de `main.py` (Task 7).
- Produces: `launch(..., on_reiniciar=None)`; aba "Consola" funcional.

- [ ] **Step 1: `launch` aceita `on_reiniciar`**

```python
def launch(on_press, on_release, ui_queue, on_close, tts_enabled,
           on_text=None, on_cancel=None, hotkey_label="?", historico=(), on_reiniciar=None):
    root = tk.Tk()
    App(root, on_press, on_release, ui_queue, on_close, tts_enabled,
        on_text=on_text, on_cancel=on_cancel, hotkey_label=hotkey_label,
        historico=historico, on_reiniciar=on_reiniciar)
    root.mainloop()
```

E o `__init__` do `App` ganha `on_reiniciar=None` no fim da assinatura, com `self.on_reiniciar = on_reiniciar` e novos atributos de estado da consola:

```python
        self.on_reiniciar = on_reiniciar
        self._consola_run = False
        self._consola_modelo = None
        self._consola_visto = True     # badge só acende quando há algo por ver
```

- [ ] **Step 2: Restruturar em `ttk.Notebook`**

`state_label`, `vu`, `botoes` (Falar) e `linha` (Parar/TTS/Topo) ficam em `root` (controlo global, sempre visível). O que muda: `moldura_chat` e `entrada` passam a viver dentro de uma aba "Chat" de um `Notebook`; adiciona-se a aba "Consola".

Substituir a criação de `moldura_chat` (linha ~326) — em vez de `moldura_chat = tk.Frame(root, ...)` seguido de packs diretos, criar o Notebook e as abas:

```python
        self.nb = ttk.Notebook(root, style="JC.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        aba_chat = tk.Frame(self.nb, bg=BG)
        self.nb.add(aba_chat, text="Chat")

        aba_consola = tk.Frame(self.nb, bg=BG)
        self.nb.add(aba_consola, text="Consola")
        self._idx_consola = self.nb.index("end") - 1
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)
```

`moldura_chat` e `entrada` passam a ter `aba_chat` como pai (trocar `root`/`moldura_chat` pelos frames da aba nas linhas relevantes — a `entrada` que hoje faz `entrada = tk.Frame(root, ...)` passa a `tk.Frame(aba_chat, ...)`, e `moldura_chat = tk.Frame(aba_chat, ...)`).

Conteúdo da aba Consola (a seguir ao `nb.add(aba_consola...)`):

```python
        moldura_cons = tk.Frame(aba_consola, bg=BG_ALT)
        moldura_cons.pack(fill="both", expand=True, padx=8, pady=8)
        self.consola_txt = tk.Text(
            moldura_cons, state="disabled", wrap="word",
            bg=COR_CODE_BG, fg=COR_CODE_FG, font=FONTE_CODE,
            relief="flat", bd=0, padx=8, pady=8,
        )
        cons_scroll = ttk.Scrollbar(moldura_cons, orient="vertical",
                                    style="JC.Vertical.TScrollbar", command=self.consola_txt.yview)
        self.consola_txt.configure(yscrollcommand=cons_scroll.set)
        cons_scroll.pack(side="right", fill="y")
        self.consola_txt.pack(side="left", fill="both", expand=True)

        self.btn_reiniciar = tk.Button(
            aba_consola, text="Consola acabou — reiniciar pra aplicar",
            font=FONTE, command=self._reiniciar_app,
            bg=BOTAO_ENVIAR, fg="white", activebackground=BOTAO_ENVIAR_ATIVO,
            activeforeground="white", relief="flat", bd=0, pady=6,
        )
        # escondido até a consola acabar (pack só no consola_fim)
```

(Adicionar um estilo `JC.TNotebook` em `_estilo_ttk` a condizer com o tema escuro — fundo `BG`, abas `BG_ALT`/`FG`. Seguir o padrão do `JC.Vertical.TScrollbar` já lá definido.)

- [ ] **Step 3: Métodos novos + ramos no `_poll`**

Adicionar métodos ao `App`:

```python
    def _on_tab(self, _event=None):
        if self.nb.index("current") == self._idx_consola:
            self._consola_visto = True
            self._refresh_badge_consola()

    def _append_consola(self, linha):
        self.consola_txt.config(state="normal")
        self.consola_txt.insert("end", linha + "\n")
        self.consola_txt.config(state="disabled")
        self.consola_txt.see("end")

    def _refresh_badge_consola(self):
        if self._consola_run:
            passado = time.monotonic() - self._desde
            frame = SPINNER[int(passado * 10) % len(SPINNER)]
            modelo = f" · {self._consola_modelo}" if self._consola_modelo else ""
            texto = f"{frame} Consola{modelo}"
        elif not self._consola_visto:
            texto = "✓ Consola"
        else:
            texto = "Consola"
        self.nb.tab(self._idx_consola, text=texto)

    def _reiniciar_app(self):
        if self.on_reiniciar:
            self.on_reiniciar()
        self._handle_close()
```

No `_poll`, adicionar ramos (antes do `else` final, junto ao ramo `"modelo"` da Task 3):

```python
                elif kind == "consola":
                    self._append_consola(payload)
                elif kind == "consola_estado":
                    self._consola_run = bool(payload.get("run"))
                    if "modelo" in payload:
                        self._consola_modelo = payload["modelo"]
                    if self._consola_run:
                        self._consola_visto = self.nb.index("current") == self._idx_consola
                    self._refresh_badge_consola()
                elif kind == "consola_fim":
                    self._append_consola(f"\n{payload}\n")
                    self._consola_run = False
                    self._consola_visto = self.nb.index("current") == self._idx_consola
                    self._refresh_badge_consola()
                    self.btn_reiniciar.pack(fill="x", padx=8, pady=(0, 8))
                    _ding()
                    self._append_msg("assistant", f"Consola acabou. {payload}")
```

No `finally` do `_poll` (que já chama `_refresh_estado`), adicionar a atualização do spinner da aba enquanto corre:

```python
        finally:
            if not self._a_fechar:
                self._refresh_estado()
                if self._consola_run:
                    self._refresh_badge_consola()
                self.root.after(50, self._poll)
```

- [ ] **Step 4: Helper `_ding` (nível de módulo)**

Junto às funções puras do topo de `ui/app.py`:

```python
def _ding():
    """Beep curto de fim de consola. No-op fora de Windows."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass
```

- [ ] **Step 5: Atualizar `skills/ui_preview.py` para exercitar a consola**

No `feeder` de `skills/ui_preview.py`, depois do estado inicial, injetar uma corrida falsa (para verificação visual da aba, badge e botão):

```python
        ui_queue.put(("consola_estado", {"run": True, "modelo": "opus"}))
        for linha in ["vou editar o agente", "🔧 Edit: brain/agent.py", "🔧 Bash: pytest",
                      "— consola terminou —"]:
            time.sleep(0.6)
            ui_queue.put(("consola", linha))
        time.sleep(0.4)
        ui_queue.put(("consola_estado", {"run": False}))
        ui_queue.put(("consola_fim", "mudei o agente, testes passaram"))
```

E passar `on_reiniciar=lambda: ui_queue.put(("info", "reiniciar (preview)"))` à chamada `ui_app.launch(...)` no preview.

- [ ] **Step 6: Verificação visual**

Run: `python -m skills.ui_preview idle`
Esperado:
- Duas abas: "Chat" e "Consola".
- A aba "Consola" mostra `● Consola · opus` a girar enquanto chegam linhas; ao fim fica `✓ Consola` (se não a tiveres aberto).
- Clicar na aba Consola: vê-se o log parseado; o badge `✓` limpa.
- No fim: botão "reiniciar" aparece; ouve-se o ding; no Chat aparece "Consola acabou. …".
- Chat continua a funcionar (escrever no input, enviar) sem interferência.

- [ ] **Step 7: Run test suite**

Run: `python -m pytest -q`
Expected: PASS (a UI não tem testes unitários novos; garantir que nada partiu)

- [ ] **Step 8: Commit**

```bash
git add ui/app.py skills/ui_preview.py
git commit -m "feat(ui): aba Consola em segundo plano (badge, log parseado, botao reiniciar, ding)"
```

---

### Task 9: Gatilho da consola na persona (`.jc-config/CLAUDE.md`)

**Files:**
- Modify: `.jc-config/CLAUDE.md` (secção "Alterações ao teu próprio código")
- Test: `tests/test_persona.py` (se afirmar conteúdo do CLAUDE.md — ajustar; senão, sem teste)

**Interfaces:**
- Consumes: nada.
- Produces: guia atualizado de quando abrir a consola.

- [ ] **Step 1: Ver se algum teste afirma o texto**

Run: `python -m pytest tests/test_persona.py -v`
Ler `tests/test_persona.py`; se algum assert depender das frases exatas que vais mudar (ex.: "reinicia a app no fim", "SEMPRE"), ajustar esse assert ao texto novo no mesmo commit.

- [ ] **Step 2: Reescrever a secção**

Substituir as linhas da secção "## Alterações ao teu próprio código (regra absoluta)" por:

```markdown
## Alterações ao teu próprio código (regra absoluta)
- O teu código está EM EXECUÇÃO. Editá-lo ao vivo pode fechar/partir a app a meio.
- Se o Fábio pedir mudanças reais ao código em `brain/`, `core/`, `ui/` ou `main.py`: NUNCA edites diretamente. Chama a tool `abrir_consola` com o `pedido` completo (contexto todo — a consola não vê esta conversa) e a `complexidade` certa: `baixa` (ajustes pequenos, renames), `media` (features, refactors médios), `alta` (SÓ refatorações grandes — estrutural, multi-ficheiro, reescrita).
- Para `voice/`, `vision/` ou testes: PERGUNTA ao Fábio antes de abrir a consola.
- NÃO abras consola para dúvidas, conversa, ou mudanças triviais — se tiveres dúvida do âmbito, pergunta.
- A consola corre em segundo plano; o Fábio acompanha na aba Consola. Quando acabar, avisa-o. O reinício para aplicar é ele que faz, no botão.
- Exceções (podes escrever diretamente): `memory/` e `skills/` — são dados e extensões, não o código em execução.
```

Atualizar também a linha ~20 se mencionar auto-reinício:
`- Abrir consola de desenvolvimento: tool \`abrir_consola\` (Claude Code no projeto, em segundo plano).`

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_persona.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add .jc-config/CLAUDE.md tests/test_persona.py
git commit -m "docs(persona): gatilho da consola (brain/core/ui/main; complexidade; reinicio por botao)"
```

---

## Verificação final

- [ ] `python -m pytest -q` — suite toda verde.
- [ ] `python -m skills.ui_preview idle` — abas Chat/Consola, badge, log, botão, ding, sem interferência no chat.
- [ ] Teste ponta-a-ponta real (manual): correr `python main.py`, pedir uma mudança pequena de código (ex.: "muda o texto do botão Falar"), confirmar: consola arranca sem janela, aba Consola pisca, chat continua a responder, no fim aparece ding + resumo + botão, clicar reinicia e o resumo reaparece no arranque.

## Self-review (feito)

- **Cobertura do spec:** A.1→Task5; A.2→Task4; A.3→Task5+Task8; A.4→Task8; A.5→Task7+Task8; A.6→Task9; B.1→Task1; B.2→Task6; B.3→Task1; B.4→Task2+Task3; B.5→Task3+Task8. Sem lacunas.
- **Placeholders:** nenhum — código completo em cada passo.
- **Consistência de tipos:** `("consola_estado", dict)` produzido na Task 5 e consumido na Task 8 com as mesmas chaves (`run`, `modelo`); `escolher_modelo`/`modelo_id`/`nome_curto` usados com as assinaturas da Task 1; `on_reiniciar` fluindo main→launch→App→botão.
```
