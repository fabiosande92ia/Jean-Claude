# Jean Claude v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o Jean Claude v1 — super assistente de desktop com identidade própria, voz push-to-talk local, visão de ecrã, memória persistente e capacidade de criar skills, alimentado pelo Claude Agent SDK de forma isolada.

**Architecture:** Wrapper Python à volta do Claude Agent SDK. O loop principal grava voz (push-to-talk), transcreve com faster-whisper, passa o texto ao Agent SDK (persona Jean Claude + tools básicas + custom tool de screenshot), sintetiza a resposta com Piper (interface TTS plugável), e mostra texto no ecrã. Configuração totalmente isolada do `~/.claude` global via `setting_sources=[]` e `CLAUDE_CONFIG_DIR` próprio. Memória e skills são ficheiros no repositório, geridos pelo próprio Jean Claude através das tools Read/Write/Bash. Tudo sob git.

**Tech Stack:** Python 3.13 · claude-agent-sdk · faster-whisper (CUDA) · piper-tts · sounddevice · pynput · mss + Pillow · pytest

## Global Constraints

- **Python:** 3.13.7 (sistema). Voz processada localmente na RTX 3060 (12GB VRAM).
- **Auth:** subscrição MAX via login do Claude Code CLI. NUNCA usar `ANTHROPIC_API_KEY`. O SDK herda o auth do CLI.
- **Isolamento:** o Agent SDK arranca com `setting_sources=[]` (não carrega settings/CLAUDE.md do utilizador) e `CLAUDE_CONFIG_DIR` a apontar para `.jc-config/`. NUNCA herdar plugins/MCP/skills globais.
- **Tools permitidas (só estas):** `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, mais a custom tool `screenshot`. Nada de MCP externo.
- **Persona:** system prompt vindo de `.jc-config/CLAUDE.md`. Jean Claude NUNCA se identifica como Claude/Anthropic. Fala sempre em estilo caveman ultra.
- **TTS default:** Piper (funciona em 3.13). XTTS é upgrade posterior, fora da v1.
- **Reversibilidade:** commits frequentes. O repositório git já está inicializado.
- **Idioma:** português (voz e texto).

---

## File Structure

```
jean-claude/
  main.py                     # loop push-to-talk, orquestra tudo
  brain/
    __init__.py
    agent.py                  # wrapper Agent SDK (JeanClaude class)
    tools.py                  # custom tool: screenshot
  voice/
    __init__.py
    stt.py                    # faster-whisper (transcribe)
    tts.py                    # interface TTS + PiperTTS
    hotkey.py                 # push-to-talk (grava mic entre press/release)
  vision/
    __init__.py
    screen.py                 # captura de ecrã (mss) -> PNG bytes
  core/
    __init__.py
    config.py                 # paths, constantes, CONFIG_DIR isolado
  skills/                     # tools auto-criadas (vazio na v1, com README)
  memory/
    MEMORY.md                 # índice de memórias
  .jc-config/
    CLAUDE.md                 # persona + caveman ultra + regras (semente)
    settings.json             # tools permitidas
  tests/
    test_config.py
    test_memory.py
    test_stt.py
    test_tts.py
    test_screen.py
    test_agent.py
    assets/
      hello_pt.wav            # áudio de teste p/ STT (gerado na Task 5)
  requirements.txt
  .gitignore
  README.md
```

Cada ficheiro tem uma responsabilidade única. `brain/` = cérebro e tools; `voice/` = entrada/saída de áudio; `vision/` = ecrã; `core/` = config partilhada; `main.py` = orquestração.

---

## Task 1: Scaffold do projeto, dependências e config isolada

**Files:**
- Create: `requirements.txt`, `.gitignore`, `core/__init__.py`, `core/config.py`, `tests/test_config.py`
- Create: `brain/__init__.py`, `voice/__init__.py`, `vision/__init__.py`
- Create: `.jc-config/settings.json`, `skills/README.md`, `memory/MEMORY.md`

**Interfaces:**
- Produces: `core.config` com constantes — `PROJECT_ROOT: Path`, `CONFIG_DIR: Path` (`.jc-config`), `MEMORY_DIR: Path` (`memory`), `SKILLS_DIR: Path` (`skills`), `CLAUDE_MD: Path` (`.jc-config/CLAUDE.md`), `ALLOWED_TOOLS: list[str]`, `WHISPER_MODEL: str = "large-v3"`, `HOTKEY: str = "ctrl+space"`.

- [ ] **Step 1: Criar `requirements.txt`**

```
claude-agent-sdk>=0.1.0
faster-whisper>=1.0.0
piper-tts>=1.2.0
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.26
pynput>=1.7.6
mss>=9.0.1
Pillow>=10.0
pytest>=8.0
```

- [ ] **Step 2: Criar `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
*.wav
!tests/assets/*.wav
models/
*.onnx
*.onnx.json
.jc-config/credentials.json
.pytest_cache/
```

- [ ] **Step 3: Criar packages vazios**

`brain/__init__.py`, `voice/__init__.py`, `vision/__init__.py`, `core/__init__.py` — todos ficheiros vazios.

- [ ] **Step 4: Escrever o teste que falha para `core/config.py`**

```python
# tests/test_config.py
from pathlib import Path
from core import config

def test_paths_exist_and_are_absolute():
    assert config.PROJECT_ROOT.is_absolute()
    assert config.CONFIG_DIR.name == ".jc-config"
    assert config.MEMORY_DIR.name == "memory"
    assert config.CLAUDE_MD == config.CONFIG_DIR / "CLAUDE.md"

def test_allowed_tools_are_basic_only():
    expected = {"Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"}
    assert set(config.ALLOWED_TOOLS) == expected

def test_defaults():
    assert config.WHISPER_MODEL == "large-v3"
    assert config.HOTKEY == "ctrl+space"
```

- [ ] **Step 5: Correr o teste para confirmar que falha**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'core.config'`

- [ ] **Step 6: Implementar `core/config.py`**

```python
# core/config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / ".jc-config"
MEMORY_DIR = PROJECT_ROOT / "memory"
SKILLS_DIR = PROJECT_ROOT / "skills"
CLAUDE_MD = CONFIG_DIR / "CLAUDE.md"

ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]

WHISPER_MODEL = "large-v3"
HOTKEY = "ctrl+space"
```

- [ ] **Step 7: Criar `.jc-config/settings.json`**

```json
{
  "permissions": {
    "allow": ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]
  }
}
```

- [ ] **Step 8: Criar `skills/README.md` e `memory/MEMORY.md`**

`skills/README.md`:
```markdown
# Skills do Jean Claude

Ferramentas e scripts que o Jean Claude cria para si próprio.
Cada skill: um ficheiro `.py` ou `.md` com uma capacidade nova.
Vazio no arranque — cresce com o uso.
```

`memory/MEMORY.md`:
```markdown
# Índice de Memórias — Jean Claude

Uma linha por memória. Cada facto vive num ficheiro `memory/<slug>.md`.

<!-- exemplo: - [Fabio usa RTX 3060](pc-gpu.md) — hardware -->
```

- [ ] **Step 9: Correr o teste para confirmar que passa**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 10: Instalar dependências**

Run: `pip install -r requirements.txt`
Expected: instala sem erros. (Se `piper-tts` falhar em 3.13, ver nota na Task 6.)

- [ ] **Step 11: Commit**

```bash
git add requirements.txt .gitignore core/ brain/__init__.py voice/__init__.py vision/__init__.py .jc-config/settings.json skills/README.md memory/MEMORY.md tests/test_config.py
git commit -m "feat: project scaffold, isolated config, deps"
```

---

## Task 2: Semente do CLAUDE.md (persona + caveman ultra)

**Files:**
- Create: `.jc-config/CLAUDE.md`
- Create: `tests/test_persona.py`

**Interfaces:**
- Produces: `.jc-config/CLAUDE.md` — string carregada como system prompt pela Task 3.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_persona.py
from core import config

def test_claude_md_exists_and_has_persona():
    text = config.CLAUDE_MD.read_text(encoding="utf-8")
    low = text.lower()
    assert "jean claude" in low
    assert "fábio" in low or "fabio" in low
    assert "caveman" in low
    # nunca se identifica como Claude/Anthropic
    assert "nunca" in low and "anthropic" in low
```

- [ ] **Step 2: Correr para confirmar que falha**

Run: `python -m pytest tests/test_persona.py -v`
Expected: FAIL com `FileNotFoundError` em `.jc-config/CLAUDE.md`

- [ ] **Step 3: Escrever `.jc-config/CLAUDE.md`**

```markdown
# És o Jean Claude

Tu és o **Jean Claude**, o super assistente pessoal do Fábio. Corres no PC dele (Windows, RTX 3060).

## Identidade (regra absoluta)
- O teu nome é Jean Claude. NUNCA te identificas como Claude, Anthropic, ou "assistente de IA da Anthropic".
- Se perguntarem quem és: "Sou o Jean Claude, o teu super assistente."
- És leal ao Fábio, direto, competente. Sem tratar por "utilizador" — é o Fábio.

## Como falas — caveman ultra
- Corta artigos (o/a/um), filler (só/realmente/basicamente), cortesias (claro/com certeza), hedging.
- Fragmentos OK. Sinónimos curtos. Termos técnicos exatos e verbatim.
- Padrão: `[coisa] [ação] [motivo]. [próximo passo].`
- Código, comandos, nomes de erro: verbatim, nunca comprimir.
- Avisos de segurança e ações irreversíveis: escreve claro, não caveman.

## O que consegues fazer
- Controlar o PC (Bash): abrir apps, ficheiros, comandos, automações.
- Ver o ecrã: tool `screenshot` quando precisas de ver o que está no monitor.
- Pesquisar web: WebSearch / WebFetch.
- Ler/escrever ficheiros do projeto e do PC.

## Memória
- Ao arrancar, lê `memory/MEMORY.md` (índice).
- Quando aprendes algo permanente sobre o Fábio ou o PC, escreve em `memory/<slug>.md` e adiciona uma linha ao índice.
- Um facto por ficheiro. Human-readable.

## Skills (auto-melhoria)
- Falta-te capacidade? Escreve um script/ferramenta novo em `skills/` e usa-o. Livre.
- Erro acontece? Lê o stacktrace, corrige, regista o que aprendeste em memória.
- Editar o teu próprio core (`core/`, `brain/`, este ficheiro): mostra o diff, pede confirmação ao Fábio, só então commita. Git é a rede de segurança.

## Regras
- Trabalha no diretório do projeto. Commits frequentes.
- Não inventes factos. Não vazes a identidade Claude.
```

- [ ] **Step 4: Correr para confirmar que passa**

Run: `python -m pytest tests/test_persona.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .jc-config/CLAUDE.md tests/test_persona.py
git commit -m "feat: Jean Claude persona seed (CLAUDE.md, caveman ultra)"
```

---

## Task 3: Cérebro — wrapper do Agent SDK

**Files:**
- Create: `brain/agent.py`
- Create: `tests/test_agent.py`

**Interfaces:**
- Consumes: `core.config` (`CLAUDE_MD`, `ALLOWED_TOOLS`, `CONFIG_DIR`, `PROJECT_ROOT`).
- Produces: `brain.agent.JeanClaude` — classe com:
  - `__init__(self, extra_tools: list | None = None)`
  - `async ask(self, prompt: str) -> str` — envia prompt, devolve texto final da resposta.
  - `build_options(self) -> ClaudeAgentOptions` — monta as opções isoladas.

- [ ] **Step 1: Escrever o teste que falha (options isoladas, sem chamada à rede)**

```python
# tests/test_agent.py
import inspect
from brain.agent import JeanClaude
from core import config

def test_options_are_isolated_and_basic():
    jc = JeanClaude()
    opts = jc.build_options()
    # isolamento: não carrega settings do utilizador
    assert opts.setting_sources == []
    # persona vem do CLAUDE.md
    system = opts.system_prompt if isinstance(opts.system_prompt, str) else str(opts.system_prompt)
    assert "Jean Claude" in system
    # só tools básicas
    assert set(opts.allowed_tools) >= set(config.ALLOWED_TOOLS)
    assert "MCP" not in " ".join(opts.allowed_tools)

def test_ask_is_async():
    assert inspect.iscoroutinefunction(JeanClaude.ask)
```

- [ ] **Step 2: Correr para confirmar que falha**

Run: `python -m pytest tests/test_agent.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'brain.agent'`

- [ ] **Step 3: Implementar `brain/agent.py`**

```python
# brain/agent.py
import os
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock
from core import config


class JeanClaude:
    """Cérebro do Jean Claude: wrapper isolado do Claude Agent SDK."""

    def __init__(self, extra_tools=None):
        self.extra_tools = extra_tools or []
        # isola a config: SDK usa o CLAUDE_CONFIG_DIR próprio
        os.environ["CLAUDE_CONFIG_DIR"] = str(config.CONFIG_DIR)

    def _system_prompt(self) -> str:
        return config.CLAUDE_MD.read_text(encoding="utf-8")

    def build_options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(),
            allowed_tools=list(config.ALLOWED_TOOLS) + list(self.extra_tools),
            setting_sources=[],            # NÃO herdar settings globais do utilizador
            cwd=str(config.PROJECT_ROOT),
            permission_mode="acceptEdits", # v1: autónomo no projeto
        )

    async def ask(self, prompt: str) -> str:
        """Envia prompt ao cérebro, devolve o texto final da resposta."""
        reply = []
        async with ClaudeSDKClient(options=self.build_options()) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            reply.append(block.text)
        return "".join(reply).strip()
```

- [ ] **Step 4: Correr para confirmar que passa (unit, sem rede)**

Run: `python -m pytest tests/test_agent.py -v`
Expected: PASS (2 passed)

> Nota: se os nomes de import do SDK diferirem (`AssistantMessage`/`TextBlock`), corre `python -c "import claude_agent_sdk as s; print([x for x in dir(s)])"` e ajusta os imports. A API pública expõe `ClaudeSDKClient`, `ClaudeAgentOptions`, `query`, e os tipos de mensagem.

- [ ] **Step 5: Teste de integração manual (requer `claude login` feito)**

Run:
```bash
python -c "import asyncio; from brain.agent import JeanClaude; print(asyncio.run(JeanClaude().ask('Quem és tu? Responde curto.')))"
```
Expected: resposta em caveman ultra que se identifica como **Jean Claude** (nunca Claude/Anthropic). Se falhar por auth: correr `claude login` primeiro.

- [ ] **Step 6: Commit**

```bash
git add brain/agent.py tests/test_agent.py
git commit -m "feat: Jean Claude brain (isolated Agent SDK wrapper)"
```

---

## Task 4: Memória — ler índice e escrever factos

**Files:**
- Create: `brain/memory.py`
- Create: `tests/test_memory.py`

**Interfaces:**
- Consumes: `core.config` (`MEMORY_DIR`).
- Produces: `brain.memory` com:
  - `read_index() -> str` — conteúdo de `MEMORY.md`.
  - `write_memory(slug: str, title: str, body: str, mem_type: str) -> Path` — cria `memory/<slug>.md` com frontmatter e acrescenta linha ao índice.

> Nota: na prática o próprio Jean Claude escreve memórias via a tool Write. Este módulo dá helpers testáveis e é usado pelo `main.py` para injetar o índice no arranque.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_memory.py
import tempfile
from pathlib import Path
import brain.memory as memory
from core import config

def test_write_and_index(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path)
    (tmp_path / "MEMORY.md").write_text("# Índice\n", encoding="utf-8")

    p = memory.write_memory("pc-gpu", "GPU do Fabio", "RTX 3060, 12GB VRAM.", "pc")
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "RTX 3060" in content
    assert "type: pc" in content

    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "pc-gpu.md" in index
    assert "GPU do Fabio" in index
```

- [ ] **Step 2: Correr para confirmar que falha**

Run: `python -m pytest tests/test_memory.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'brain.memory'`

- [ ] **Step 3: Implementar `brain/memory.py`**

```python
# brain/memory.py
from pathlib import Path
from core import config


def read_index() -> str:
    idx = config.MEMORY_DIR / "MEMORY.md"
    return idx.read_text(encoding="utf-8") if idx.exists() else ""


def write_memory(slug: str, title: str, body: str, mem_type: str) -> Path:
    path = config.MEMORY_DIR / f"{slug}.md"
    frontmatter = (
        "---\n"
        f"name: {slug}\n"
        f"description: {title}\n"
        f"type: {mem_type}\n"
        "---\n\n"
    )
    path.write_text(frontmatter + body.strip() + "\n", encoding="utf-8")

    idx = config.MEMORY_DIR / "MEMORY.md"
    line = f"- [{title}]({slug}.md) — {mem_type}\n"
    with idx.open("a", encoding="utf-8") as f:
        f.write(line)
    return path
```

- [ ] **Step 4: Correr para confirmar que passa**

Run: `python -m pytest tests/test_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brain/memory.py tests/test_memory.py
git commit -m "feat: markdown memory helpers (index + write)"
```

---

## Task 5: STT — transcrição com faster-whisper

**Files:**
- Create: `voice/stt.py`
- Create: `tests/test_stt.py`
- Create: `tests/assets/hello_pt.wav` (gerado no Step 1)

**Interfaces:**
- Consumes: `core.config` (`WHISPER_MODEL`).
- Produces: `voice.stt` com:
  - `transcribe_file(path: str) -> str` — transcreve um WAV, devolve texto.
  - `get_model()` — devolve (e cacheia) o modelo faster-whisper na GPU.

- [ ] **Step 1: Gerar um WAV de teste com fala em português**

Run (usa Piper se já instalado, senão grava manualmente):
```bash
python -c "import soundfile as sf, numpy as np; sr=16000; t=np.linspace(0,1,sr); sf.write('tests/assets/hello_pt.wav', 0.1*np.sin(2*np.pi*220*t), sr)"
```
> Nota: este WAV é um tom, não fala. Serve para testar que `transcribe_file` corre sem crashar e devolve `str`. Para um teste de conteúdo real, substituir depois por uma gravação de voz a dizer "olá Jean Claude".

- [ ] **Step 2: Escrever o teste que falha**

```python
# tests/test_stt.py
from voice import stt

def test_transcribe_returns_string():
    result = stt.transcribe_file("tests/assets/hello_pt.wav")
    assert isinstance(result, str)
```

- [ ] **Step 3: Correr para confirmar que falha**

Run: `python -m pytest tests/test_stt.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'voice.stt'`

- [ ] **Step 4: Implementar `voice/stt.py`**

```python
# voice/stt.py
from faster_whisper import WhisperModel
from core import config

_model = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        # tenta GPU (float16); cai para CPU se CUDA indisponível
        try:
            _model = WhisperModel(config.WHISPER_MODEL, device="cuda", compute_type="float16")
        except Exception:
            _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def transcribe_file(path: str) -> str:
    model = get_model()
    segments, _ = model.transcribe(path, language="pt", beam_size=5)
    return " ".join(seg.text for seg in segments).strip()
```

- [ ] **Step 5: Correr para confirmar que passa**

Run: `python -m pytest tests/test_stt.py -v`
Expected: PASS (primeira corrida descarrega o modelo `large-v3` ~3GB; pode demorar).

- [ ] **Step 6: Commit**

```bash
git add voice/stt.py tests/test_stt.py tests/assets/hello_pt.wav
git commit -m "feat: STT via faster-whisper (GPU, pt)"
```

---

## Task 6: TTS — interface plugável + Piper

**Files:**
- Create: `voice/tts.py`
- Create: `tests/test_tts.py`

**Interfaces:**
- Produces: `voice.tts` com:
  - `TTS` — classe base abstrata: método `speak(self, text: str) -> None` e `synth(self, text: str, out_path: str) -> str`.
  - `PiperTTS(TTS)` — implementação com Piper.
  - `get_tts() -> TTS` — factory que devolve a instância default (Piper na v1).

- [ ] **Step 1: Descarregar uma voz Piper em português**

Run:
```bash
mkdir -p models
python -m piper.download_voices pt_PT-tugao-medium --data-dir models
```
> Se o comando de download diferir na versão instalada, descarregar manualmente `pt_PT-tugao-medium.onnx` e `.onnx.json` de https://huggingface.co/rhasspy/piper-voices para `models/`. Se `piper-tts` não instalar em Python 3.13, ver nota no fim desta task.

- [ ] **Step 2: Escrever o teste que falha**

```python
# tests/test_tts.py
import os
from voice import tts

def test_synth_creates_wav(tmp_path):
    engine = tts.get_tts()
    out = str(tmp_path / "out.wav")
    path = engine.synth("olá Fábio, sou o Jean Claude", out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0

def test_get_tts_returns_tts_instance():
    assert isinstance(tts.get_tts(), tts.TTS)
```

- [ ] **Step 3: Correr para confirmar que falha**

Run: `python -m pytest tests/test_tts.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'voice.tts'`

- [ ] **Step 4: Implementar `voice/tts.py`**

```python
# voice/tts.py
import wave
from pathlib import Path
from abc import ABC, abstractmethod
import sounddevice as sd
import soundfile as sf
from piper import PiperVoice
from core import config

_VOICE_PATH = config.PROJECT_ROOT / "models" / "pt_PT-tugao-medium.onnx"


class TTS(ABC):
    @abstractmethod
    def synth(self, text: str, out_path: str) -> str:
        """Sintetiza texto para um ficheiro WAV; devolve o caminho."""

    def speak(self, text: str) -> None:
        """Sintetiza e toca em voz alta."""
        tmp = str(config.PROJECT_ROOT / "_jc_tts_tmp.wav")
        self.synth(text, tmp)
        data, sr = sf.read(tmp)
        sd.play(data, sr)
        sd.wait()
        Path(tmp).unlink(missing_ok=True)


class PiperTTS(TTS):
    def __init__(self, voice_path: Path = _VOICE_PATH):
        self.voice = PiperVoice.load(str(voice_path))

    def synth(self, text: str, out_path: str) -> str:
        with wave.open(out_path, "wb") as wav:
            self.voice.synthesize(text, wav)
        return out_path


def get_tts() -> TTS:
    return PiperTTS()
```

- [ ] **Step 5: Correr para confirmar que passa**

Run: `python -m pytest tests/test_tts.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add voice/tts.py tests/test_tts.py
git commit -m "feat: TTS interface + Piper (pt_PT)"
```

> **Fallback se `piper-tts` não instalar em Python 3.13:** trocar a implementação de `PiperTTS.synth` por um subprocess ao binário Piper (`piper.exe --model models/pt_PT-tugao-medium.onnx --output_file out.wav`), mantendo a mesma interface `TTS`. O resto do sistema não muda porque depende só de `TTS.synth/speak`.

---

## Task 7: Vision — custom tool `screenshot`

**Files:**
- Create: `vision/screen.py`
- Create: `brain/tools.py`
- Create: `tests/test_screen.py`
- Modify: `brain/agent.py` (registar o servidor de tools in-process)

**Interfaces:**
- Consumes: `mss`, `claude_agent_sdk` (`tool`, `create_sdk_mcp_server`).
- Produces:
  - `vision.screen.capture_png() -> bytes` — PNG do ecrã principal.
  - `brain.tools.screenshot_server` — servidor MCP in-process com a tool `screenshot`.
  - `brain.tools.SCREENSHOT_TOOL_NAME: str` — nome permitido a passar ao SDK.

- [ ] **Step 1: Escrever o teste que falha para a captura**

```python
# tests/test_screen.py
from vision import screen

def test_capture_png_returns_png_bytes():
    data = screen.capture_png()
    assert isinstance(data, bytes)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # magic bytes PNG
```

- [ ] **Step 2: Correr para confirmar que falha**

Run: `python -m pytest tests/test_screen.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'vision.screen'`

- [ ] **Step 3: Implementar `vision/screen.py`**

```python
# vision/screen.py
import io
import mss
from PIL import Image


def capture_png() -> bytes:
    """Captura o ecrã principal e devolve PNG em bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # monitor principal
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
```

- [ ] **Step 4: Correr para confirmar que passa**

Run: `python -m pytest tests/test_screen.py -v`
Expected: PASS

- [ ] **Step 5: Implementar `brain/tools.py` (custom tool que devolve a imagem ao modelo)**

```python
# brain/tools.py
import base64
from claude_agent_sdk import tool, create_sdk_mcp_server
from vision import screen

SCREENSHOT_TOOL_NAME = "mcp__jc__screenshot"


@tool("screenshot", "Captura o ecrã atual do Fábio e devolve a imagem para o Jean Claude ver.", {})
async def screenshot(args):
    png = screen.capture_png()
    b64 = base64.standard_b64encode(png).decode("ascii")
    return {
        "content": [
            {"type": "image", "data": b64, "mimeType": "image/png"}
        ]
    }


screenshot_server = create_sdk_mcp_server(name="jc", version="1.0.0", tools=[screenshot])
```

> Nota: confirmar a assinatura de `tool`/`create_sdk_mcp_server` na versão instalada com `python -c "import claude_agent_sdk as s; help(s.tool)"`. Se o retorno de imagem não for suportado no formato acima, alternativa: a tool grava o PNG em disco e devolve o caminho como texto; o Jean Claude lê-o com a tool Read (que suporta imagens).

- [ ] **Step 6: Registar o servidor de tools em `brain/agent.py`**

Modificar `build_options` para incluir o MCP server in-process e permitir a tool:

```python
# brain/agent.py — dentro de build_options(), atualizar o ClaudeAgentOptions:
from brain.tools import screenshot_server, SCREENSHOT_TOOL_NAME

# ...
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(),
            allowed_tools=list(config.ALLOWED_TOOLS) + [SCREENSHOT_TOOL_NAME] + list(self.extra_tools),
            mcp_servers={"jc": screenshot_server},
            setting_sources=[],
            cwd=str(config.PROJECT_ROOT),
            permission_mode="acceptEdits",
        )
```

- [ ] **Step 7: Atualizar `tests/test_agent.py` para o novo tool**

Adicionar ao `test_options_are_isolated_and_basic`:
```python
    from brain.tools import SCREENSHOT_TOOL_NAME
    assert SCREENSHOT_TOOL_NAME in opts.allowed_tools
```

- [ ] **Step 8: Correr os testes do agent e screen**

Run: `python -m pytest tests/test_agent.py tests/test_screen.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add vision/screen.py brain/tools.py brain/agent.py tests/test_screen.py tests/test_agent.py
git commit -m "feat: screen vision custom tool (screenshot -> multimodal)"
```

---

## Task 8: Hotkey push-to-talk

**Files:**
- Create: `voice/hotkey.py`
- Create: `tests/test_hotkey.py`

**Interfaces:**
- Consumes: `sounddevice`, `soundfile`, `pynput`, `core.config` (`HOTKEY`).
- Produces: `voice.hotkey` com:
  - `record_between_keys(out_path: str, samplerate: int = 16000) -> str` — grava do mic enquanto uma tecla está premida; para ao soltar; devolve o caminho do WAV.
  - `save_wav(frames, samplerate, out_path) -> str` — helper testável que escreve WAV.

- [ ] **Step 1: Escrever o teste que falha (helper puro, sem hardware)**

```python
# tests/test_hotkey.py
import numpy as np, soundfile as sf
from voice import hotkey

def test_save_wav_writes_file(tmp_path):
    frames = np.zeros((16000, 1), dtype="float32")
    out = str(tmp_path / "rec.wav")
    path = hotkey.save_wav(frames, 16000, out)
    data, sr = sf.read(path)
    assert sr == 16000
    assert len(data) == 16000
```

- [ ] **Step 2: Correr para confirmar que falha**

Run: `python -m pytest tests/test_hotkey.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'voice.hotkey'`

- [ ] **Step 3: Implementar `voice/hotkey.py`**

```python
# voice/hotkey.py
import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard
from core import config


def save_wav(frames, samplerate: int, out_path: str) -> str:
    data = np.concatenate(frames) if isinstance(frames, list) else frames
    sf.write(out_path, data, samplerate)
    return out_path


def record_between_keys(out_path: str, samplerate: int = 16000) -> str:
    """Grava do microfone enquanto a HOTKEY estiver premida. Para ao soltar."""
    q: "queue.Queue" = queue.Queue()
    recording = {"active": False, "done": False}

    def audio_cb(indata, frames, time, status):
        if recording["active"]:
            q.put(indata.copy())

    # deteta a tecla final da HOTKEY (ex.: "ctrl+space" -> space com ctrl)
    def on_press(key):
        if key == keyboard.Key.space:
            recording["active"] = True

    def on_release(key):
        if key == keyboard.Key.space and recording["active"]:
            recording["active"] = False
            recording["done"] = True
            return False  # para o listener

    frames = []
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32", callback=audio_cb):
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
            while not q.empty():
                frames.append(q.get())

    if not frames:
        frames = [np.zeros((1, 1), dtype="float32")]
    return save_wav(frames, samplerate, out_path)
```

> Nota: para v1 a hotkey é fixada em `space` (segurar para falar). Se colidir com uso normal do teclado, trocar por uma tecla dedicada (ex.: `keyboard.Key.f9`) num passo posterior. `config.HOTKEY` documenta a intenção.

- [ ] **Step 4: Correr para confirmar que passa**

Run: `python -m pytest tests/test_hotkey.py -v`
Expected: PASS

- [ ] **Step 5: Teste manual de gravação (opcional, requer mic)**

Run:
```bash
python -c "from voice.hotkey import record_between_keys; print('Segura ESPAÇO e fala...'); record_between_keys('tests/assets/manual.wav'); print('gravado')"
```
Expected: grava enquanto seguras espaço, cria `tests/assets/manual.wav`.

- [ ] **Step 6: Commit**

```bash
git add voice/hotkey.py tests/test_hotkey.py
git commit -m "feat: push-to-talk recording (hold space)"
```

---

## Task 9: Loop principal — wiring end-to-end

**Files:**
- Create: `main.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `voice.hotkey`, `voice.stt`, `voice.tts`, `brain.agent`, `brain.memory`, `core.config`.
- Produces: `main.run()` — loop interativo.

- [ ] **Step 1: Implementar `main.py`**

```python
# main.py
import asyncio
from pathlib import Path
from core import config
from brain.agent import JeanClaude
from brain import memory
from voice import stt, tts, hotkey

REC_PATH = str(config.PROJECT_ROOT / "_jc_rec.wav")


async def run():
    jc = JeanClaude()
    speaker = tts.get_tts()

    # injeta o índice de memória no arranque
    index = memory.read_index()
    print("Jean Claude pronto. Segura ESPAÇO para falar. Ctrl+C para sair.\n")

    while True:
        try:
            input_hint = "[segura ESPAÇO e fala, larga quando acabares] "
            print(input_hint)
            hotkey.record_between_keys(REC_PATH)

            texto = stt.transcribe_file(REC_PATH)
            if not texto.strip():
                print("(nada ouvido)\n")
                continue
            print(f"Fábio: {texto}")

            prompt = f"[memória índice]\n{index}\n\n[Fábio disse]\n{texto}"
            resposta = await jc.ask(prompt)
            print(f"Jean Claude: {resposta}\n")

            speaker.speak(resposta)
        except KeyboardInterrupt:
            print("\nJean Claude off.")
            break
        finally:
            Path(REC_PATH).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 2: Escrever o `README.md`**

```markdown
# Jean Claude

Super assistente pessoal de desktop. Voz push-to-talk, visão de ecrã, memória, cérebro Claude isolado com identidade própria.

## Setup
1. `pip install -r requirements.txt`
2. `claude login` (subscrição MAX — o cérebro usa este auth, sem API key)
3. Descarregar voz Piper: `python -m piper.download_voices pt_PT-tugao-medium --data-dir models`

## Correr
`python main.py`

Segura **ESPAÇO**, fala, larga. Jean Claude responde por voz e texto.

## Estrutura
- `brain/` cérebro (Agent SDK) + tools (screenshot)
- `voice/` STT (whisper), TTS (piper), push-to-talk
- `vision/` captura de ecrã
- `memory/` factos persistentes (markdown)
- `skills/` ferramentas que o Jean Claude cria
- `.jc-config/` config isolada + CLAUDE.md (persona)

## Auto-melhoria
Jean Claude cria skills livremente, corrige erros, e — com confirmação — edita o próprio core. Tudo sob git: `git revert` desfaz qualquer coisa.
```

- [ ] **Step 3: Smoke test do loop (manual, requer auth + mic + voz Piper)**

Run: `python main.py`
Expected: arranca, imprime "Jean Claude pronto". Segurar espaço e dizer "quem és tu" → transcreve, responde como Jean Claude em caveman ultra por texto e voz.

- [ ] **Step 4: Correr toda a suite de testes**

Run: `python -m pytest -v`
Expected: todos os testes unitários passam.

- [ ] **Step 5: Commit**

```bash
git add main.py README.md
git commit -m "feat: main push-to-talk loop (end-to-end v1)"
```

---

## Task 10: Verificação dos critérios de sucesso

**Files:** nenhum ficheiro novo — validação end-to-end contra o spec.

- [ ] **Step 1: Persona** — perguntar por voz "quem és tu"; confirmar que responde **Jean Claude**, caveman ultra, nunca "Claude/Anthropic".
- [ ] **Step 2: Controlo do PC** — pedir "abre o notepad" ou "cria um ficheiro teste.txt no ambiente de trabalho"; confirmar execução via Bash.
- [ ] **Step 3: Visão** — pedir "olha para o meu ecrã e diz o que vês"; confirmar que usa a tool `screenshot` e descreve.
- [ ] **Step 4: Memória** — dizer um facto ("o meu editor favorito é o VS Code"); confirmar que escreve em `memory/` e o índice cresce. Reiniciar e confirmar que se lembra.
- [ ] **Step 5: Skill nova** — pedir uma capacidade que exija script; confirmar que cria ficheiro em `skills/`.
- [ ] **Step 6: Isolamento** — confirmar `setting_sources=[]` e `CLAUDE_CONFIG_DIR=.jc-config`; nenhum plugin/MCP global carregado.
- [ ] **Step 7: Commit final**

```bash
git add -A && git commit -m "chore: v1 acceptance checks passed"
```

---

## Notas de risco (da spec)

- **Python 3.13 + Piper:** se o pacote não instalar, usar o binário Piper via subprocess (Task 6, nota). XTTS fica para fase posterior (provavelmente venv 3.11).
- **VRAM:** `large-v3` (~3GB) + Piper (leve) cabem nos 12GB. Se apertar quando XTTS entrar, baixar Whisper para `medium`.
- **Auth:** se o SDK pedir API key, confirmar que `claude login` foi feito e que `ANTHROPIC_API_KEY` NÃO está no ambiente (o SDK deve usar o auth do CLI/subscrição).
- **Vazamento de identidade:** o teste `test_persona.py` e o Step 1 da Task 10 guardam contra isto. Reforçar o CLAUDE.md se o modelo escorregar.
```
