# Consola em segundo plano + seleção de modelo automática

**Data:** 2026-07-13
**Estado:** aprovado (design)

## Problema

Hoje a tool `abrir_consola` abre um Claude Code em janela **separada e visível**
(`CREATE_NEW_CONSOLE`), fire-and-forget, e a app **reinicia-se sozinha** quando a
consola fecha para carregar o código novo. O Fábio quer:

1. A consola a correr **escondida, em segundo plano**, com o progresso visível
   numa **aba** da UI que ele abre quando quer — sem interromper a conversa com
   o Jean, que continua a funcionar enquanto a consola trabalha.
2. No fim, o Jean **confirma no chat** que a consola acabou, e o reinício (para
   aplicar mudanças de código) passa a ser **por botão**, decidido pelo Fábio.
3. **Seleção de modelo automática** por complexidade do pedido — tanto na consola
   como na conversa normal — com um **badge** a mostrar o modelo a correr.

## Âmbito e não-âmbito

Duas features, tratadas no mesmo spec por partilharem o mapa complexidade→modelo
e o badge:

- **A — Consola em segundo plano numa aba** (mecânica de processo + UI).
- **B — Seleção de modelo automática** (heurística local + classificação na consola).

**Não-âmbito:** router por LLM para a conversa (rejeitado — latência numa app de
voz); consolas concorrentes (uma de cada vez); alterar a persona para lá do
gatilho da consola.

---

## Feature A — Consola em segundo plano

### A.1 Módulo `brain/consola.py`

Classe `ConsoleRunner`, dona única do ciclo de vida do subprocesso. Isola toda a
mecânica (Popen, parsing, guard, fim) do resto da app.

```python
class ConsoleRunner:
    def __init__(self, ui_queue, on_terminou):
        # on_terminou: callback sem args, disparado quando o processo sai.
        # Serve para a app marcar "resumo pronto / reinício disponível".

    def start(self, pedido: str, complexidade: str) -> tuple[bool, str]:
        # Devolve (True, "") se arrancou.
        # Devolve (False, motivo) se: já corre uma; não é Windows; claude não no PATH.

    def is_running(self) -> bool:
        ...
```

**Guard uma-de-cada-vez:** flag booleana sob `threading.Lock`. `start` recusa se
`is_running()` — nunca há duas consolas a editar o mesmo código.

**Arranque (`start`):**
- Escreve o `pedido` em `config.PEDIDO_CONSOLA` (por ficheiro, nunca por argumento
  — evita injeção de comandos, como hoje).
- Mapeia `complexidade` → `--model <id>` (ver B.1).
- Env-limpo: copia `os.environ`, remove `CLAUDE_CONFIG_DIR` se apontar para a
  `.jc-config` do JC (mesma lógica de [tools.py:107-109](../../../brain/tools.py)).
- `subprocess.Popen`:
  ```
  claude -p --model <id> --output-format stream-json --verbose \
         --dangerously-skip-permissions <PROMPT_CONSOLA>
  ```
  com `creationflags=CREATE_NO_WINDOW`, `stdout=PIPE`, `stderr=STDOUT`,
  `stdin=DEVNULL`, `text=True`, `cwd=PROJECT_ROOT`, `encoding="utf-8"`,
  `errors="replace"`.
  - `--output-format stream-json --verbose` é o que dá **progresso vivo**; o modo
    `-p` texto só imprime o resultado final (aba ficaria vazia até ao fim).
  - `stdin=DEVNULL` corta o "no stdin data received" do modo pipe.
- Arranca uma **thread leitora** daemon.
- Emite `("consola_estado", {"run": True, "modelo": nome})` no `ui_queue`.

**Thread leitora:** lê `proc.stdout` linha-a-linha. Cada linha é um evento JSON
(newline-delimited). Passa por `parse_evento` (função pura) e, se devolver texto,
`ui_queue.put(("consola", linha_amigavel))`.

**Fim** (quando `proc.stdout` esgota / `proc.wait()` retorna):
- Lê o resumo via `ler_resumo_consola_pendente()` (já existe em `brain/tools.py`).
- `ui_queue.put(("consola_estado", {"run": False}))`.
- `ui_queue.put(("consola_fim", resumo or "(sem resumo)"))`.
- Chama `on_terminou()`.
- Limpa a flag do guard (sob lock).

### A.2 Parsing do stream-json

Função pura, testável sem processo:

```python
def parse_evento(ev: dict) -> str | None:
    # None => linha ignorada (não aparece na aba)
```

Regras sobre os tipos de evento do `claude --output-format stream-json`:

| Evento | Ação |
|---|---|
| `assistant` com bloco `text` | devolve o texto |
| `assistant` com bloco `tool_use` | devolve `🔧 {nome}: {alvo}` (ex.: `🔧 Edit: brain/agent.py`, `🔧 Bash: pytest`) — `alvo` extraído de `input` (file_path / command / pattern), truncado |
| `result` | devolve `— consola terminou —` |
| `system`/`init`, `user`/`tool_result`, outros | `None` (ignora) |

Na thread leitora, se `json.loads` falhar, a linha crua é mostrada tal e qual
(fallback — nunca rebenta o parsing).

### A.3 Mensagens `ui_queue` novas

Drenadas no [`App._poll`](../../../ui/app.py) (o `else` com `.get()` já tolera
kinds desconhecidos, mas estes são tratados explicitamente):

| Mensagem | Efeito |
|---|---|
| `("consola", linha)` | append da linha ao `Text` da aba Consola; auto-scroll |
| `("consola_estado", {"run": bool, "modelo": str?})` | liga/desliga spinner do badge da aba; guarda o modelo a correr |
| `("consola_fim", resumo)` | escreve resumo no fim da aba; badge → `✓`; mostra botão reiniciar; `winsound.MessageBeep` (no-op fora de Windows); **e** append de uma linha no **chat**: `Consola acabou. {resumo}` (kind `assistant`, para o Jean confirmar onde o Fábio fala) |

O texto da consola vai **só** para a aba Consola; a conversa vai **só** para o
chat. Canais independentes — zero interferência.

### A.4 Aba na UI (`ui/app.py`)

Envolver a UI atual num `ttk.Notebook`:

- **Tab 1 "Chat"** — o painel atual, movido tal e qual para dentro de um frame.
  Mascot, tray, VU meter, entrada de texto: intactos.
- **Tab 2 "Consola"** — `Text` scrollável, mono (`FONTE_CODE`), read-only
  (`state="disabled"` fora dos appends), auto-scroll para o fundo. Botão
  "Reiniciar pra aplicar" no fundo, escondido até `consola_fim`.

**Badge no título da aba Consola:**
- parada, sem resumo por ver: `Consola`
- a correr: `● Consola · {modelo}` (spinner `SPINNER` a girar, atualizado no
  `_refresh_estado` já existente)
- acabou, resumo por ver: `✓ Consola`
- ao selecionar a aba: badge volta a `Consola` (marca como visto)

### A.5 Botão reiniciar + `main.py`

- `main()` cria `runner = ConsoleRunner(ui_queue, on_terminou=...)`. O
  `on_terminou` apenas sinaliza "resumo pronto" (a UI já recebeu `consola_fim`);
  **não** reinicia.
- O botão "Reiniciar pra aplicar" dispara o caminho de reinício **que já existe**:
  `reiniciar_event.set()` + fecho limpo do mainloop → [main() relança o
  processo](../../../main.py) com `CREATE_NEW_CONSOLE` para si próprio.
- O `runner` é ligado ao `abrir_consola` via `brain_tools` (estender o
  `configurar_reinicio` atual, ou wiring análogo, para o tool alcançar o runner).
- **Remove-se** o Popen antigo de `abrir_consola` (o de `CREATE_NEW_CONSOLE`
  fire-and-forget) e o auto-reinício-no-fim da consola. `ler_resumo_consola_pendente`
  no arranque ([main.py:292](../../../main.py)) **fica** — cobre o resumo pendente
  após o reinício por botão.

### A.6 Gatilho: quando o Jean abre a consola

Descrição do tool `abrir_consola` + [.jc-config/CLAUDE.md](../../../.jc-config/CLAUDE.md)
passam a dizer:

- **Abre consola** para mudanças reais de código em `brain/`, `core/`, `ui/`,
  `main.py`.
- `voice/`, `vision/`, `tests/`: **pergunta ao Fábio antes** de abrir.
- `memory/`, `skills/`: exceção mantida — escreve direto (dados/extensões, não
  código em execução).
- Trivial ou dúvida de âmbito: **pergunta**, não dispara.
- Deixa de ser "usa SEMPRE que pedir mudanças ao código".

---

## Feature B — Seleção de modelo automática

### B.1 Mapa complexidade → modelo

| Complexidade | Modelo (ID) | Uso |
|---|---|---|
| baixa | `claude-haiku-4-5-20251001` | comandos diretos, ações runtime, tweaks pequenos |
| media | `claude-sonnet-5` | conversa normal, features, refactors médios |
| alta | `claude-opus-4-8` | **só refatorações grandes de código** (estrutural, multi-ficheiro, reescrita) — apenas via consola |

`ConsoleRunner` traduz a `complexidade` recebida neste mapa. Fallback para `media`
se a string vier fora do conjunto.

### B.2 Consola: o Jean classifica

`abrir_consola` ganha um segundo parâmetro:

```python
{"pedido": str, "complexidade": str}   # "baixa" | "media" | "alta"
```

A descrição do tool ensina o Jean a escolher: baixa para ajustes pequenos, media
para trabalho médio, **alta só quando é mesmo um refactor grande**.

### B.3 Conversa normal: heurística local (nunca Opus)

Função pura em módulo próprio (ex.: `brain/router.py`), testável:

```python
def escolher_modelo(texto: str) -> str:
    # devolve "baixa" ou "media" — NUNCA "alta" na conversa normal
```

Regras (default **media**):
- **baixa (Haiku)** se o pedido é curto **e** começa/contém verbo de ação runtime:
  `abre`, `fecha`, `aumenta`, `baixa`, `liga`, `desliga`, `diz`, `que horas`,
  `que temperatura`, etc. Comandos diretos, sem raciocínio.
- **media (Sonnet)** para tudo o resto — perguntas, conversa, pedidos médios.
- Opus nunca sai daqui: refatorações grandes vão pela consola (B.2), não pela
  conversa.

As listas de verbos/limiares ficam constantes no módulo, fáceis de afinar.

### B.4 Ligação ao agente

- `JeanClaude.ask(prompt, on_delta=None, model=None)` passa `model` a
  `build_options`, que o mete em `ClaudeAgentOptions(model=...)`
  ([agent.py:26](../../../brain/agent.py)). `model=None` → default do SDK
  (retrocompatível).
- No `worker_loop` ([main.py:236](../../../main.py)), antes do `ask_cancelavel`:
  - `comp = escolher_modelo(texto)`
  - `modelo_id = MAPA[comp]`
  - `ui_queue.put(("modelo", nome_curto))` (para o badge do header)
  - passa `model=modelo_id` ao `ask`.

### B.5 Badge do modelo (header da conversa)

O header já mostra o estado (`idle`, `a processar`, …) com spinner. Passa a
mostrar também o modelo do turno: `a processar · sonnet`. Nova mensagem
`("modelo", nome_curto)` guarda o nome; o `_set_estado`/`_refresh_estado`
compõe `{label} · {modelo}`.

`nome_curto`: `haiku` / `sonnet` / `opus`.

---

## Isolamento e testabilidade

- `parse_evento(ev)` — pura, testada com dicts de evento falsos (assistant/text,
  assistant/tool_use, result, ignorados).
- `escolher_modelo(texto)` — pura, testada com comandos curtos (baixa) e frases
  (media); garante que nunca devolve alta.
- Mapa complexidade→modelo — testado (incl. fallback).
- `ConsoleRunner` — o guard uma-de-cada-vez é testável sem processo real
  (mock do Popen); o start recusa a segunda chamada.

## Fluxo final (Fábio)

1. Fábio pede mudança a `brain/core/ui/main` → Jean classifica complexidade e
   chama `abrir_consola` → consola arranca **escondida** com o modelo certo.
2. Aba **Consola** ganha `● Consola · {modelo}`. Fábio **continua a falar** com o
   Jean (conversa usa Haiku/Sonnet pela heurística; badge do header mostra qual).
3. Fábio clica a aba quando quer → vê o progresso vivo, parseado em linhas limpas.
4. Consola acaba → **ding** + badge `✓` + linha no chat `Consola acabou. {resumo}`
   + botão **Reiniciar pra aplicar**.
5. Fábio clica o botão quando lhe dá jeito → app relança com o código novo; o
   resumo pendente reaparece no arranque.
