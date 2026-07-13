# Jean Claude

Super assistente pessoal de desktop. Voz push-to-talk, visão de ecrã, memória, cérebro Claude isolado com identidade própria.

## Setup

1. `pip install -r requirements.txt`

2. **Login do cérebro (MAX subscription, sem API key).**
   O `brain/agent.py` isola o SDK com `CLAUDE_CONFIG_DIR=.jc-config` (para não herdar
   settings/tools globais do teu `~/.claude`). Isto também isola as **credenciais** — o
   `claude login` que já correste globalmente não é visto pela app. É preciso fazer login
   uma vez apontado para a config isolada do projeto:

   PowerShell:
   ```powershell
   $env:CLAUDE_CONFIG_DIR = "<caminho absoluto do projeto>\.jc-config"
   claude login
   ```

   Confirma que ficaram credenciais em `.jc-config\.credentials.json` (ou equivalente) antes
   de correr `main.py`. Só precisas de fazer isto uma vez por máquina.

3. **Descarregar a voz Piper (pt_PT).**
   O comando documentado do piper-tts **não funciona** para esta voz:
   ```
   python -m piper.download_voices pt_PT-tugao-medium
   ```
   falha por duas razões: (a) a chave real da voz no repositório Hugging Face
   `rhasspy/piper-voices` tem um til — `pt_PT-tugão-medium` — e não `tugao`; (b) mesmo
   corrigindo o nome, o downloader do piper-tts 1.4.2 rebenta com
   `UnicodeEncodeError` ao tentar construir o pedido HTTP com o `ã` sem
   percent-encoding.

   Solução: descarregar os dois ficheiros manualmente do Hugging Face, com o `ã`
   codificado como `%C3%A3` no URL, e guardá-los localmente com nome ASCII (é o que
   `voice/tts.py` espera em `models/`):

   ```
   curl -L -o models/pt_PT-tugao-medium.onnx ^
     "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_PT/tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx"

   curl -L -o models/pt_PT-tugao-medium.onnx.json ^
     "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_PT/tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx.json"
   ```

   Verifica os ficheiros contra o `md5_digest` publicado em `voices.json` desse repositório
   antes de confiar neles. Os nomes finais em disco devem ser exatamente:
   - `models/pt_PT-tugao-medium.onnx`
   - `models/pt_PT-tugao-medium.onnx.json`

   (nomes ASCII sem til — só o nome do ficheiro local é ASCII, o conteúdo é a voz
   `pt_PT-tugão-medium` original, byte-a-byte).

## Correr

`python main.py`

Abre uma janela: segura **Numpad -** (ou clica e segura o botão "Numpad -" na
janela), fala, larga. Jean Claude responde por voz e mostra a conversa no
chat da janela.

## Estrutura

- `brain/` cérebro (Agent SDK) + tools (screenshot)
- `voice/` STT (whisper), TTS (piper), push-to-talk
- `vision/` captura de ecrã
- `memory/` factos persistentes (markdown)
- `skills/` ferramentas que o Jean Claude cria
- `.jc-config/` config isolada + CLAUDE.md (persona)

## Auto-melhoria

Jean Claude cria skills livremente, corrige erros, e — com confirmação — edita o próprio core. Tudo sob git: `git revert` desfaz qualquer coisa.
