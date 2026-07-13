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
