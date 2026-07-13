# brain/tools.py
import base64
import contextlib
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


screenshot_server = create_sdk_mcp_server(
    name="jc", version="1.0.0", tools=[screenshot, abrir_consola]
)

JC_TOOL_NAMES = [SCREENSHOT_TOOL_NAME, CONSOLE_TOOL_NAME]
