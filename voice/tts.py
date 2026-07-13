# voice/tts.py
import os
import tempfile
import uuid
import wave
from pathlib import Path
from abc import ABC, abstractmethod
import sounddevice as sd
import soundfile as sf
from piper import PiperVoice
from core import config

_VOICE_PATH = config.PROJECT_ROOT / "models" / "pt_PT-tugao-medium.onnx"


class TTS(ABC):
    @abstractmethod
    def synth(self, text: str, out_path: str) -> str:
        """Sintetiza texto para um ficheiro WAV; devolve o caminho."""

    def speak(self, text: str) -> None:
        """Sintetiza e toca em voz alta."""
        # Path único no temp do SO. Era fixo e na raiz do repo: dois speak() em
        # paralelo escreviam o mesmo ficheiro, e um crash deixava lixo no projeto.
        tmp = os.path.join(tempfile.gettempdir(), f"_jc_tts_{uuid.uuid4().hex}.wav")
        try:
            self.synth(text, tmp)
            data, sr = sf.read(tmp)
            sd.play(data, sr)
            sd.wait()
        finally:
            Path(tmp).unlink(missing_ok=True)


class PiperTTS(TTS):
    def __init__(self, voice_path: Path = _VOICE_PATH):
        self.voice = PiperVoice.load(str(voice_path))

    def synth(self, text: str, out_path: str) -> str:
        # A API instalada (piper-tts 1.4.2) expõe synthesize_wav(text, wav_file),
        # não synthesize(text, wav) como noutras versões: recebe um
        # wave.Wave_write (de wave.open(out_path, "wb")) e escreve os frames lá.
        with wave.open(out_path, "wb") as wav_file:
            self.voice.synthesize_wav(text, wav_file)
        return out_path


def get_tts() -> TTS:
    return PiperTTS()
