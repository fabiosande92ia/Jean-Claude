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
