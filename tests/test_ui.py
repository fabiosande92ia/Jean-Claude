import inspect
import queue
import time
import tkinter as tk

import pytest
from ui import app as ui_app

EXPECTED = {"idle", "loading", "recording", "processing", "speaking"}


def test_state_maps_cover_all_states():
    assert set(ui_app.STATE_COLORS) == EXPECTED
    assert set(ui_app.STATE_LABELS) == EXPECTED


def test_estado_desconhecido_nao_rebenta():
    """Antes era STATE_LABELS[payload]: um KeyError matava o _poll e a UI congelava."""
    assert ui_app.STATE_LABELS.get("xpto", "xpto") == "xpto"
    assert ui_app.STATE_COLORS.get("xpto", ui_app.UNKNOWN_COLOR) == ui_app.UNKNOWN_COLOR


def test_estados_ocupados_sao_estados_reais():
    """O spinner/elapsed só pode acender em estados que existem."""
    assert set(ui_app.ESTADOS_OCUPADOS) <= EXPECTED
    assert "idle" not in ui_app.ESTADOS_OCUPADOS


def test_launch_aceita_texto_cancelar_e_historico():
    params = inspect.signature(ui_app.launch).parameters
    for p in ("on_text", "on_cancel", "hotkey_label", "historico"):
        assert p in params


def test_hora_formata_iso_e_cai_para_agora():
    assert ui_app._hora("2026-07-13T09:05:00") == "09:05"
    assert len(ui_app._hora(None)) == 5      # HH:MM de agora
    assert len(ui_app._hora("lixo")) == 5    # ts corrompido não rebenta a chat


@pytest.mark.parametrize("rms", [0.0, 0.001, 0.05, 1.0, 99.0, -1.0])
def test_nivel_do_vu_fica_sempre_entre_0_e_1(rms):
    assert 0.0 <= ui_app.nivel_vu(rms) <= 1.0


def test_vu_sobe_com_o_sinal():
    silencio = ui_app.nivel_vu(0.0)
    fala = ui_app.nivel_vu(0.05)
    assert silencio == 0.0
    assert 0.15 < fala < 1.0        # fala normal: barra visível, não colada ao zero
    assert ui_app.nivel_vu(1.0) == 1.0   # clip satura, não estoura o canvas


# --- contraste do header ---------------------------------------------------
def test_contraste_conhecido():
    assert ui_app.contraste("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert ui_app.contraste("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("estado", sorted(EXPECTED))
def test_header_passa_wcag_aa(estado):
    """Texto branco sobre o amarelo do 'a processar' dava 2.6:1. Agora >= 4.5:1."""
    fundo = ui_app.STATE_COLORS[estado]
    assert ui_app.contraste(ui_app.cor_texto(fundo), fundo) >= 4.5


def test_header_de_estado_desconhecido_tambem_passa():
    fundo = ui_app.UNKNOWN_COLOR
    assert ui_app.contraste(ui_app.cor_texto(fundo), fundo) >= 4.5


# --- botões que seguem o estado --------------------------------------------
class BotaoFalso:
    """Widget de mentira: guarda o config() em vez de desenhar. Assim testa-se a
    lógica dos botões sem abrir uma janela Tk (nem arrancar o tray) no pytest."""

    def __init__(self):
        self.cfg = {}

    def config(self, **kw):
        self.cfg.update(kw)


def app_falso(estado):
    app = object.__new__(ui_app.App)
    app._estado = estado
    app._hotkey_label = "Numpad -"
    app.button = BotaoFalso()
    app.stop_button = BotaoFalso()
    app.send_button = BotaoFalso()
    app._refresh_botoes()
    return app


def test_estados_sem_envio_sao_estados_reais():
    assert set(ui_app.ESTADOS_SEM_ENVIO) <= EXPECTED
    assert "idle" not in ui_app.ESTADOS_SEM_ENVIO


def test_botao_falar_pinta_se_a_gravar():
    """Push-to-talk sem confirmação no próprio botão: não se sabia se apanhou."""
    a = app_falso("recording")
    assert "GRAVAR" in a.button.cfg["text"]
    assert a.button.cfg["bg"] == ui_app.STATE_COLORS["recording"]

    b = app_falso("idle")
    assert "Falar" in b.button.cfg["text"]
    assert b.button.cfg["bg"] != ui_app.STATE_COLORS["recording"]


@pytest.mark.parametrize("estado", sorted(EXPECTED))
def test_parar_so_ativo_quando_ha_algo_para_parar(estado):
    a = app_falso(estado)
    ocupado = estado in ui_app.ESTADOS_OCUPADOS
    assert a.stop_button.cfg["state"] == ("normal" if ocupado else "disabled")


@pytest.mark.parametrize("estado", sorted(EXPECTED))
def test_enviar_desativa_enquanto_processa(estado):
    a = app_falso(estado)
    pode = estado not in ui_app.ESTADOS_SEM_ENVIO
    assert a.send_button.cfg["state"] == ("normal" if pode else "disabled")
    assert a._pode_enviar() is pode


def test_parar_em_idle_nao_chama_o_backend():
    """Esc distraído em idle enchia a chat de 'parado.' sem nada a correr."""
    chamadas = []
    a = app_falso("idle")
    a.on_cancel = lambda: chamadas.append(1)
    a._parar()
    assert chamadas == []

    b = app_falso("processing")
    b.on_cancel = lambda: chamadas.append(1)
    b._parar()
    assert chamadas == [1]


# --- modelo do turno (badge do header) --------------------------------------
def _app_para_set_estado(estado_inicial):
    app = object.__new__(ui_app.App)
    app._estado = estado_inicial
    app._desde = time.monotonic()
    app._refresh_botoes = lambda: None
    app._draw_level = lambda rms: None
    return app


def test_set_estado_reseta_modelo_ao_voltar_idle():
    """O badge é do turno: sobreviver-lhe (ex.: 'idle · opus' para sempre) mentia."""
    app = _app_para_set_estado("processing")
    app._modelo = "opus"
    app._set_estado("idle")
    assert app._modelo is None


def test_set_estado_mantem_modelo_entre_estados_ocupados():
    app = _app_para_set_estado("recording")
    app._modelo = "haiku"
    app._set_estado("processing")
    assert app._modelo == "haiku"


# --- código na chat ---------------------------------------------------------
def test_texto_sem_cercas_e_um_so_trecho():
    assert ui_app.segmentos_code("olá Fábio") == [("olá Fábio", False)]


def test_bloco_de_codigo_e_separado_do_texto():
    texto = "corre isto:\n```bash\ngit status\n```\ne diz-me"
    assert ui_app.segmentos_code(texto) == [
        ("corre isto:", False),
        ("git status", True),      # a linha da cerca (e a linguagem) some: é sintaxe
        ("e diz-me", False),
    ]


def test_cerca_por_fechar_nao_perde_texto():
    assert ui_app.segmentos_code("olha:\n```\ngit log") == [("olha:", False), ("git log", True)]


def test_codigo_multilinha_fica_inteiro():
    (trecho, codigo), = ui_app.segmentos_code("```\nlinha1\nlinha2\n```")
    assert codigo is True
    assert trecho == "linha1\nlinha2"   # verbatim: um comando cortado é um comando errado


# --- geometria da janela ----------------------------------------------------
ECRA = (0, 0, 1920, 1080)


def test_parse_geometry():
    assert ui_app.parse_geometry("540x680+100+50") == (540, 680, 100, 50)
    assert ui_app.parse_geometry("540x680-8-8") == (540, 680, -8, -8)
    assert ui_app.parse_geometry("540x680") is None      # sem posição: não serve
    assert ui_app.parse_geometry("lixo") is None
    assert ui_app.parse_geometry("") is None


def test_geometria_boa_e_aceite():
    assert ui_app.geometry_cabe("540x680+100+50", ECRA)


@pytest.mark.parametrize("geo, porque", [
    ("540x680+3000+50", "todo fora do ecrã à direita"),
    ("540x680-600+50", "todo fora do ecrã à esquerda"),
    ("540x680+100+2000", "abaixo do fundo do ecrã"),
    ("540x680+100-300", "barra de título acima do topo: não se agarra"),
    ("100x100+100+50", "abaixo do minsize"),
    ("4000x3000+0+0", "maior que o ecrã"),
    ("lixo", "geometry corrompida"),
])
def test_geometria_ma_e_recusada(geo, porque):
    assert not ui_app.geometry_cabe(geo, ECRA), porque


def test_geometria_no_segundo_monitor_a_esquerda():
    """Monitor à esquerda do principal tem x negativo — é válido, não é lixo."""
    ecra = (-1920, 0, 3840, 1080)
    assert ui_app.geometry_cabe("540x680-1800+50", ecra)


def test_ui_state_guarda_e_recarrega(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", tmp_path / "ui.json")
    ui_app.guardar_ui_state({"geometry": "540x680+10+10", "zoomed": False})
    assert ui_app.carregar_ui_state() == {"geometry": "540x680+10+10", "zoomed": False}


def test_ui_state_corrompido_nao_rebenta(tmp_path, monkeypatch):
    f = tmp_path / "ui.json"
    f.write_text("{isto não é json", encoding="utf-8")
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", f)
    assert ui_app.carregar_ui_state() == {}   # arranca no default em vez de morrer


def test_ui_state_ausente_nao_rebenta(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", tmp_path / "nao-existe.json")
    assert ui_app.carregar_ui_state() == {}


# --- resposta a fluir (kind="delta") ---------------------------------------
@pytest.fixture(scope="module")
def tk_root():
    # Um root para todos: criar e destruir um Tk() por teste falhava de vez em
    # quando com TclError, e um teste que se auto-desliga não testa nada.
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("sem display para o Tk")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def chat(tk_root):
    """App com um Text a sério (o _delta usa marks do widget), sem janela nem tray."""
    app = object.__new__(ui_app.App)
    app.chat = tk.Text(tk_root)
    app._delta_ativo = False
    yield app
    app.chat.destroy()


def texto_da(app):
    return app.chat.get("1.0", "end")


def test_deltas_vao_aparecendo_no_mesmo_bloco(chat):
    chat._delta("isto ")
    chat._delta("chega ")
    chat._delta("aos bocados")
    saida = texto_da(chat)
    assert "Jean Claude: isto chega aos bocados" in saida
    assert saida.count("Jean Claude:") == 1   # um bloco, não um por pedaço


def test_resposta_final_substitui_o_que_fluiu(chat):
    chat._delta("isto chega ")
    chat._delta("aos bocados")
    chat._apagar_delta()
    chat._append_msg("assistant", "isto chega aos bocados")
    saida = texto_da(chat)
    assert saida.count("isto chega aos bocados") == 1   # sem duplicar a resposta
    assert saida.count("Jean Claude:") == 1


def test_cancelar_a_meio_guarda_o_que_ja_fluiu(chat):
    chat._delta("metade da resp")
    chat._fechar_delta()
    chat._append_msg("info", "parado.")
    saida = texto_da(chat)
    assert "metade da resp" in saida   # o que já se viu não desaparece
    assert "parado." in saida


def test_delta_sem_stream_ativo_nao_rebenta(chat):
    """Os _fechar/_apagar são no-op sem stream ativo (nenhum delta chegou ainda)."""
    chat._fechar_delta()
    chat._apagar_delta()
    chat._append_msg("assistant", "resposta inteira de uma vez")
    assert "resposta inteira de uma vez" in texto_da(chat)


# --- mascote ------------------------------------------------------------------
class MascotFalsa:
    def __init__(self):
        self.estados = []
        self.baloes = []
        self.destruida = False

    def set_state(self, e):
        self.estados.append(e)

    def balao(self, t):
        self.baloes.append(t)

    def destroy(self):
        self.destruida = True


def _app_para_poll(mascot):
    """App mínima para exercer o _poll: fila, mascote, e stubs dos handlers que
    os branches tocam. _a_fechar=True impede o reagendamento do after."""
    import queue
    app = object.__new__(ui_app.App)
    app.ui_queue = queue.Queue()
    app._a_fechar = True
    app.mascot = mascot
    app._set_estado = lambda p: None
    app._refresh_estado = lambda: None
    app._apagar_delta = lambda: None
    app._append_msg = lambda k, p: None
    return app


def test_poll_encaminha_estado_para_a_mascote():
    app = _app_para_poll(MascotFalsa())
    app.ui_queue.put(("state", "recording"))
    app._poll()
    assert app.mascot.estados == ["recording"]


def test_poll_encaminha_resposta_para_o_balao():
    app = _app_para_poll(MascotFalsa())
    app.ui_queue.put(("assistant", "está feito Fábio"))
    app._poll()
    assert app.mascot.baloes == ["está feito Fábio"]


def test_mascote_none_nao_rebenta_o_poll():
    app = _app_para_poll(None)
    app.ui_queue.put(("state", "idle"))
    app.ui_queue.put(("assistant", "olá"))
    app._poll()   # não levanta


# --- consola (corrida em segundo plano) --------------------------------------
class NotebookFalso:
    """Notebook de mentira: guarda o texto do separador em vez de desenhar."""

    def __init__(self):
        self._atual = 0
        self.textos = {}

    def index(self, arg):
        return self._atual if arg == "current" else arg

    def tab(self, idx, text):
        self.textos[idx] = text


class BotaoConsolaFalso:
    def __init__(self):
        self.visivel = False

    def pack(self, **kw):
        self.visivel = True

    def pack_forget(self):
        self.visivel = False


@pytest.fixture
def app_consola(tk_root, monkeypatch):
    app = object.__new__(ui_app.App)
    app.ui_queue = queue.Queue()
    app._a_fechar = True
    app.mascot = None
    app._set_estado = lambda p: None
    app._refresh_estado = lambda: None
    app._apagar_delta = lambda: None
    app.mensagens = []
    app._append_msg = lambda k, p: app.mensagens.append((k, p))
    app.chat = tk.Text(tk_root)
    app._delta_ativo = False
    app.consola_txt = tk.Text(tk_root)
    app.nb = NotebookFalso()
    app._idx_consola = 0
    app._consola_run = False
    app._consola_modelo = None
    app._consola_visto = True
    app._consola_desde = time.monotonic()
    app.btn_reiniciar = BotaoConsolaFalso()
    app.dings = []
    monkeypatch.setattr(ui_app, "_ding", lambda: app.dings.append(1))
    yield app
    app.chat.destroy()
    app.consola_txt.destroy()


def test_consola_fim_fecha_delta_em_curso_antes_de_anexar_ao_chat(app_consola):
    """Sem isto, um 'Consola acabou' a meio de uma resposta a fluir reabria o
    bloco delta em vez de o fechar primeiro."""
    app = app_consola
    app._delta_ativo = True
    app.ui_queue.put(("consola_fim", "mudei X, testes ok"))
    app._poll()
    assert app._delta_ativo is False
    assert ("assistant", "Consola acabou. mudei X, testes ok") in app.mensagens
    assert app.dings == [1]


def test_consola_fim_mostra_botao_reiniciar(app_consola):
    app = app_consola
    app.ui_queue.put(("consola_fim", "resumo"))
    app._poll()
    assert app.btn_reiniciar.visivel is True


def test_2a_corrida_esconde_botao_reiniciar_da_corrida_anterior(app_consola):
    """Clicar 'reiniciar' com uma 2ª consola já a correr orfanava o subprocesso
    (a app fecha, o Popen escondido continua vivo sem ninguém à espera dele)."""
    app = app_consola
    app.btn_reiniciar.visivel = True   # ficou visível da corrida anterior
    app.ui_queue.put(("consola_estado", {"run": True, "modelo": "opus"}))
    app._poll()
    assert app.btn_reiniciar.visivel is False
    assert app._consola_run is True


def test_consola_run_arranca_timer_proprio(app_consola):
    """O spinner da consola não pode saltar quando o estado principal muda."""
    app = app_consola
    antes = time.monotonic()
    app.ui_queue.put(("consola_estado", {"run": True, "modelo": "sonnet"}))
    app._poll()
    assert app._consola_desde >= antes
