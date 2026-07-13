# core/config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / ".jc-config"
MEMORY_DIR = PROJECT_ROOT / "memory"
SKILLS_DIR = PROJECT_ROOT / "skills"
CLAUDE_MD = CONFIG_DIR / "CLAUDE.md"

ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]

WHISPER_MODEL = "large-v3"
HOTKEY = "space"
