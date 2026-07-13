# tests/test_tools.py
import asyncio
import brain.tools as tools
from core import config


def _run(args):
    return asyncio.run(tools.abrir_consola.handler(args))


def _texto_de(resultado) -> str:
    return resultado["content"][0]["text"]


class RunnerFalso:
    def __init__(self, resultado=(True, "")):
        self.resultado = resultado
        self.chamadas = []
    def start(self, pedido, complexidade):
        self.chamadas.append((pedido, complexidade))
        return self.resultado


def test_abrir_consola_delega_no_runner_com_complexidade():
    runner = RunnerFalso((True, ""))
    tools.configurar_consola(runner)
    res = _run({"pedido": "muda a cor do botão", "complexidade": "alta"})
    assert "is_error" not in res
    assert runner.chamadas == [("muda a cor do botão", "alta")]


def test_abrir_consola_complexidade_default_media():
    runner = RunnerFalso((True, ""))
    tools.configurar_consola(runner)
    _run({"pedido": "faz x"})
    assert runner.chamadas == [("faz x", "media")]


def test_abrir_consola_sem_pedido_e_erro():
    tools.configurar_consola(RunnerFalso())
    res = _run({"pedido": "   "})
    assert res.get("is_error") is True


def test_abrir_consola_propaga_recusa_do_runner():
    runner = RunnerFalso((False, "Já há uma consola a correr. Espera que acabe."))
    tools.configurar_consola(runner)
    res = _run({"pedido": "faz x", "complexidade": "baixa"})
    assert res.get("is_error") is True
    assert "a correr" in _texto_de(res)


def test_abrir_consola_sem_runner_ligado_e_erro():
    tools.configurar_consola(None)
    res = _run({"pedido": "faz x"})
    assert res.get("is_error") is True


def _preparar_ficheiros(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEDIDO_CONSOLA", tmp_path / "pedido-consola.md")
    monkeypatch.setattr(config, "CONSOLA_ULTIMA", tmp_path / "consola-ultima.md")
    monkeypatch.setattr(config, "CONSOLA_LOG", tmp_path / "consola-log.txt")


def test_resumo_consola_le_e_apaga_o_ficheiro(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    config.CONSOLA_ULTIMA.write_text("mudei o botão, testes passaram", encoding="utf-8")

    resumo = tools.ler_resumo_consola_pendente()

    assert resumo == "mudei o botão, testes passaram"
    assert not config.CONSOLA_ULTIMA.exists()
    # não repete: chamada seguinte não encontra nada
    assert tools.ler_resumo_consola_pendente() is None


def test_resumo_consola_cai_para_o_log_se_nao_ha_resumo(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    config.CONSOLA_LOG.write_text("saida bruta do processo", encoding="utf-8")

    resumo = tools.ler_resumo_consola_pendente()

    assert resumo == "saida bruta do processo"
    assert not config.CONSOLA_LOG.exists()


def test_resumo_consola_none_se_nao_ha_nada_pendente(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    assert tools.ler_resumo_consola_pendente() is None
