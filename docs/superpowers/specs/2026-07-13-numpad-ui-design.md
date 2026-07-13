# UI Simples + Hotkey Numpad — Design Spec

**Data:** 2026-07-13
**Autor:** Fábio + Claude Code (brainstorming)
**Estado:** Aprovado para plano de implementação

## Visão

Substitui a interação CLI atual (consola texto + tecla ESPAÇO) por uma janela `tkinter` com histórico de conversa tipo chat, indicador de estado, e push-to-talk pela tecla **Numpad Minus (-)** (em vez de ESPAÇO), com botão clicável na UI como alternativa.

## Requisitos funcionais

1. **Hotkey Numpad Minus** — push-to-talk global (funciona sem foco na janela), substitui ESPAÇO.
2. **Botão clicável na UI** — mousedown/mouseup no botão replica start/stop de gravação, útil se hotkey falhar.
3. **Indicador de estado visual** — idle / a gravar / a processar, com mudança de cor (cinza / vermelho / amarelo).
4. **Histórico de conversa** — área scrollável mostra "Fábio:" e "Jean Claude:" por turno, substitui prints na consola.
5. **Fechar janela encerra a app** — sem depender de Ctrl+C.

## Requisitos não-funcionais

- Zero dependências novas — `tkinter` é built-in Python.
- Mantém filosofia resiliente do loop atual: erro num turno não crasha app, aparece como bolha erro no chat, próximo turno continua.
- Mantém isolamento e comportamento do cérebro (`brain/agent.py`) e voz (`voice/stt.py`, `voice/tts.py`) inalterados.

## Arquitetura

Processo único, duas threads:

- **Thread principal** — `tkinter` mainloop (UI).
- **Thread background** — pipeline Jean Claude (STT → agent → TTS), corre em `asyncio` loop próprio.

Comunicação entre threads via `queue.Queue` thread-safe. UI thread faz polling da queue com `root.after(50, ...)` e atualiza chat/estado sem bloquear.

## Componentes

### `voice/hotkey.py` (refactor)

Troca `record_between_keys` (bloqueante, `listener.join()`) por classe `Recorder`:

- `Recorder.start()` — abre `sd.InputStream`, começa a acumular frames.
- `Recorder.stop() -> str` — para stream, grava wav, devolve path.
- Listener `pynput` global captura Numpad Minus (vk 0x6D no Windows) chama `start()`/`stop()`.
- Callback de estado (`on_state_change`) para a UI refletir gravar/parar.

Mantém `save_wav` como está.

### `ui/app.py` (novo)

- Janela `tkinter`: label estado (topo), botão "Numpad -" (mousedown/mouseup liga ao `Recorder`), área `ScrolledText` (chat, read-only).
- `on_state_change` callback do `Recorder` atualiza label + cor.
- Consome queue de eventos (transcrição, resposta, erro) da thread background, insere bolhas no chat.
- `WM_DELETE_WINDOW` — sinaliza thread background parar, fecha app.

### `main.py` (refactor)

- Cria `Recorder`, liga hotkey global.
- Arranca thread background com `asyncio.run(run_loop(...))` — mesma lógica de turno atual (transcribe → `jc.ask` → `speak`), mas em vez de `print`, empurra eventos pra queue.
- Chama `ui.app.launch(recorder, event_queue)` na thread principal — bloqueia até janela fechar.

## Fluxo de dados

1. Numpad Minus pressiona (ou botão mousedown) → `Recorder.start()` → estado "a gravar" (vermelho).
2. Solta (ou mouseup) → `Recorder.stop()` → path wav → thread background pega, estado "a processar" (amarelo).
3. Background: `stt.transcribe_file` → push evento `("user", texto)` pra queue → `jc.ask(prompt)` → push evento `("assistant", resposta)` → `speaker.speak(resposta)` → estado volta "idle" (cinza).
4. UI thread lê queue a cada 50ms, insere bolhas no chat, atualiza label estado.

## Tratamento de erros

- Exceção em qualquer passo do turno (STT, agent, TTS) → captura, push evento `("error", mensagem)` pra queue → UI mostra bolha vermelha no chat → estado volta idle → próximo turno continua normalmente (mesma filosofia do `main.py` atual, linha `except Exception as e: print(...)`).
- Falha ao abrir stream de áudio ou falha do listener global (ex: sem permissões) → mostra erro na área de estado da UI ao arrancar, não crasha silenciosamente.

## Testes

- `tests/test_hotkey.py` já existe — adaptar para nova API `Recorder.start()/stop()`.
- Novo `tests/test_ui.py` (opcional, smoke) — testa lógica de eventos/queue sem abrir janela real (mock `tkinter` ou testar só a camada de estado/queue, não o mainloop).
