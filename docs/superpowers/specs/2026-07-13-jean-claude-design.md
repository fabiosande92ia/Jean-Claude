# Jean Claude — Design Spec

**Data:** 2026-07-13
**Autor:** Fábio + Claude Code (brainstorming)
**Estado:** Aprovado para plano de implementação

## Visão

Jean Claude é um super assistente pessoal para desktop Windows, alimentado pelo cérebro do Claude (via Claude Agent SDK) mas com **identidade própria** — nunca se identifica como Claude/Anthropic. Interage por voz (push-to-talk) e texto, fala em estilo **caveman ultra**, mantém **memória persistente** sobre o utilizador e o PC, e pode **auto-melhorar-se** (criar skills, auto-diagnosticar erros, editar o próprio código) com o git como rede de segurança.

Corre localmente numa máquina com RTX 3060 (12GB VRAM). Voz processada 100% local, sem custos e sem enviar áudio para fora.

## Requisitos

### Funcionais
1. **Persona Jean Claude** — system prompt reescrito. Nunca diz "sou o Claude"; é o Jean Claude, assistente do Fábio.
2. **Fala caveman ultra** — estilo de comunicação comprimido, embutido no prompt (não herdado do setup global do utilizador).
3. **Interface voz + texto** — push-to-talk por tecla; responde em voz (TTS) e mostra texto no ecrã.
4. **Controlo do PC** — abrir apps, ficheiros, correr comandos, automatizar tarefas Windows.
5. **Pesquisa web / Q&A** — pesquisa internet, responde perguntas, ajuda geral.
6. **Rotinas / lembretes** — (fase posterior) tarefas agendadas e automações.
7. **Memória persistente** — factos sobre utilizador e PC em markdown, acumulados ao longo do tempo.
8. **Auto-melhoria** — criar skills novas (livre), auto-diagnóstico de erros, editar core (gated por confirmação + git).

### Não-funcionais
- **Isolamento total** do `~/.claude` global do utilizador — config, memória, skills próprias. Sem herdar plugins/MCP/skills existentes.
- **Só tools básicas** — sem stack de MCP herdada.
- **Voz local e gratuita** — sem custo por uso na voz.
- **Auth por subscrição MAX** — sem `ANTHROPIC_API_KEY`, sem custo por token no cérebro.
- **Reversibilidade** — cada auto-edição é um commit git revertível.

## Arquitetura

### Abordagem escolhida
Wrapper Python à volta do **Claude Agent SDK**. Python porque toda a stack de voz (Whisper, XTTS, PyTorch) é Python. Herda as capacidades reais do Claude Code (tools, execução), mas com configuração isolada e persona própria.

### Fluxo de execução (loop principal)
```
[tecla push-to-talk premida]
   → grava microfone (sounddevice)
   → faster-whisper (GPU) transcreve → texto
   → Agent SDK (persona Jean Claude + tools) pensa e age
   → texto de resposta
   → XTTS-v2 (GPU) sintetiza → fala em voz alta
   → mostra texto no ecrã em paralelo
[volta a aguardar tecla]
```
Piper (CPU, leve) disponível como fallback rápido de TTS.

### Componentes (unidades isoladas)

| Unidade | Responsabilidade | Depende de |
|---------|------------------|------------|
| `main.py` | Loop push-to-talk, orquestra tudo | brain, voice |
| `brain/agent.py` | Wrapper Agent SDK, carrega system prompt + tools, gere sessão | claude-agent-sdk |
| `brain/prompt.py` | Constrói system prompt (persona + caveman ultra + regras) | CLAUDE.md semente |
| `voice/stt.py` | Grava mic + transcreve (faster-whisper) | sounddevice, faster-whisper |
| `voice/tts.py` | Sintetiza fala (XTTS-v2, fallback Piper) | coqui TTS / piper |
| `voice/hotkey.py` | Deteta push-to-talk | keyboard/pynput |
| `memory/` | Factos markdown + `MEMORY.md` índice | filesystem |
| `skills/` | Ferramentas/scripts auto-criados pelo Jean Claude | — |
| `core/config.py` | Config, paths, `CLAUDE_CONFIG_DIR` isolado | — |

### Estrutura de ficheiros
```
jean-claude/
  main.py                     # loop push-to-talk
  brain/
    agent.py                  # wrapper Agent SDK
    prompt.py                 # montagem do system prompt
  voice/
    stt.py                    # faster-whisper
    tts.py                    # XTTS-v2 + fallback Piper
    hotkey.py                 # deteção push-to-talk
  core/
    config.py                 # paths, config isolada (edições gated)
  skills/                     # tools auto-criadas (crescem sozinhas)
  memory/                     # factos markdown
    MEMORY.md                 # índice
  .jc-config/                 # CLAUDE_CONFIG_DIR isolado do Jean Claude
    CLAUDE.md                 # persona + caveman ultra + regras (semente)
    settings.json             # tools permitidas, auth
  requirements.txt
  .git/                       # rede de segurança p/ auto-edições
  README.md
```

## Memória

- Ficheiros markdown, um facto por ficheiro, human-readable e greppáveis.
- `MEMORY.md` = índice (uma linha por memória) carregado no arranque.
- Tipos: `user` (quem é o Fábio, preferências), `pc` (config, apps instaladas, paths, hardware), `project`, `feedback`.
- Jean Claude lê o índice ao arrancar e escreve memórias novas durante a conversa (livre).
- Tudo sob git.

## Auto-melhoria — três níveis com salvaguardas

1. **Criar skills novas (livre)** — falta capacidade → escreve script/tool em `skills/` e usa. Sem gate.
2. **Auto-diagnóstico de erros** — algo falha → lê stacktrace → corrige/ajusta. Registado em memória.
3. **Editar o próprio core (gated)** — modifica loop/prompt/config em `core/` ou `.jc-config/CLAUDE.md`. Mostra o diff, pede confirmação explícita, só então commita.

**Rede de segurança:** o projeto é um repositório git. Cada auto-edição é um commit. Se Jean Claude se partir, `git revert` restaura. Edições ao core nunca acontecem sem confirmação.

### Dois níveis de "memória de identidade" (não confundir)
- `.jc-config/CLAUDE.md` = identidade + regras fixas. Muda pouco. Edição **gated**.
- `memory/*.md` = factos soltos acumulados continuamente. Muda **livre**.

## Isolamento e identidade

- Jean Claude arranca com `CLAUDE_CONFIG_DIR` a apontar para `jean-claude/.jc-config/`, nunca o global `~/.claude`.
- `settings.json` dele permite só as tools básicas: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `WebSearch`, `WebFetch`. Sem MCP, sem plugins herdados.
- System prompt (a partir do `CLAUDE.md` semente): persona Jean Claude + estilo caveman ultra + regras. O modelo por baixo continua Claude, mas nunca se apresenta como tal.

## Stack técnica

- Python 3.11+
- `claude-agent-sdk` (cérebro)
- `faster-whisper` (STT, modelo `large-v3` na GPU)
- Coqui `XTTS-v2` (TTS principal, GPU)
- `piper-tts` (TTS fallback, CPU)
- `sounddevice` (captura de microfone)
- `pynput` ou `keyboard` (push-to-talk)
- PyTorch com CUDA (RTX 3060)

## Auth

Subscrição **MAX**. O Agent SDK autentica via token de login do Claude Code (`claude login` uma vez). Sem `ANTHROPIC_API_KEY`, sem custo por token.

## Escopo

### v1 (primeiro plano de implementação)
- Loop push-to-talk (voz local: Whisper + XTTS)
- Cérebro via Agent SDK, isolado, tools básicas
- Persona Jean Claude + caveman ultra
- Memória markdown (ler/escrever)
- Criar skills novas (livre)
- Git inicializado como rede de segurança
- `CLAUDE.md` semente

### Fases posteriores
- Editar-core gated (confirmação + diff)
- Auto-diagnóstico de erros
- Rotinas / lembretes agendados
- Clonar voz custom para o Jean Claude (XTTS voice cloning)
- Fallback Piper afinado

## Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Auto-edição parte o Jean Claude | Git; core gated por confirmação; `git revert` |
| Latência de voz alta | GPU para STT+TTS; Piper como fallback rápido |
| Modelo "vaza" identidade Claude | Regra forte no system prompt + testes de persona |
| Config global contamina | `CLAUDE_CONFIG_DIR` isolado, settings próprias |
| VRAM insuficiente (Whisper large-v3 + XTTS juntos) | Medir uso; opção de baixar Whisper p/ `medium` se apertar |

## Critérios de sucesso (v1)

1. Premir tecla, falar em português, Jean Claude transcreve corretamente.
2. Responde por voz (XTTS) e texto, em estilo caveman ultra, como Jean Claude — nunca "Claude".
3. Executa uma tarefa real no PC (ex: abrir app, criar ficheiro) por comando de voz.
4. Escreve uma memória nova sobre o Fábio e lê-a numa sessão seguinte.
5. Cria uma skill nova a pedido e usa-a.
6. Tudo isolado do `~/.claude` global; auth via subscrição MAX.
