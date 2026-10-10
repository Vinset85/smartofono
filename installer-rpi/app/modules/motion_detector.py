"""Motion detector basato su frame differencing.

Usa la CameraPreview esistente; NON apre una propria camera.
Funziona in 'pull' (chiamata `tick()` periodica) per non aggiungere thread.

Algoritmo:
  - downsample frame BGR a piccola dimensione (es. 160x120)
  - converti a grigi (media canali)
  - calcola |frame - prev_frame|
  - se # pixel sopra `pixel_thresh` supera `area_thresh_pct` % -> motion
  - debounce: ignora motion per `cooldown_sec` dopo l'ultimo evento
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

LOG = logging.getLogger(__name__)

# Diff >50% tra due snapshot consecutivi indica frame corrotto / camera
# ripresa (es. go2rtc non pronto), non movimento reale.
_GLITCH_PCT = 50.0


class MotionDetector:
    def __init__(
        self,
        camera,
        pixel_thresh: int = 25,
        area_thresh_pct: float = 1.5,
        cooldown_sec: float = 1.0,
        downsample: int = 8,
    ):
        self.camera = camera
        self.pixel_thresh = pixel_thresh
        self.area_thresh_pct = area_thresh_pct
        self.cooldown_sec = cooldown_sec
        self.downsample = max(1, downsample)
        self._prev = None
        self._last_event = 0.0
        self._cb: Optional[Callable[[], None]] = None

    def on_motion(self, cb: Callable[[], None]) -> None:
        self._cb = cb

    def tick(self) -> bool:
        """Esegue una valutazione. Restituisce True se motion rilevato."""
        if not self.camera or not self.camera.is_available():
            return False
        frame = self.camera.get_frame()
        if frame is None:
            return False

        try:
            import numpy as np
            small = frame[::self.downsample, ::self.downsample]
            gray = small.mean(axis=2).astype("int16")
            if self._prev is None or self._prev.shape != gray.shape:
                self._prev = gray
                return False
            diff = np.abs(gray - self._prev)
            self._prev = gray
            changed = int((diff > self.pixel_thresh).sum())
            total = gray.size
            pct = (changed / total) * 100 if total else 0
            if pct >= self.area_thresh_pct:
                now = time.time()
                if now - self._last_event >= self.cooldown_sec:
                    self._last_event = now
                    LOG.info("Motion rilevato (%.2f%% pixel cambiati)", pct)
                    if self._cb:
                        try:
                            self._cb()
                        except Exception as e:
                            LOG.error("motion cb err: %s", e)
                    return True
        except Exception as e:
            LOG.error("motion tick err: %s", e)
        return False

    def reset(self) -> None:
        self._prev = None


class MotionPicameraDetector:
    """Motion detector che apre direttamente la libcamera (picamera2) a
    bassa risoluzione e bassa frequenza (es. 320x240@2fps Y-only) e fa
    frame differencing.

    Usato quando il Pi NON ha go2rtc/RTSP attivo (architettura LiveKit
    diretta): la camera e' libera tra una chiamata e l'altra, quindi il
    motion detector la usa fra una chiamata e l'altra. La camera deve
    essere RILASCIATA prima che la sessione LiveKit la apra: chiamare
    `stop()` quando si entra in calling/conversation, `start()` quando
    si torna a home/screensaver.

    Il loop gira in un thread dedicato per non bloccare il main loop di
    Kivy. Il callback `on_motion` viene invocato dal thread di background:
    il main app deve schedulare l'azione UI con Clock.schedule_once(...).
    """

    def __init__(
        self,
        width: int = 320,
        height: int = 240,
        fps: float = 2.0,
        pixel_thresh: int = 18,
        area_thresh_pct: float = 1.0,
        cooldown_sec: float = 2.0,
        debug_log_every: int = 30,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self.pixel_thresh = int(pixel_thresh)
        self.area_thresh_pct = float(area_thresh_pct)
        self.cooldown_sec = float(cooldown_sec)
        self.debug_log_every = max(0, int(debug_log_every))
        self._prev = None
        self._last_event = 0.0
        self._cb: Optional[Callable[[], None]] = None
        self._stop = None
        self._thread = None
        self._cam = None
        self._tick_n = 0

    def on_motion(self, cb: Callable[[], None]) -> None:
        self._cb = cb

    def is_available(self) -> bool:
        return True

    def start(self) -> None:
        import threading
        if self._thread and self._thread.is_alive():
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="motion-picam", daemon=True)
        self._thread.start()
        LOG.info("MotionPicameraDetector thread avviato (%dx%d@%.1ffps)",
                 self.width, self.height, self.fps)

    def stop(self, join_timeout: float = 2.0) -> None:
        # Ferma il thread e chiudi la camera. Idempotente.
        if self._stop:
            self._stop.set()
        t = self._thread
        if t and t.is_alive():
            try:
                t.join(timeout=max(0.0, float(join_timeout)))
            except Exception:
                pass
        self._thread = None
        self._close_cam()
        # Reset prev per non confrontare frame pre/post pausa (luce diversa).
        self._prev = None

    def tick(self) -> bool:
        return False

    # ------------------------- internal ---------------------------------
    def _open_cam(self):
        # Usa il singleton PicamSession invece di creare una propria
        # Picamera2: questo evita il problema di libcamera che resta in
        # stato 'Configured' bloccato dopo close+open ripetuti.
        from .camera_session import PicamSession
        sess = PicamSession.instance()
        if not sess.is_available():
            LOG.warning("picamera2 non disponibile (motion off)")
            return None
        if not sess.acquire("motion"):
            # Dedup: il chiamante (_loop) logga gia' un warning con backoff
            # su fail_streak; qui evitiamo lo spam ad ogni retry.
            LOG.debug("PicamSession.acquire(motion) FAIL")
            return None
        return sess  # restituiamo il session-handle, non un Picamera2

    def _close_cam(self):
        # Non chiudiamo il session: motion rilascia solo "logicamente" la
        # camera (smette di leggere). L'apertura/chiusura HW e' decisa da
        # main._on_screen_changed (release in calling/conversation).
        self._cam = None

    def _loop(self):
        import numpy as np
        period = 1.0 / max(self.fps, 0.5)
        fail_streak = 0
        try:
            while self._stop and not self._stop.is_set():
                if self._cam is None:
                    self._cam = self._open_cam()
                    if self._cam is None:
                        fail_streak += 1
                        if fail_streak in (1, 5, 15) or fail_streak % 30 == 0:
                            LOG.warning(
                                "motion picam: camera non disponibile (retry %d)",
                                fail_streak)
                        self._stop.wait(min(period * 3, 5.0))
                        continue
                    fail_streak = 0
                    self._prev = None
                t0 = time.time()
                try:
                    # `self._cam` e' un PicamSession; capture("motion")
                    # ritorna None se la sessione e' stata riconfigurata altrove.
                    arr = self._cam.capture("motion")
                    if arr is None:
                        self._cam = None
                        self._prev = None
                        self._stop.wait(period)
                        continue
                    # YUV420 planar shape (h*1.5, w): la prima banda h e' Y (luma).
                    gray = arr[: self.height, :].astype("int16")
                except Exception as e:
                    LOG.warning("motion picam capture err: %s", e)
                    self._cam = None
                    self._prev = None
                    self._stop.wait(period * 2)
                    continue
                try:
                    self._tick_n += 1
                    if self._prev is None or self._prev.shape != gray.shape:
                        self._prev = gray
                    else:
                        diff = np.abs(gray - self._prev)
                        self._prev = gray
                        changed = int((diff > self.pixel_thresh).sum())
                        total = gray.size
                        pct = (changed / total) * 100 if total else 0
                        if self.debug_log_every and (self._tick_n % self.debug_log_every == 0):
                            LOG.info(
                                "motion picam debug: tick=%d avg_diff=%.2f changed=%.2f%% (thr=%d, area=%.2f%%)",
                                self._tick_n, float(diff.mean()), pct,
                                self.pixel_thresh, self.area_thresh_pct,
                            )
                        if pct >= self.area_thresh_pct:
                            now = time.time()
                            if now - self._last_event >= self.cooldown_sec:
                                self._last_event = now
                                LOG.info("MOTION rilevato (%.2f%% pixel cambiati)", pct)
                                if self._cb:
                                    try:
                                        self._cb()
                                    except Exception as e:
                                        LOG.error("motion cb err: %s", e)
                except Exception as e:
                    LOG.error("motion picam loop err: %s", e)
                elapsed = time.time() - t0
                wait = max(0.0, period - elapsed)
                if wait:
                    self._stop.wait(wait)
        finally:
            self._close_cam()

    def reset(self) -> None:
        self._prev = None


class MotionSnapshotDetector:
    """Motion detector che NON apre la camera: legge snapshot JPEG da un URL HTTP
    (es. go2rtc API: http://localhost:1984/api/frame.jpeg?src=pi5cam_h264).

    Esegue fetch + diff in un THREAD DEDICATO per non bloccare il main loop di
    Kivy (urllib.urlopen blocca ~200-300 ms a snapshot). Il callback `on_motion`
    viene invocato dal thread di background: il main app deve schedulare
    l'azione UI con Clock.schedule_once(...).
    """

    def __init__(
        self,
        snapshot_url: str,
        pixel_thresh: int = 25,
        area_thresh_pct: float = 1.5,
        cooldown_sec: float = 1.5,
        thumb_size: int = 160,
        timeout_sec: float = 1.5,
        tick_hz: float = 2.0,
        debug_log_every: int = 20,
    ):
        self.url = snapshot_url
        self.pixel_thresh = pixel_thresh
        self.area_thresh_pct = area_thresh_pct
        self.cooldown_sec = cooldown_sec
        self.thumb_size = thumb_size
        self.timeout = timeout_sec
        self.interval = 1.0 / max(0.5, tick_hz)
        self.debug_log_every = max(0, int(debug_log_every))
        self._prev = None
        self._last_event = 0.0
        self._cb: Optional[Callable[[], None]] = None
        self._fail_count = 0
        self._tick_n = 0
        self._stop = None
        self._thread = None

    def on_motion(self, cb: Callable[[], None]) -> None:
        self._cb = cb

    def is_available(self) -> bool:
        return True

    def start(self) -> None:
        import threading
        if self._thread and self._thread.is_alive():
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="motion-snap", daemon=True)
        self._thread.start()
        LOG.info("MotionSnapshotDetector thread avviato (interval=%.2fs)", self.interval)

    def stop(self) -> None:
        if self._stop:
            self._stop.set()
        t = self._thread
        if t and t.is_alive():
            try:
                t.join(timeout=3.0)
            except Exception:
                pass
        self._thread = None
        self._stop = None
        self._prev = None

    # Compat con la vecchia interfaccia (no-op: il loop è autonomo)
    def tick(self) -> bool:
        return False

    def _fetch_thumb(self):
        import urllib.request
        from PIL import Image
        from io import BytesIO
        import numpy as np
        with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
            data = r.read()
        img = Image.open(BytesIO(data)).convert("L")
        img.thumbnail((self.thumb_size, self.thumb_size))
        return np.asarray(img, dtype="int16")

    def _loop(self):
        import numpy as np
        while self._stop and not self._stop.is_set():
            t0 = time.time()
            try:
                gray = self._fetch_thumb()
                self._fail_count = 0
            except Exception as e:
                self._fail_count += 1
                self._prev = None
                if self._fail_count in (1, 5, 30) or self._fail_count % 60 == 0:
                    LOG.warning("motion snapshot fetch fallita (n=%d): %s", self._fail_count, e)
                if self._fail_count in (5, 15, 30) or (
                        self._fail_count >= 10 and self._fail_count % 30 == 0):
                    try:
                        from modules.go2rtc_control import ensure_running_for_motion
                        ensure_running_for_motion()
                    except Exception:
                        pass
                # backoff piccolo su errori
                self._stop.wait(self.interval * 2)
                continue

            try:
                self._tick_n += 1
                if self._prev is None or self._prev.shape != gray.shape:
                    self._prev = gray
                else:
                    diff = np.abs(gray - self._prev)
                    self._prev = gray
                    changed = int((diff > self.pixel_thresh).sum())
                    total = gray.size
                    pct = (changed / total) * 100 if total else 0
                    if pct >= _GLITCH_PCT:
                        LOG.warning(
                            "motion snapshot glitch (%.1f%%), reset baseline", pct)
                        self._prev = gray
                        continue
                    if self.debug_log_every and (self._tick_n % self.debug_log_every == 0):
                        LOG.info(
                            "motion debug: tick=%d avg_diff=%.2f changed=%.2f%% (thr=%d, area=%.2f%%)",
                            self._tick_n, float(diff.mean()), pct,
                            self.pixel_thresh, self.area_thresh_pct,
                        )
                    if pct >= self.area_thresh_pct:
                        now = time.time()
                        if now - self._last_event >= self.cooldown_sec:
                            self._last_event = now
                            LOG.info("MOTION rilevato (%.2f%% pixel cambiati)", pct)
                            if self._cb:
                                try:
                                    self._cb()
                                except Exception as e:
                                    LOG.error("motion cb err: %s", e)
            except Exception as e:
                LOG.error("motion snapshot loop err: %s", e)

            elapsed = time.time() - t0
            wait = max(0.0, self.interval - elapsed)
            if wait:
                self._stop.wait(wait)

    def reset(self) -> None:
        self._prev = None
