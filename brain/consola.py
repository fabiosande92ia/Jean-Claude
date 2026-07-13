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
