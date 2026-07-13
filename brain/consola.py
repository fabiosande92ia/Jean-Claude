"""
Consola Claude Code em segundo plano.

`ConsoleRunner` é dono do subprocesso escondido: arranca-o, lê o stream-json numa
thread e empurra linhas amigáveis para o ui_queue; no fim lê o resumo e avisa a
app. `parse_evento` é puro (testável sem processo).
"""

import json
import os
import shutil
import subprocess
import sys
import threading

from core import config
from brain import router

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


_RESERVANDO = object()   # sentinel: reserva o slot sob lock antes do Popen, fecha a janela TOCTOU


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
            self._proc = _RESERVANDO   # reserva já, sob lock: ninguém mais passa o guard

        if sys.platform != "win32":
            with self._lock:
                self._proc = None
            return False, "A consola de desenvolvimento só está implementada em Windows."
        if shutil.which("claude") is None:
            with self._lock:
                self._proc = None
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
            with self._lock:
                self._proc = None
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
