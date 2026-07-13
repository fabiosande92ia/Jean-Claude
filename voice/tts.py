# voice/tts.py
"""Text-to-Speech do Jean Claude.

Três motores, escolhidos por `config.TTS_ENGINE`:

- edge_vc (default): Edge-TTS Duarte (pt-PT-DuarteNeural, pronúncia europeia
  garantida) + voice conversion FreeVC para o timbre do JeanClaude. Melhor dos
  dois: sotaque PT-PT europeu certo + a voz do Jean Claude. Online (Edge) + GPU.
- edge: só o Duarte europeu (online, sem clonagem).
- xtts: XTTS-v2 local com clonagem do JeanClaude (offline após 1º download, mas
  o "pt" do XTTS puxa para pt-BR nalgumas palavras).

Contrato do repo: cada motor implementa `synth(text, out_path)` e herda
`speak()`/`stop()` da base. `speak()` sintetiza para um WAV temporário, lê-o e
toca via sounddevice, com `cancel` a poder abortar antes de tocar.
"""
import asyncio
import io
import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from abc import ABC, abstractmethod
import numpy as np
import sounddevice as sd
import soundfile as sf
from core import config

# No Windows, o ProactorEventLoop (default) sofre com resets de rede do Edge-TTS
# (WinError 64). O SelectorEventLoop é mais estável para o HTTP do edge_tts.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Amostra de voz alvo (timbre a clonar). WAV (não MP3): o FreeVC/XTTS carregam-na
# via torchaudio, que no Windows sem ffmpeg não descodifica MP3. O WAV é gerado do
# MP3 (fonte versionada) na 1ª carga — models/ é gitignored, o clone só traz o MP3.
_SPEAKER_WAV = config.XTTS_SPEAKER_WAV
_SPEAKER_MP3 = config.XTTS_SPEAKER_MP3
_SPEAKER_MAX_S = 30   # cap da amostra alvo (fala limpa) — ver _ensure_speaker_wav


def _ensure_speaker_wav() -> "str | None":
    """Garante o WAV da amostra. Se faltar mas houver o MP3, converte (mono +
    silêncio cortado).

    soundfile lê MP3 (libsndfile 1.1+) sem ffmpeg; escreve o WAV que o FreeVC/XTTS
    pedem. O silêncio é cortado (top_db=30): a amostra crua tinha ~38% de espaço
    morto, que dilui o embedding de timbre do FreeVC. Concentrar a fala aproxima o
    resultado da voz alvo.

    Cap em _SPEAKER_MAX_S: o FreeVC re-extrai o embedding do alvo a CADA frase, logo
    um alvo de minutos torna cada síntese lenta (3 min -> ~2-3 s/frase vs ~0.7 s).
    ~30 s de fala limpa dão um embedding rico na mesma. None se não houver amostra.
    """
    wav = Path(_SPEAKER_WAV)
    if wav.exists():
        return str(wav)
    mp3 = Path(_SPEAKER_MP3)
    if not mp3.exists():
        return None
    data, sr = sf.read(str(mp3))
    if data.ndim > 1:
        data = data.mean(axis=1)   # mono
    data = data.astype(np.float32)
    try:
        import librosa
        intervalos = librosa.effects.split(data, top_db=30)
        if len(intervalos):
            data = np.concatenate([data[a:b] for a, b in intervalos])
    except Exception:
        pass   # sem librosa / falha no corte: usa o áudio inteiro, ninguém morre
    data = data[: int(_SPEAKER_MAX_S * sr)]   # cap de duração (velocidade por frase)
    wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(wav), data, sr, subtype="PCM_16")
    return str(wav)


def robotize(data: np.ndarray, sr: int, carrier_hz: float = 55.0,
             crush_bits: int = 6, mix: float = 0.9,
             pitch_semitones: float = 0.0) -> np.ndarray:
    """Torna a voz "robótica": pitch shift + ring modulation + bitcrush, com dry/wet.

    `pitch_semitones` sobe (>0) ou baixa (<0) o tom sem mudar a duração — voz mais
    "fina"/aguda para cima. Feito com librosa (dep opcional já usada no repo); se
    faltar, salta o shift (o resto do efeito continua). O dry/wet mistura sempre
    contra o sinal JÁ com pitch, para o `mix` regular só a dose de robô, não o tom.

    Ring mod = multiplicar o sinal por um seno de `carrier_hz` (o timbre metálico
    clássico de robô/Dalek). Bitcrush = quantizar a `crush_bits` (som digital,
    áspero). `mix` mistura o resultado com a voz (1 = só robô, 0 = voz limpa).

    Puro numpy (fora o pitch), sem estado — testável sem tocar/rede e aplicável a
    qualquer motor. Mono (n,) ou estéreo (n, ch); devolve float32 em [-1, 1]. O
    seno arranca em fase 0 a cada frase: sem continuidade entre frases, mas cada
    frase é curta e o efeito não depende de fase absoluta.
    """
    data = np.asarray(data, dtype=np.float32)
    if pitch_semitones:
        try:
            import librosa
            if data.ndim > 1:   # librosa quer mono; processa canal a canal
                data = np.stack(
                    [librosa.effects.pitch_shift(data[:, c], sr=sr,
                                                 n_steps=float(pitch_semitones))
                     for c in range(data.shape[1])], axis=1).astype(np.float32)
            else:
                data = librosa.effects.pitch_shift(
                    data, sr=sr, n_steps=float(pitch_semitones)).astype(np.float32)
        except Exception:
            pass   # sem librosa / falha: fica no tom original, resto do FX segue
    n = data.shape[0]
    t = np.arange(n, dtype=np.float32) / float(sr)
    carrier = np.sin(2.0 * np.pi * float(carrier_hz) * t)
    if data.ndim > 1:
        carrier = carrier[:, None]          # (n,) -> (n,1) para o broadcast estéreo
    ring = data * carrier
    q = float(2 ** int(crush_bits))
    crushed = np.round(ring * q) / q
    out = float(mix) * crushed + (1.0 - float(mix)) * data
    return np.clip(out, -1.0, 1.0).astype(np.float32)


class TTS(ABC):
    @abstractmethod
    def synth(self, text: str, out_path: str) -> str:
        """Sintetiza texto para um ficheiro WAV; devolve o caminho."""

    def speak(self, text: str, cancel: "threading.Event | None" = None) -> None:
        """
        Sintetiza e toca em voz alta. `cancel` permite abortar antes de tocar.

        A síntese demora: sem o teste ao `cancel` a seguir ao synth, carregar em
        Parar durante a síntese não impedia a fala de arrancar logo a seguir.
        """
        text = (text or "").strip()
        if not text:
            return
        # Path único no temp do SO. Era fixo e na raiz do repo: dois speak() em
        # paralelo escreviam o mesmo ficheiro, e um crash deixava lixo no projeto.
        tmp = os.path.join(tempfile.gettempdir(), f"_jc_tts_{uuid.uuid4().hex}.wav")
        try:
            self.synth(text, tmp)
            if cancel is not None and cancel.is_set():
                return
            data, sr = sf.read(tmp)
            if config.TTS_ROBOT:
                data = robotize(data, sr, config.TTS_ROBOT_CARRIER_HZ,
                                config.TTS_ROBOT_CRUSH_BITS, config.TTS_ROBOT_MIX,
                                config.TTS_ROBOT_PITCH_SEMITONES)
            sd.play(data, sr)
            sd.wait()   # stop() noutra thread corta o áudio e faz isto voltar
        finally:
            Path(tmp).unlink(missing_ok=True)

    def stop(self) -> None:
        """Corta a fala a meio. Chamado da thread da UI enquanto speak() bloqueia."""
        try:
            sd.stop()
        except Exception:
            pass   # nada a tocar / device já fechado: parar tem de ser sempre seguro


class EdgeTTS(TTS):
    """Vozes neurais da Microsoft (edge-tts) — grátis, sem chave, online.

    pt-PT-DuarteNeural = português europeu garantido. Cada síntese tem 3
    tentativas com backoff para absorver resets de rede transitórios (WinError 64).
    """

    def __init__(self, voice: str = "pt-PT-DuarteNeural", rate: str = "+0%",
                 pitch: str = "+0Hz", volume: str = "+0%") -> None:
        self.voice = voice
        self.rate = rate
        self.pitch = pitch      # ex: "+15Hz" mais agudo, "-15Hz" mais grave
        self.volume = volume

    def _synth_mp3(self, text: str) -> bytes:
        import edge_tts

        async def go() -> bytes:
            buf = bytearray()
            com = edge_tts.Communicate(text, self.voice, rate=self.rate,
                                       pitch=self.pitch, volume=self.volume)
            async for ch in com.stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
            return bytes(buf)

        erro: "Exception | None" = None
        for _ in range(3):  # resets de rede (WinError 64) são transitórios
            try:
                return asyncio.run(go())
            except Exception as exc:
                erro = exc
                time.sleep(0.3)
        raise erro  # type: ignore[misc]

    @staticmethod
    def _decode(mp3: bytes) -> "tuple[np.ndarray, int]":
        # soundfile lê o MP3 do Edge (libsndfile) — sem PyAV nem ffmpeg.
        data, sr = sf.read(io.BytesIO(mp3))
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data.astype(np.float32), sr

    def synth(self, text: str, out_path: str) -> str:
        data, sr = self._decode(self._synth_mp3(text))
        sf.write(out_path, data, sr, subtype="PCM_16")
        return out_path


class EdgeVcTTS(TTS):
    """Edge Duarte (PT-PT europeu) + voice conversion (FreeVC) para o timbre alvo.

    Mantém a pronúncia europeia do Duarte e "repinta" a cor de voz para a de
    `target_wav` (JeanClaude). Corre a conversão localmente na GPU (~1 s/frase).
    """

    def __init__(self, target_wav: str, voice: str = "pt-PT-DuarteNeural",
                 rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%") -> None:
        os.environ.setdefault("COQUI_TOS_AGREED", "1")  # evita o prompt de licença
        import torch
        from TTS.api import TTS as CoquiTTS

        self._edge = EdgeTTS(voice, rate, pitch, volume)
        self.target = str(target_wav)
        self.sample_rate = 24000       # FreeVC24 devolve 24 kHz
        # source temporário para o VC: a fala do Duarte antes de repintar o timbre
        self._src = os.path.join(tempfile.gettempdir(), f"_jc_vc_src_{uuid.uuid4().hex}.wav")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._vc = CoquiTTS("voice_conversion_models/multilingual/vctk/freevc24").to(device)

    def synth(self, text: str, out_path: str) -> str:
        data, sr = self._edge._decode(self._edge._synth_mp3(text))
        sf.write(self._src, data, sr, subtype="PCM_16")
        wav = self._vc.voice_conversion(source_wav=self._src, target_wav=self.target)
        wav = np.clip(np.asarray(wav, dtype=np.float32), -1.0, 1.0)
        sf.write(out_path, wav, self.sample_rate, subtype="PCM_16")
        return out_path


class XttsTTS(TTS):
    """XTTS-v2 (Coqui) local com clonagem de voz.

    Se `speaker_wav` for dado (amostra de ~6 s+), clona essa voz; senão usa uma
    voz embutida (`speaker`). Corre na GPU (fallback CPU). O "pt" do XTTS puxa
    para pt-BR nalgumas palavras — para PT-PT garantido, usar edge_vc.
    """

    _MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
    _SAMPLE_RATE = 24000   # taxa de saída do XTTS-v2

    def __init__(self, speaker_wav: "str | Path | None" = None,
                 speaker: "str | None" = None,
                 language: str = config.XTTS_LANGUAGE) -> None:
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        import torch
        from TTS.api import TTS as CoquiTTS

        self.language = language
        speaker_wav = speaker_wav if speaker_wav is not None else _ensure_speaker_wav()
        self.speaker_wav = str(speaker_wav) if speaker_wav else None
        self.speaker = speaker if not self.speaker_wav else None

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._tts = CoquiTTS(self._MODEL).to(device)
        self._model = self._tts.synthesizer.tts_model
        self._gpt = self._spk = None
        if self.speaker_wav:
            # calcula a "identidade" da voz UMA vez (não a cada frase)
            self._gpt, self._spk = self._model.get_conditioning_latents(
                audio_path=[self.speaker_wav])

    def synth(self, text: str, out_path: str) -> str:
        if self.speaker_wav:   # voz clonada -> usa os latentes pré-calculados
            out = self._model.inference(text, self.language, self._gpt, self._spk,
                                        temperature=0.7)
            wav = np.asarray(out["wav"], dtype=np.float32)
        else:                  # voz embutida
            wav = np.asarray(
                self._tts.tts(text=text, language=self.language, speaker=self.speaker),
                dtype=np.float32)
        wav = np.clip(wav, -1.0, 1.0)
        sf.write(out_path, wav, self._SAMPLE_RATE, subtype="PCM_16")
        return out_path


def get_tts() -> TTS:
    """Cria o motor TTS conforme config.TTS_ENGINE (edge_vc | edge | xtts).

    edge_vc e xtts caem para Edge simples se o motor pesado falhar a carregar —
    a app nunca fica muda.
    """
    engine = str(config.TTS_ENGINE).lower()

    def _edge() -> TTS:
        return EdgeTTS(config.EDGE_VOICE, config.EDGE_RATE, config.EDGE_PITCH,
                       config.EDGE_VOLUME)

    if engine == "edge_vc":
        try:
            alvo = _ensure_speaker_wav()
            if not alvo:
                raise ValueError("amostra de voz (JeanClaude) não encontrada")
            return EdgeVcTTS(alvo, config.EDGE_VOICE, config.EDGE_RATE,
                             config.EDGE_PITCH, config.EDGE_VOLUME)
        except Exception:
            return _edge()   # VC indisponível -> Duarte europeu simples

    if engine == "xtts":
        try:
            return XttsTTS()
        except Exception:
            return _edge()

    return _edge()
