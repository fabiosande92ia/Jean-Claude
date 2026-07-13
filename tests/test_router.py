import brain.router as router


def test_modelo_id_mapeia_complexidades():
    assert router.modelo_id("baixa") == "claude-haiku-4-5-20251001"
    assert router.modelo_id("media") == "claude-sonnet-5"
    assert router.modelo_id("alta") == "claude-opus-4-8"


def test_modelo_id_fallback_media():
    assert router.modelo_id("desconhecida") == "claude-sonnet-5"
    assert router.modelo_id("") == "claude-sonnet-5"


def test_nome_curto():
    assert router.nome_curto("claude-haiku-4-5-20251001") == "haiku"
    assert router.nome_curto("claude-sonnet-5") == "sonnet"
    assert router.nome_curto("claude-opus-4-8") == "opus"
    assert router.nome_curto("outro-qualquer") == "outro-qualquer"


def test_escolher_modelo_comando_curto_e_baixa():
    assert router.escolher_modelo("abre o spotify") == "baixa"
    assert router.escolher_modelo("aumenta o volume") == "baixa"
    assert router.escolher_modelo("que horas são") == "baixa"


def test_escolher_modelo_pedido_medio_e_media():
    assert router.escolher_modelo(
        "resume-me o que fizemos hoje no projeto, com detalhe, para o diario de bordo"
    ) == "media"
    assert router.escolher_modelo("porque é que o céu é azul?") == "media"


def test_escolher_modelo_vazio_e_media():
    assert router.escolher_modelo("") == "media"
    assert router.escolher_modelo("   ") == "media"


def test_escolher_modelo_nunca_devolve_alta():
    for t in ["abre o spotify", "refactor gigante a tudo", "analisa a arquitetura toda",
              "", "reescreve o main.py inteiro por favor com muito detalhe e cuidado"]:
        assert router.escolher_modelo(t) in ("baixa", "media")
