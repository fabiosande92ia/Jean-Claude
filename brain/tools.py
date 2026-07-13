# brain/tools.py
import base64
import contextlib
import os
import shutil
import subprocess
import sys
import threading
from claude_agent_sdk import tool, create_sdk_mcp_server
from core import config
from vision import screen

SCREENSHOT_TOOL_NAME = "mcp__jc__screenshot"
CONSOLE_TOOL_NAME = "mcp__jc__abrir_consola"


def _texto(msg: str, erro: bool = False) -> dict:
    out = {"content": [{"type": "text", "text": msg}]}
    if erro:
        out["is_error"] = True
    return out


@tool("screenshot", "Captura o ecrã atual do Fábio e devolve a imagem para o Jean Claude ver.", {})
async def screenshot(args):
    jpeg = screen.capture_jpeg()
    b64 = base64.standard_b64encode(jpeg).decode("ascii")
    return {
        "content": [
            {"type": "image", "data": b64, "mimeType": "image/jpeg"}
        ]
    }


# Prompt FIXO passado à consola: o texto do Fábio nunca entra no comando (injeção
# de shell via `cmd /c`); vai por ficheiro e a consola lê-o de lá.
_PROMPT_CONSOLA = (
    "Le o ficheiro .jc-config/pedido-consola.md e executa o pedido que la esta. "
    "No fim corre os testes e escreve um resumo final (o que mudou e se os testes "
    "passaram) no ficheiro .jc-config/consola-ultima.md — a app do Jean Claude "
    "reinicia-se sozinha quando esta consola fechar e mostra esse resumo ao Fabio."
)

# Contexto injetado por main.py (ver `configurar_reinicio`): a thread que espera a
# consola acabar não tem acesso direto à ui_queue nem ao evento de reinício — o
# módulo é importado antes de a app montar essas peças.
_restart_ctx = {"ui_queue": None, "sinalizar": None}


def configurar_reinicio(ui_queue, sinalizar_reinicio) -> None:
    """Liga `abrir_consola` ao resto da app: `ui_queue` para pedir o encerramento
    limpo (mesmo caminho do "Sair" do tray) e `sinalizar_reinicio` para o main()
    saber, depois do mainloop acabar, que tem de relançar o processo."""
    _restart_ctx["ui_queue"] = ui_queue
    _restart_ctx["sinalizar"] = sinalizar_reinicio


def ler_resumo_consola_pendente() -> str | None:
    """Lê (e consome) o resumo deixado pela última consola, se houver.

    Prioridade ao resumo escrito pela consola; se não existir (ex.: a consola
    rebentou antes de o escrever), cai para o log bruto de stdout/stderr. Ambos
    os ficheiros são apagados de seguida — nunca repetem no arranque seguinte.
    """
    resumo = None
    if config.CONSOLA_ULTIMA.exists():
        resumo = config.CONSOLA_ULTIMA.read_text(encoding="utf-8", errors="replace").strip() or None
    elif config.CONSOLA_LOG.exists():
        resumo = config.CONSOLA_LOG.read_text(encoding="utf-8", errors="replace").strip() or None
    for caminho in (config.CONSOLA_ULTIMA, config.CONSOLA_LOG):
        with contextlib.suppress(OSError):
            caminho.unlink()
    return resumo


@tool(
    "abrir_consola",
    "Abre uma consola Claude Code no projeto do Jean Claude que executa o pedido do Fábio "
    "sozinha, sem pedir aprovações, e sem mexer na app em execução. Usa isto SEMPRE que o "
    "Fábio pedir mudanças ao código do próprio Jean Claude. Passa em `pedido` o que ele "
    "quer, com o contexto todo necessário — a consola não vê esta conversa. Quando a "
    "consola acabar, a app reinicia-se sozinha e mostra ao Fábio o resumo do que foi feito.",
    {"pedido": str},
)
async def abrir_consola(args):
    pedido = (args.get("pedido") or "").strip()
    if not pedido:
        return _texto("Falta o `pedido`: descreve o que o Fábio quer mudar.", erro=True)
    if sys.platform != "win32":
        return _texto("abrir_consola só está implementada em Windows.", erro=True)
    if shutil.which("claude") is None:
        return _texto(
            "Claude Code não está no PATH — instala com: npm install -g @anthropic-ai/claude-code",
            erro=True,
        )
    try:
        config.PEDIDO_CONSOLA.parent.mkdir(parents=True, exist_ok=True)
        config.PEDIDO_CONSOLA.write_text(
            "# Pedido do Fábio (entregue pelo Jean Claude em execução)\n\n"
            + pedido + "\n",
            encoding="utf-8",
        )
        # A consola tem de abrir com a config GLOBAL do Fábio (plugins, skills,
        # superpowers) — não com a config isolada do JC. Se o CLAUDE_CONFIG_DIR
        # do processo apontar para a nossa .jc-config, é contaminação nossa e
        # sai; se o Fábio o tiver definido para outro sítio, é escolha dele e fica.
        env = os.environ.copy()
        if env.get("CLAUDE_CONFIG_DIR") == str(config.CONFIG_DIR):
            del env["CLAUDE_CONFIG_DIR"]
        # stdout/stderr num ficheiro (não herdados da consola): é o fallback do
        # resumo em consola-ultima.md, e "w" trunca o log da vez anterior.
        config.CONSOLA_LOG.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(config.CONSOLA_LOG, "w", encoding="utf-8")
        try:
            # `/c` (não `/k`): a consola fecha sozinha quando o claude acabar —
            # é o que a thread abaixo espera para disparar o reinício da app.
            proc = subprocess.Popen(
                ["cmd", "/c", "claude", "--dangerously-skip-permissions", _PROMPT_CONSOLA],
                cwd=str(config.PROJECT_ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            log_fh.close()
            raise
    except Exception as e:
        return _texto(f"Falha a abrir a consola: {type(e).__name__}: {e}", erro=True)

    def _esperar_fim_e_reiniciar(proc=proc, log_fh=log_fh):
        proc.wait()
        with contextlib.suppress(OSError):
            log_fh.close()
        sinalizar = _restart_ctx["sinalizar"]
        if sinalizar:
            sinalizar()
        ui_queue = _restart_ctx["ui_queue"]
        if ui_queue:
            # Mesmo caminho do "Sair" do tray: encerramento limpo (worker, hotkey,
            # geometria guardada) — nunca os._exit a meio de um job em curso.
            ui_queue.put(("tray", "sair"))

    threading.Thread(target=_esperar_fim_e_reiniciar, daemon=True).start()
    return _texto(
        "Consola Claude Code aberta, em modo automático, a trabalhar no pedido. "
        "Quando acabar a app reinicia-se sozinha e mostra o resumo ao Fábio."
    )


screenshot_server = create_sdk_mcp_server(
    name="jc", version="1.0.0", tools=[screenshot, abrir_consola]
)

JC_TOOL_NAMES = [SCREENSHOT_TOOL_NAME, CONSOLE_TOOL_NAME]
