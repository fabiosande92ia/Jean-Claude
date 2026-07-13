# core/config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- caveman -----------------------------------------------------------------
# O estilo do Jean Claude vem do plugin caveman REAL (o mesmo do Claude Code do
# Fábio), não de regras à mão no CLAUDE.md. O nível vai por env var
# (CAVEMAN_DEFAULT_MODE) só no subprocess do SDK: as sessões do Fábio neste
# repo não são afetadas.
CAVEMAN_MODE = "ultra"
_CAVEMAN_CACHE = Path.home() / ".claude" / "plugins" / "cache" / "caveman" / "caveman"


def caveman_plugin_path() -> Path | None:
    """
    Diretório do plugin caveman mais recente na cache do Claude Code do Fábio.
    None se não estiver instalado — o Jean Claude fala normal, ninguém morre.
    (A cache muda de hash a cada update do plugin: daí resolver em runtime.)
    """
    if not _CAVEMAN_CACHE.is_dir():
        return None
    candidatos = [
        p for p in _CAVEMAN_CACHE.iterdir()
        if (p / ".claude-plugin" / "plugin.json").is_file()
    ]
    return max(candidatos, key=lambda p: p.stat().st_mtime, default=None)
CONFIG_DIR = PROJECT_ROOT / ".jc-config"
MEMORY_DIR = PROJECT_ROOT / "memory"
SKILLS_DIR = PROJECT_ROOT / "skills"
CLAUDE_MD = CONFIG_DIR / "CLAUDE.md"

ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]

WHISPER_MODEL = "large-v3"

# Tecla de push-to-talk. Fonte ÚNICA de verdade: voice.hotkey.resolve() traduz este
# nome para a tecla real *e* para o rótulo que a UI mostra no botão. Antes isto dizia
# "space" enquanto o main.py usava numpad e a UI escrevia "Numpad -" à mão — três
# sítios, uma verdade, dois a mentir. Nomes válidos: voice.hotkey.KEYS.
HOTKEY = "numpad_minus"

# Conversa persistida entre arranques. Fica em .jc-config (gitignored): é privada.
CONVERSA_FILE = CONFIG_DIR / "conversas.jsonl"

# Posição/tamanho da janela entre arranques. Mesmo sítio da conversa: é estado
# local desta máquina, não configuração do projeto.
UI_STATE_FILE = CONFIG_DIR / "ui.json"

# Pedido de alteração ao código do próprio JC, entregue à consola Claude Code por
# ficheiro. Por ficheiro e não por argumento: texto arbitrário dentro de um
# `cmd /c claude "..."` é injeção de comandos.
PEDIDO_CONSOLA = CONFIG_DIR / "pedido-consola.md"

# Resumo final que a consola escreve antes de fechar, e log bruto (stdout/stderr)
# como fallback se o resumo não existir. Consumidos (apagados) no arranque
# seguinte da app — não podem repetir-se.
CONSOLA_ULTIMA = CONFIG_DIR / "consola-ultima.md"
CONSOLA_LOG = CONFIG_DIR / "consola-log.txt"
HISTORY_SIZE = 5      # trocas recentes injetadas no prompt do agente
HISTORY_REPLAY = 20   # mensagens recarregadas para o chat ao arrancar

# Abaixo deste pico de RMS, a gravação é silêncio: o mic está mudo ou é o errado.
MIC_SILENCE_THRESHOLD = 0.005
