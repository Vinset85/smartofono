"""Consumer video HA -> RPi via ffmpeg HTTP/MP4 fragmented.

Architettura:
    [browser HA WHIP push] -> [go2rtc HA :1984] -> stream "responder_av"
        -> HTTP GET /api/stream.mp4?src=responder_av (fMP4 con SPS/PPS in moov)
        -> ffmpeg -i pipe.mp4 -f rawvideo -pix_fmt rgb24 -s WxH pipe:1
        -> reader thread legge w*h*3 bytes per frame
        -> callback push_frame(rgb_bytes, w, h) -> Kivy blit

Razionale (vs aiortc WHEP video):
    - pyav (decoder usato da aiortc) e' fragile coi profili H264 emessi da
      Chromium e silenziosamente scarta tutti i frame -> video bianco.
    - libavcodec (ffmpeg CLI) ha decoder H264/VP8 maturi: decodifica
      affidabile sia profilo Baseline che Main/High, sia VP8 che VP9.
    - HTTP + fragmented MP4 e' tollerante a publisher con framerate
      irregolare: ffmpeg attende e produce frame appena disponibili,
      mentre WHEP RTP scarta packets se il jitter buffer si svuota.
    - Latenza extra ~1-2s vs WebRTC raw (~150ms). Accettabile per
      un videocitofono dove il visitatore non vede il proprio interlocutore
      in real-time stretto.

Robustezza:
    - Se il publisher cade o lo stream e' vuoto, ffmpeg termina;
      reader thread rilancia automaticamente con backoff.
    - Output rawvideo a risoluzione fissa (default 480x480) per evitare
      di dover ri-allocare la texture Kivy ad ogni frame.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Callable, Optional

LOG = logging.getLogger(__name__)


class MP4VideoConsumer:
    """Pull HTTP/fMP4 dal go2rtc HA e fornisce frame RGB24 via callback.

    Args:
        url: URL fragmented MP4 (es.
             "http://192.168.1.160:1984/api/stream.mp4?src=responder_av").
        width, height: risoluzione di output rawvideo (ffmpeg scaling).
        on_frame: callback(rgb_bytes, w, h) chiamato per ogni frame.
                  Eseguito nel reader thread, deve essere veloce o
                  delegare a coda (es. Kivy Clock.schedule_once).
    """

    def __init__(
        self,
        url: str,
        width: int = 480,
        height: int = 480,
        on_frame: Optional[Callable[[bytes, int, int], None]] = None,
    ):
        self.url = url
        self.width = width
        self.height = height
        self.on_frame = on_frame

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._frame_size = width * height * 3  # rgb24

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="mp4-video-consumer", daemon=True
        )
        self._thread.start()
        LOG.info("MP4VideoConsumer start url=%s %dx%d", self.url, self.width, self.height)

    def stop(self) -> None:
        LOG.info("MP4VideoConsumer stop")
        self._stop.set()
        self._kill_proc()
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        self._thread = None

    def _kill_proc(self) -> None:
        p = self._proc
        if p is None:
            return
        try:
            p.terminate()
            try:
                p.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass
        self._proc = None

    def _spawn_ffmpeg(self) -> Optional[subprocess.Popen]:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            # ----- low-latency tuning input -----
            # probesize 32: leggi solo i primi 32 bytes per detect format
            #   (default 5MB -> aspetta secondi); minimo per fMP4 OK perche'
            #   ffmpeg conosce il container.
            # analyzeduration 0: zero ms di analisi sul flusso (default 5s)
            # max_delay 0: zero microsecondi di reorder buffer per RTP
            # rtbufsize 1M: bound piccolo (default 64MB!) input buffer
            "-probesize", "32",
            "-analyzeduration", "0",
            "-max_delay", "0",
            "-rtbufsize", "1M",
            "-fflags", "+nobuffer+discardcorrupt+flush_packets",
            "-flags", "low_delay",
            "-strict", "experimental",
            # reconnect automatico se publisher droppa
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            # input
            "-i", self.url,
            # filter: scala + format. format=rgb24 prima di scale evita
            # warning "no accelerated colorspace" perche' converte yuv->rgb
            # in un singolo pass dello scaler invece di catena multipla.
            "-vf", f"scale={self.width}:{self.height}:flags=fast_bilinear,format=rgb24",
            "-fps_mode", "passthrough",
            # output rawvideo su stdout
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            # no audio (lo gestisce il consumer WHEP audio-only separato)
            "-an",
            "pipe:1",
        ]
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            LOG.info("ffmpeg video consumer avviato pid=%d", p.pid)
            # thread che logga stderr ffmpeg (utile per diagnostica)
            threading.Thread(
                target=self._stderr_logger, args=(p,), daemon=True
            ).start()
            return p
        except FileNotFoundError:
            LOG.error("ffmpeg non installato")
            return None
        except Exception as e:
            LOG.error("ffmpeg spawn err: %s", e)
            return None

    def _stderr_logger(self, p: subprocess.Popen) -> None:
        try:
            for line in iter(p.stderr.readline, b""):
                if not line:
                    break
                msg = line.decode("utf-8", "replace").rstrip()
                if msg:
                    LOG.warning("[mp4-video ffmpeg] %s", msg)
        except Exception:
            pass

    def _run(self) -> None:
        backoff = 0.5
        n_total = 0
        while not self._stop.is_set():
            self._proc = self._spawn_ffmpeg()
            if self._proc is None:
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 1.5, 5.0)
                continue
            n_in_session = 0
            t_start = time.monotonic()
            stdout = self._proc.stdout
            try:
                while not self._stop.is_set():
                    # readinto non disponibile su BufferedReader stdout pipe
                    # quando bufsize=0; usiamo read() classico.
                    buf = self._read_exact(stdout, self._frame_size)
                    if buf is None:
                        break  # ffmpeg terminato
                    n_in_session += 1
                    n_total += 1
                    if self.on_frame is not None:
                        try:
                            self.on_frame(buf, self.width, self.height)
                        except Exception as e:
                            LOG.warning("on_frame callback err: %s", e)
                    if n_total in (1, 5, 25) or n_total % 250 == 0:
                        elapsed = time.monotonic() - t_start
                        fps = n_in_session / elapsed if elapsed > 0 else 0
                        LOG.info("mp4-video frames=%d session=%d (%.1f fps)",
                                 n_total, n_in_session, fps)
            except Exception as e:
                LOG.warning("mp4-video reader err: %s", e)
            finally:
                self._kill_proc()
            if self._stop.is_set():
                break
            # ffmpeg esce: publisher caduto o stream vuoto. Backoff veloce.
            if self._stop.wait(backoff):
                return
            backoff = min(backoff * 1.3, 3.0) if n_in_session == 0 else 0.5
        LOG.info("MP4VideoConsumer thread end (frames=%d)", n_total)

    def _read_exact(self, stream, n: int) -> Optional[bytes]:
        """Legge esattamente n bytes dallo stream o None se EOF."""
        chunks = []
        remaining = n
        while remaining > 0:
            if self._stop.is_set():
                return None
            try:
                chunk = stream.read(remaining)
            except Exception:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
