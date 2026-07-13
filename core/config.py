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

# --- TTS ---------------------------------------------------------------------
# Motor: edge_vc (default) | edge | xtts.
#   edge_vc: Duarte europeu (Edge-TTS) + FreeVC -> timbre do JeanClaude. PT-PT
#            garantido + voz do Jean Claude. Online (Edge) + GPU (FreeVC).
#   edge   : só o Duarte europeu, sem clonagem.
#   xtts   : XTTS-v2 local clona o JeanClaude, mas o "pt" puxa para pt-BR.
TTS_ENGINE = "edge_vc"

# Voz Edge (base do edge/edge_vc). Duarte = português europeu.
EDGE_VOICE = "pt-PT-DuarteNeural"
EDGE_RATE = "+0%"
# Duarte base ~121 Hz; JeanClaude ~103 Hz. FreeVC preserva o tom da fonte, logo
# baixar o Duarte para o tom dele aproxima o resultado da voz clonada (-20Hz ≈ 104).
EDGE_PITCH = "-20Hz"
EDGE_VOLUME = "+0%"

# --- TTS: efeito robô -------------------------------------------------------
# FX "voz de robô" aplicado a QUALQUER motor (edge/edge_vc/xtts), depois da
# síntese e antes de tocar, em voice.tts.TTS.speak(). Ring modulation (multiplica
# a voz por um seno) + bitcrush (quantiza -> som digital). Desligado por default.
# Preset atual: B "metálico" + voz fina (+6 semitons). Escolhido a ouvir demos.
TTS_ROBOT = True
TTS_ROBOT_CARRIER_HZ = 140.0  # seno da ring mod: 40-60 grave/Dalek, 150+ metálico
TTS_ROBOT_CRUSH_BITS = 7      # bits do bitcrush: menor = mais digital/áspero
TTS_ROBOT_MIX = 0.85          # 0..1 dry/wet: 1 = só robô, 0 = voz limpa
TTS_ROBOT_PITCH_SEMITONES = 6.0  # sobe o tom (voz mais fina); 0 = tom original

# Amostra de voz alvo (timbre a clonar no edge_vc/xtts). WAV e não MP3: FreeVC/XTTS
# carregam-na via torchaudio, que no Windows sem ffmpeg não descodifica MP3.
# JeanClaude.wav é derivado do MP3 (mono) e gitignored; o MP3 é a fonte versionada
# e voice.tts gera o WAV na 1ª carga se ele faltar.
XTTS_SPEAKER_WAV = PROJECT_ROOT / "models" / "JeanClaude.wav"
XTTS_SPEAKER_MP3 = PROJECT_ROOT / "JeanClaude.mp3"
XTTS_LANGUAGE = "pt"

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
