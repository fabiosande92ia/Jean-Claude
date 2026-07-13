# main.py
import asyncio
from pathlib import Path
from core import config
from brain.agent import JeanClaude
from brain import memory
from voice import stt, tts, hotkey

REC_PATH = str(config.PROJECT_ROOT / "_jc_rec.wav")


async def run():
    jc = JeanClaude()
    speaker = tts.get_tts()

    # injeta o índice de memória no arranque
    index = memory.read_index()
    print("Jean Claude pronto. Segura ESPAÇO para falar. Ctrl+C para sair.\n")

    while True:
        try:
            input_hint = "[segura ESPAÇO e fala, larga quando acabares] "
            print(input_hint)
            hotkey.record_between_keys(REC_PATH)

            texto = stt.transcribe_file(REC_PATH)
            if not texto.strip():
                print("(nada ouvido)\n")
                continue
            print(f"Fábio: {texto}")

            prompt = f"[memória índice]\n{index}\n\n[Fábio disse]\n{texto}"
            resposta = await jc.ask(prompt)
            print(f"Jean Claude: {resposta}\n")

            speaker.speak(resposta)
        except KeyboardInterrupt:
            print("\nJean Claude off.")
            break
        finally:
            Path(REC_PATH).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(run())
