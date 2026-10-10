"""Audio player: riproduce su PulseAudio l'audio HA->RPi ricevuto via WebRTC
(modalita' attuale, post-migrazione MQTT->WebRTC).

Sorgente PCM:
    `feed_webrtc_pcm(pcm, rate, channels)` chiamato da:
      - ConversationScreen (modalita' video: audio+video nello stesso pc)
      - WebRTCAudioController (modalita' audio-only: solo m=audio nel pc)
    I chunk sono AudioFrame Opus decodificati da aiortc -> PCM s16le.

Pipeline interna:
    PCM s16le stdin -> ffmpeg (EQ vocale + volume + alimiter) -> PulseAudio
    sink default (= ec_sink dell'AEC PulseAudio module-echo-cancel).

Mic ducking:
    Durante il talkback abbassa il volume del mic capture (ec_source) per
    contrastare il loop acustico residuo. In modalita' WebRTC, default 100%
    (no duck): la latenza <80ms permette all'AEC PulseAudio webrtc backend
    di cancellare efficacemente il loop senza intervento aggiuntivo.

Hardware richiesto:
    - PulseAudio con module-echo-cancel attivo (vedi systemd user service
      videocitofono-mic-volume.service)
    - `ffmpeg` con filter equalizer/alimiter (standard)
    - `pactl` per mic ducking (opzionale)

NOTA: il path MQTT (videocitofono/talkback/audio + base64 PCM) e' stato
rimosso. Le subscription MQTT sono no-op da quando l'audio HA->RPi viaggia
interamente in WebRTC. Il modulo e' rinominabile a `audio_player` ma
mantenuto come `audio_backchannel` per non rompere import esistenti.
"""
from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)


class AudioBackchannel:
    def __init__(self, mqtt_client, cfg: Optional[Dict[str, Any]] = None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("talkback_enabled", cfg.get("enabled", True)))
        self.device = cfg.get("talkback_device", "default")
        self.rate = int(cfg.get("talkback_rate", 16000))
        self.channels = int(cfg.get("talkback_channels", 1))
        self.format = cfg.get("talkback_format", "S16_LE")
        self._mqtt = mqtt_client  # mantenuto per compat firma, non usato
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._has_ffmpeg = shutil.which("ffmpeg") is not None
        # Writer thread + bounded queue per disaccoppiare l'event loop
        # asyncio aiortc (che chiama feed_webrtc_pcm ogni 20ms) dalla
        # syscall write su pipe ffmpeg (potenzialmente bloccante 1-15ms).
        # Se il loop si blocca su write, aiortc accumula RtpPacket e
        # produce packet loss (visto fraction_lost=67% in journalctl).
        # Queue bounded (~1.5s a 20ms/chunk) per evitare drift latenza
        # se il consumer ffmpeg e' temporaneamente lento.
        self._pcm_q: "queue.Queue[bytes]" = queue.Queue(maxsize=75)
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_stop = threading.Event()
        # Mic ducking: durante il talkback HA->RPi attiviamo un'attenuazione
        # forte del mic (oltre l'AEC) per uccidere ogni residuo di Larsen
        # acustico. Valori in % di volume PulseAudio sulla sorgente di
        # default (ec_source). Idle = livello operativo normale,
        # ducked = livello molto basso (mic quasi muto) durante playback.
        self._mic_source = cfg.get("mic_source", "ec_source")
        self._mic_vol_idle = int(cfg.get("mic_volume_idle_pct", 140))
        self._mic_vol_ducked = int(cfg.get("mic_volume_ducked_pct", 25))
        # In modalita' WebRTC il publisher invia frame Opus IN CONTINUO
        # (anche durante silenzio): se duckassimo come per MQTT (25%),
        # il mic resterebbe attenuato per TUTTA la chiamata, peggiorando
        # l'uplink RPi->HA. La latenza WebRTC <80ms permette all'AEC
        # PulseAudio (webrtc backend) di cancellare il loop senza bisogno
        # del duck aggressivo. Default 100% = nessun duck in WebRTC.
        self._mic_vol_ducked_webrtc = int(cfg.get("mic_volume_ducked_webrtc_pct", 100))
        self._has_pactl = shutil.which("pactl") is not None
        self._mic_ducked = False
        self._webrtc_active = False
        # Equalizzatore minimalista sul PCM HA->RPi (Opus 48k WebRTC).
        # Il browser ha gia' applicato echoCancellation + noiseSuppression
        # + autoGainControl WebRTC: la voce arriva pronta. Un EQ aggressivo
        # qui (boost +2dB su 1.5kHz, taglio -3dB su 4kHz) sovra-processava
        # producendo artefatti percepiti come distorsione/metallico.
        # Filter chain conservativa per voce naturale:
        #   highpass 100Hz   : taglio rumble (handling, AC, low-end leak)
        #   lowpass 7500Hz   : taglio fuori-banda (Opus voip 8kHz cap)
        #   volume 1.0       : nessun boost software (gain via PulseAudio
        #                       sink se serve piu' uscita)
        #   alimiter 0.97    : safety clip leggero, evita transient hard-clip
        self._eq_filter = cfg.get(
            "talkback_filter",
            "highpass=f=100,lowpass=f=7500,volume=0.3,alimiter=limit=0.97"
        )
        # Buffer PulseAudio output: tenuto BASSO (60ms) per evitare
        # latency creep. aiortc consegna AudioFrame in burst (specie
        # all'inizio della track, per recover di jitter buffer): se il
        # buffer pulse e' grande, l'eccesso si accumula e l'audio
        # diventa progressivamente "ritardato/asincrono" rispetto al
        # video. 60ms = buffer corto ma sufficiente per Opus 20ms a
        # ritmo regolare. Underrun coperti dal catch-up policy del
        # writer (vedi _writer_loop).
        self._pulse_buffer_ms = int(cfg.get("talkback_pulse_buffer_ms", 200))
        # Sink PulseAudio destinazione: DEVE essere ec_sink (loopback
        # del module-echo-cancel) altrimenti l'audio HA esce diretto
        # sull'hardware bypassando l'AEC -> forte echo Larsen al mic.
        # Default ec_sink, fallback configurabile.
        self._pulse_sink = cfg.get("talkback_pulse_sink", "ec_sink")
        # Catch-up policy: se la queue PCM cresce oltre questa soglia
        # (latenza accumulata), il writer scarta i chunk piu' vecchi
        # per riallinearsi al real-time. Soglia in numero di chunk;
        # tipicamente Opus 20ms = 1 chunk = 20ms. 4 chunk = 80ms max
        # latenza interna prima del drop.
        self._pcm_q_catchup_threshold = int(
            cfg.get("talkback_q_catchup_threshold", 15)
        )

    def start(self) -> None:
        """No-op nel path WebRTC: la sorgente PCM e' iniettata da
        feed_webrtc_pcm() chiamato dai consumer aiortc, non da
        subscription MQTT. Manteniamo il metodo per compat con main.py."""
        if not self.enabled:
            LOG.info("AudioBackchannel disabilitato in config")
            return
        if not self._has_ffmpeg:
            LOG.warning("ffmpeg non installato: talkback disattivo")
            return
        LOG.info(
            "AudioBackchannel pronto (WebRTC mode, ffmpeg+pulse, eq=%s)",
            self._eq_filter[:60] if hasattr(self, "_eq_filter") else "default",
        )

    def stop(self) -> None:
        self._kill_player()

    def _set_mic_volume(self, pct: int) -> None:
        if not self._has_pactl:
            return
        try:
            subprocess.run(
                ["pactl", "set-source-volume", self._mic_source, f"{pct}%"],
                check=False, timeout=1.0,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            LOG.debug("pactl set-source-volume err: %s", e)

    def _get_mic_volume(self) -> Optional[int]:
        """Legge il volume % corrente di ec_source (impostazione utente).

        Serve a ripristinare ESATTAMENTE il livello impostato dallo slider
        `volume_mic_pct` invece di un default hardcoded che lo sovrascriveva
        a fine talkback (bug: il mic tornava a 140% perdendo il 200% utente)."""
        if not self._has_pactl:
            return None
        try:
            r = subprocess.run(
                ["pactl", "get-source-volume", self._mic_source],
                capture_output=True, text=True, timeout=1.0,
            )
            import re
            m = re.search(r"(\d+)%", r.stdout or "")
            return int(m.group(1)) if m else None
        except Exception as e:
            LOG.debug("pactl get-source-volume err: %s", e)
            return None

    def _duck_mic(self) -> None:
        if self._mic_ducked:
            return
        # Cattura il volume mic CORRENTE come livello di ripristino: cosi'
        # rispettiamo l'impostazione utente (slider volume_mic_pct, es. 200%)
        # invece di tornare a un 140% hardcoded a fine talkback.
        cur = self._get_mic_volume()
        if cur is not None:
            self._mic_vol_idle = cur
        self._mic_ducked = True
        # In WebRTC mode NON duckiamo: i frame Opus arrivano sempre e l'AEC
        # PulseAudio cancella il loop; abbassare qui ridurrebbe la voce del
        # visitatore (uplink RPi->HA) per tutta la chiamata.
        if self._webrtc_active:
            LOG.info("Mic duck skip (WebRTC, idle=%d%% preservato)",
                     self._mic_vol_idle)
            return
        self._set_mic_volume(self._mic_vol_ducked)
        LOG.info("Mic ducked a %d%% (talkback MQTT, ripristino a %d%%)",
                 self._mic_vol_ducked, self._mic_vol_idle)

    def _unduck_mic(self) -> None:
        if not self._mic_ducked:
            return
        self._mic_ducked = False
        self._set_mic_volume(self._mic_vol_idle)
        LOG.info("Mic ripristinato a %d%% (talkback off)", self._mic_vol_idle)

    def _ensure_player(self) -> Optional[subprocess.Popen]:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return self._proc
            # Se un proc precedente e' morto, leggiamo stderr per logging
            # (utilissimo: senza di questo i fail di apertura ALSA/Pulse
            # restavano silenti e l'audio "non si sentiva e basta").
            if self._proc and self._proc.poll() is not None:
                try:
                    err = (self._proc.stderr.read() or b"").decode(errors="ignore").strip()
                    if err:
                        LOG.warning("ffmpeg player precedente terminato (rc=%s): %s",
                                    self._proc.returncode, err[:300])
                except Exception:
                    pass
            # ffmpeg legge PCM raw 16le mono 16k da stdin, applica EQ vocale,
            # boost, limiter; output -> PulseAudio sink default (= ec_sink).
            # Codec wav non serve, alsa/pulse usa raw float internamente.
            # -ac 1 -ar 16000 sull'input + filtri lavorano @ 16kHz; PulseAudio
            # resampla a 48kHz dell'AEC trasparentemente.
            ar = str(self.rate)
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning",
                "-fflags", "+nobuffer",
                "-flags", "low_delay",
                "-thread_queue_size", "1024",
                "-f", "s16le", "-ac", str(self.channels), "-ar", ar,
                "-i", "pipe:0",
                "-af", self._eq_filter,
                "-f", "pulse",
                "-device", self._pulse_sink,
                "-buffer_duration", str(self._pulse_buffer_ms),
                "videocitofono-talkback",
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )
                LOG.info("ffmpeg player avviato (pid=%s rate=%s eq=%s)",
                         self._proc.pid, ar, self._eq_filter[:60])
                self._duck_mic()
                self._start_writer()
                return self._proc
            except Exception as e:
                LOG.error("ffmpeg player spawn err: %s", e)
                self._proc = None
                return None

    def _start_writer(self) -> None:
        if self._writer_thread and self._writer_thread.is_alive():
            return
        self._writer_stop.clear()
        try:
            while True:
                self._pcm_q.get_nowait()
        except queue.Empty:
            pass
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="vc-audio-writer", daemon=True,
        )
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        dropped = 0
        last_drop_log = 0.0
        import time as _t
        while not self._writer_stop.is_set():
            try:
                chunk = self._pcm_q.get(timeout=0.2)
            except queue.Empty:
                continue
            # Catch-up: se la queue ha accumulato troppi chunk (latenza
            # cresce), scarta i piu' vecchi per riallinearsi al real-time.
            # Critico per evitare audio "rallentato/asincrono" quando
            # aiortc consegna frame in burst.
            qsize = self._pcm_q.qsize()
            if qsize > self._pcm_q_catchup_threshold:
                drop_n = qsize - self._pcm_q_catchup_threshold
                for _ in range(drop_n):
                    try:
                        chunk = self._pcm_q.get_nowait()
                        dropped += 1
                    except queue.Empty:
                        break
                now = _t.monotonic()
                if now - last_drop_log > 2.0 and dropped > 0:
                    LOG.info("audio writer catch-up: dropped=%d chunk (qsize=%d)",
                             dropped, qsize)
                    last_drop_log = now
                    dropped = 0
            proc = self._proc
            if not proc or not proc.stdin or proc.poll() is not None:
                continue
            try:
                proc.stdin.write(chunk)
            except (BrokenPipeError, ValueError, OSError) as e:
                LOG.warning("writer stdin err: %s, restart al prossimo feed", e)
                self._kill_player()
                return

    def _kill_player(self) -> None:
        self._writer_stop.set()
        with self._lock:
            p = self._proc
            self._proc = None
        if p:
            try:
                if p.stdin:
                    p.stdin.close()
            except Exception:
                pass
            try:
                p.terminate()
                p.wait(timeout=1.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            LOG.info("ffmpeg player chiuso")
        try:
            while True:
                self._pcm_q.get_nowait()
        except queue.Empty:
            pass
        self._unduck_mic()

    # ------------------------------------------------------------------
    # Path WebRTC (post-migrazione bidirezionale): la ConversationScreen
    # riceve gli AudioFrame dal browser HA via aiortc (Opus 48k decod.
    # automaticamente a PCM s16) e li inietta qui. Riusiamo il player
    # ffmpeg, l'EQ vocale, il mic ducking e tutta la logica esistente,
    # cambiando solo la sorgente: stdin scritto da Python invece che
    # alimentato dai chunk MQTT base64. Codec path eliminato (no
    # base64 decode, no JSON parse) -> latenza minima.
    # ------------------------------------------------------------------
    def feed_webrtc_pcm(self, pcm: bytes, rate: int, channels: int) -> None:
        """Inietta un blocco PCM s16le interleaved nel player ffmpeg.

        Se rate/channels differiscono dall'ultima sessione il player
        viene rigenerato (kill + spawn) per allineare gli header
        ffmpeg al nuovo formato. Non thread-safe per il blocco di
        cambio formato, ma chiamato sempre dallo stesso task asyncio
        della ConversationScreen, quindi ok.

        Setta self._webrtc_active = True per indicare al _duck_mic
        di usare il duck "soft" (default 100%, no attenuazione mic).
        """
        self._webrtc_active = True
        if not self.enabled or not self._has_ffmpeg or not pcm:
            return
        if rate != self.rate or channels != self.channels:
            LOG.info(
                "WebRTC PCM format change: %dHz/%dch -> %dHz/%dch, restart player",
                self.rate, self.channels, rate, channels,
            )
            self._kill_player()
            self.rate = rate
            self.channels = channels
        proc = self._ensure_player()
        if not proc or not proc.stdin:
            return
        # Non-blocking enqueue: se la queue e' satura (writer/ffmpeg/Pulse
        # in stallo), scartiamo il chunk piu' vecchio per mantenere la
        # latenza bassa. Meglio un piccolo skip che 1.5s di drift cumulato.
        try:
            self._pcm_q.put_nowait(pcm)
        except queue.Full:
            try:
                self._pcm_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._pcm_q.put_nowait(pcm)
            except queue.Full:
                pass

    def stop_webrtc(self) -> None:
        """Chiude il player WebRTC e ripristina mic volume idle.

        Chiamato da ConversationScreen.on_leave() o quando la track
        audio aiortc termina. Equivalente a _on_stop ma senza
        dipendenza dal messaggio MQTT (deprecato per il flusso video).
        """
        LOG.info("WebRTC audio stream chiuso, kill player")
        self._webrtc_active = False
        self._kill_player()
