"""Text-To-Speech con engine selezionabile e fallback.

Engine supportati (in ordine di qualita'):
  1. edge       - voci neurali Microsoft, la piu' naturale delle tre.
                  Richiede internet per SINTETIZZARE, non per parlare: ogni
                  frase viene salvata come wav in `cache_dir` e da lì in poi
                  si riproduce da disco. Se la rete manca e la frase non e'
                  in cache, si ricade su piper.
  2. piper      - TTS neurale locale (voce it_IT-paola-medium). Sempre
                  disponibile, cadenza piu' meccanica.
  3. espeak-ng + mbrola - voce `mb-it4` (femminile italiana, accettabile).
  4. espeak-ng puro - `it+f3` fallback sintetico (metallico).

L'engine viene auto-rilevato in base a cio' che e' installato e si puo'
forzare via config (`tts.engine`). La sintesi avviene su thread di
background per non bloccare l'UI.

Uscita audio: fuori chiamata si parla direttamente all'altoparlante,
scavalcando il sink con cancellazione d'eco (che attenua di ~4 dB e
appiattisce il timbro). Durante una chiamata si torna sul percorso con
l'AEC, altrimenti l'interlocutore sentirebbe l'eco della nostra voce.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading

LOG = logging.getLogger(__name__)


PIPER_DIR = "/opt/videocitofono/piper"
PIPER_BIN = os.path.join(PIPER_DIR, "piper", "piper")
PIPER_VOICES_DIR = os.path.join(PIPER_DIR, "voices")
PIPER_DEFAULT_VOICE = "it_IT-paola-medium"

EDGE_DEFAULT_VOICE = "de-DE-SeraphinaMultilingualNeural"
EDGE_CACHE_DIR = "/opt/videocitofono/data/tts-cache"
# Il DAC della voiceHAT accetta solo 48 kHz: si consegna gia' in quel formato
# per non far ricampionare al volo la catena audio.
OUT_RATE = 48000
# Il parlato viene compresso e portato a fondo scala: l'amplificatore della
# voiceHAT ha guadagno fisso e senza questo il saluto resta troppo basso per
# essere sentito da chi sta fuori.
_FILTRO_LIVELLO = ("acompressor=threshold=-20dB:ratio=3:attack=5:release=120"
                   ":makeup=4,alimiter=level_in=1:limit=0.97")


def _piper_available() -> tuple[bool, str]:
    """Ritorna (ok, model_path) se piper + voce italiana disponibili."""
    if not (os.path.isfile(PIPER_BIN) and os.access(PIPER_BIN, os.X_OK)):
        return False, ""
    voice_path = os.path.join(PIPER_VOICES_DIR, PIPER_DEFAULT_VOICE + ".onnx")
    if not os.path.isfile(voice_path):
        return False, ""
    if not shutil.which("aplay"):
        return False, ""
    return True, voice_path


def _edge_available() -> bool:
    """edge-tts installato e ffmpeg presente per portare l'audio a 48 kHz."""
    try:
        import edge_tts  # type: ignore # noqa: F401
    except Exception:
        return False
    return bool(shutil.which("ffmpeg"))


def _sink_altoparlante() -> str:
    """Sink PipeWire dell'altoparlante, scartando quello con l'AEC e l'HDMI.

    Ritorna "" se non si riesce a interrogare PipeWire: in quel caso si usa il
    device predefinito, cioe' il percorso con cancellazione d'eco di sempre."""
    try:
        p = subprocess.run(["pactl", "list", "sinks", "short"],
                           capture_output=True, text=True, timeout=5)
        for riga in (p.stdout or "").splitlines():
            nome = riga.split("\t")[1] if "\t" in riga else ""
            if nome.startswith("alsa_output") and "hdmi" not in nome:
                return nome
    except Exception as e:
        LOG.debug("tts: sink altoparlante non determinato: %s", e)
    return ""


def _detect_default_espeak_voice() -> str:
    has_mbrola = bool(shutil.which("mbrola"))
    has_it4 = os.path.exists("/usr/share/mbrola/it4/it4")
    if has_mbrola and has_it4:
        return "mb-it4"
    return "it+f3"


class Tts:
    def __init__(self, enabled: bool = True, lang: str = "it",
                 wpm: int = 140, volume: float = 1.0,
                 voice: str = "", pitch: int = 50,
                 word_gap_ms: int = 50,
                 engine: str = "auto",
                 piper_voice: str = "",
                 length_scale: float = 1.10,
                 noise_scale: float = 0.667,
                 noise_w: float = 0.8,
                 edge_voice: str = "",
                 edge_rate: str = "+0%",
                 cache_dir: str = "",
                 in_call=None) -> None:
        self.enabled = bool(enabled)
        self.lang = lang or "it"
        self.wpm = int(wpm)
        self.volume = float(max(0.0, min(2.0, volume)))
        self.pitch = max(0, min(99, int(pitch)))
        self.word_gap_ms = max(0, int(word_gap_ms))

        # Parametri Piper:
        #   length_scale: >1 = piu' lento, <1 = piu' veloce. 1.1 = pacato.
        #   noise_scale:  variabilita' timbro/intonazione (default 0.667).
        #   noise_w:      variabilita' durata fonemi (default 0.8).
        self.length_scale = float(length_scale)
        self.noise_scale = float(noise_scale)
        self.noise_w = float(noise_w)
        self.piper_voice = piper_voice or PIPER_DEFAULT_VOICE

        # Voce neurale e cache su disco.
        self.edge_voice = edge_voice or EDGE_DEFAULT_VOICE
        self.edge_rate = edge_rate or "+0%"
        self.cache_dir = cache_dir or EDGE_CACHE_DIR
        # Durante la chiamata l'audio deve passare per l'AEC: senza questo
        # controllo chi sta dall'altra parte sentirebbe l'eco del saluto.
        self._in_call = in_call if callable(in_call) else (lambda: False)
        self._sink = None  # risolto alla prima riproduzione

        engine = (engine or "auto").lower().strip()
        edge_ok = _edge_available()
        piper_ok, piper_model = _piper_available()
        if piper_voice:
            cand = os.path.join(PIPER_VOICES_DIR, piper_voice + ".onnx")
            if os.path.isfile(cand):
                piper_model = cand
                piper_ok = True

        if engine == "edge" and not edge_ok:
            LOG.warning("Tts: engine=edge richiesto ma edge-tts/ffmpeg mancano, "
                        "fallback piper")
            engine = "piper"
        if engine == "piper" and not piper_ok:
            LOG.warning("Tts: engine=piper richiesto ma non disponibile, fallback espeak-ng")
            engine = "espeak"
        if engine == "auto":
            engine = "edge" if edge_ok else ("piper" if piper_ok else "espeak")

        self.engine = engine
        # Il modello piper serve anche con engine=edge: e' la riserva quando
        # manca la rete e la frase non e' ancora in cache.
        self._piper_model = piper_model if piper_ok else ""
        self._piper_ok = piper_ok

        # Voce per engine espeak/mbrola.
        self.voice = voice or _detect_default_espeak_voice()
        self._espeak_available = bool(shutil.which("espeak-ng"))

        self._available = (
            (engine == "edge" and edge_ok) or
            (engine == "piper" and piper_ok) or
            (engine == "espeak" and self._espeak_available)
        )

        if not self.enabled:
            LOG.info("Tts: disabilitato da config")
        elif not self._available:
            LOG.warning("Tts: nessun engine disponibile (edge=%s, piper=%s, "
                        "espeak=%s)", edge_ok, piper_ok,
                        self._espeak_available)
        elif self.engine == "edge":
            LOG.info("Tts: engine=edge, voce=%s, rate=%s, cache=%s, "
                     "riserva=%s", self.edge_voice, self.edge_rate,
                     self.cache_dir, "piper" if piper_ok else "espeak")
        elif self.engine == "piper":
            LOG.info("Tts: engine=piper, voce=%s, length_scale=%.2f, vol=%.2f",
                     os.path.basename(self._piper_model), self.length_scale,
                     self.volume)
        else:
            LOG.info("Tts: engine=espeak, voce=%s, wpm=%d, vol=%.2f, pitch=%d, gap=%dms",
                     self.voice, self.wpm, self.volume, self.pitch,
                     self.word_gap_ms // 10 * 10)

    def is_available(self) -> bool:
        return self.enabled and self._available

    def set_volume(self, vol: float) -> None:
        """Aggiorna il volume del TTS in live (range 0..2)."""
        try:
            self.volume = float(max(0.0, min(2.0, vol)))
            LOG.info("Tts: volume aggiornato a %.2f", self.volume)
        except Exception:
            pass

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def speak(self, text: str) -> None:
        if not self.is_available():
            return
        text = (text or "").strip()
        if not text:
            return
        threading.Thread(
            target=self._speak_blocking,
            args=(text,),
            name="tts-speak",
            daemon=True,
        ).start()

    def _speak_blocking(self, text: str) -> None:
        try:
            if self.engine == "edge":
                if self._speak_edge(text):
                    return
                # Rete assente o servizio giu': meglio una voce meccanica che
                # il silenzio, chi sta alla porta aspetta una conferma.
                if self._piper_ok:
                    self._speak_piper(text)
                else:
                    self._speak_espeak(text)
            elif self.engine == "piper":
                self._speak_piper(text)
            else:
                self._speak_espeak(text)
        except Exception as e:
            LOG.debug("tts speak err: %s", e)

    # ------------------------------ engine edge ----------------------------

    def percorso_cache(self, text: str) -> str:
        """File wav che corrisponde a questa frase con la voce corrente.

        La chiave include voce e velocita': cambiandole la cache si rigenera
        da sola invece di restituire l'audio della voce precedente."""
        chiave = "|".join([self.edge_voice, self.edge_rate,
                           " ".join((text or "").split())])
        h = hashlib.sha1(chiave.encode("utf-8")).hexdigest()[:20]
        return os.path.join(self.cache_dir, h + ".wav")

    def _speak_edge(self, text: str) -> bool:
        """Riproduce la frase con la voce neurale. False se non ci riesce."""
        wav = self.percorso_cache(text)
        if not os.path.isfile(wav):
            if not self.prepara(text):
                return False
        return self._riproduci(wav)

    def prepara(self, text: str) -> bool:
        """Sintetizza e mette in cache una frase, senza riprodurla.

        Usata anche dallo script di pre-generazione, cosi' i saluti degli
        utenti registrati sono pronti prima del primo utilizzo."""
        text = " ".join((text or "").split())
        if not text:
            return False
        wav = self.percorso_cache(text)
        if os.path.isfile(wav):
            return True
        tmp_mp3 = wav + ".part.mp3"
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            import asyncio

            import edge_tts  # type: ignore

            async def _sintesi() -> None:
                com = edge_tts.Communicate(text, self.edge_voice,
                                           rate=self.edge_rate)
                await com.save(tmp_mp3)

            asyncio.run(_sintesi())
            if not os.path.isfile(tmp_mp3) or os.path.getsize(tmp_mp3) < 512:
                raise RuntimeError("audio vuoto dal servizio")
            # Conversione al formato dell'altoparlante + livellamento, una
            # volta sola: alla riproduzione resta solo da leggere il file.
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", tmp_mp3,
                 "-af", _FILTRO_LIVELLO, "-ar", str(OUT_RATE), "-ac", "1",
                 wav + ".part.wav"],
                check=True, timeout=30,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.replace(wav + ".part.wav", wav)
            LOG.info("tts: frase in cache (%s) %r", self.edge_voice, text[:60])
            return True
        except Exception as e:
            LOG.info("tts edge non disponibile (%s) per %r", e, text[:40])
            return False
        finally:
            for scarto in (tmp_mp3, wav + ".part.wav"):
                try:
                    os.remove(scarto)
                except OSError:
                    pass

    def _riproduci(self, wav: str) -> bool:
        """Manda il wav all'altoparlante, diretto se non siamo in chiamata."""
        if self._sink is None:
            self._sink = _sink_altoparlante()
        try:
            in_call = bool(self._in_call())
        except Exception:
            in_call = False
        cmd = None
        if shutil.which("paplay"):
            cmd = ["paplay"]
            if self._sink and not in_call:
                cmd.append("--device=" + self._sink)
            # Il livello del file e' gia' a fondo scala: qui si applica solo
            # il volume scelto in configurazione (1.0 = pieno).
            cmd.append("--volume=%d" % int(65536 * max(0.0, min(1.0, self.volume))))
            cmd.append(wav)
        elif shutil.which("aplay"):
            cmd = ["aplay", "-q", wav]
        if not cmd:
            return False
        try:
            subprocess.run(cmd, check=False, timeout=30,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            LOG.debug("tts riproduzione err: %s", e)
            return False

    def _speak_piper(self, text: str) -> None:
        # Pipeline: piper -> raw 22050 mono S16_LE -> [gain numpy] -> aplay.
        # Piper non ha un'opzione --volume, percio' applichiamo il gain
        # in Python su tutto il buffer raw prima di inoltrarlo ad aplay.
        # Per messaggi brevi (saluti) la latenza aggiuntiva e' < 100ms.
        piper_cmd = [
            PIPER_BIN,
            "--model", self._piper_model,
            "--output_raw",
            "--length_scale", f"{self.length_scale:.3f}",
            "--noise_scale", f"{self.noise_scale:.3f}",
            "--noise_w", f"{self.noise_w:.3f}",
            "--sentence_silence", "0.25",
        ]
        aplay_cmd = ["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"]

        try:
            p1 = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw, _ = p1.communicate(input=text.encode("utf-8"), timeout=20)
        except subprocess.TimeoutExpired:
            try:
                p1.kill()
            except Exception:
                pass
            return
        except Exception as e:
            LOG.debug("piper synth err: %s", e)
            return
        if not raw:
            LOG.debug("piper: output vuoto per testo=%r", text[:60])
            return

        # Applica gain (volume) sul raw PCM S16_LE.
        gain = float(self.volume)
        if abs(gain - 1.0) > 0.01:
            try:
                import numpy as np
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                arr = np.clip(arr * gain, -32768.0, 32767.0).astype(np.int16)
                raw = arr.tobytes()
            except Exception as e:
                LOG.debug("piper gain err: %s", e)

        try:
            p2 = subprocess.Popen(
                aplay_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            p2.communicate(input=raw, timeout=20)
        except subprocess.TimeoutExpired:
            try:
                p2.kill()
            except Exception:
                pass

    def _speak_espeak(self, text: str) -> None:
        cmd = [
            "espeak-ng",
            "-v", self.voice,
            "-s", str(self.wpm),
            "-a", str(int(self.volume * 100)),
            "-p", str(self.pitch),
            "-g", str(max(0, self.word_gap_ms // 10)),
            text,
        ]
        subprocess.run(cmd, check=False, timeout=15,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
