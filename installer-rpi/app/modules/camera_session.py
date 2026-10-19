"""Singleton camera session: gestisce un solo `Picamera2` istanziato dopo
il boot e fa switch_mode (stop/configure/start) quando si passa fra
modalita' motion (320x240 YUV @ 2fps) e face (640x480 RGB @ 10fps).

Motivazione: aprire/chiudere ripetutamente Picamera2() su Pi5 lascia la
libcamera in stato 'Configured' bloccato (errore "Camera __init__ sequence
did not complete"), recuperabile solo riavviando il process. Tenendo
l'oggetto vivo e usando solo `cam.stop() / cam.configure() / cam.start()`
si evita il problema, perche' la libcamera resta sempre nello stesso ciclo
di acquire del device.

API:
    sess = PicamSession.instance()
    sess.acquire("motion")      # apre se chiuso, riconfigura se mode diverso
    arr = sess.capture("motion")  # numpy array (per motion: YUV planar)
    ...
    sess.acquire("face")        # switch a face (no close)
    bgr = sess.capture("face")  # ndarray BGR
    ...
    sess.release()              # solo per liberare in calling/conversation
                                # (LiveKit usa libcamera in esclusiva)

Thread-safety: i metodi sono protetti da lock; capture() puo' essere
chiamato dal thread del consumer mentre acquire/release dal main thread.
Non si supportano consumer concorrenti su modi diversi (un solo modo
attivo alla volta).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)


# Configurazioni per modalita'. Tutti i parametri sono espressi in modo
# da poter chiamare cam.create_video_configuration(**MODE_CFG[mode])
MODE_CFG: Dict[str, Dict[str, Any]] = {
    "motion": {
        "main": {"size": (320, 240), "format": "YUV420"},
        "controls": {"FrameRate": 2.0},
    },
    "face": {
        "main": {"size": (640, 480), "format": "RGB888"},
        "controls": {"FrameRate": 10.0},
    },
    # Anteprima dashboard HA: JPEG via MQTT, niente WebRTC nel browser.
    "preview": {
        "main": {"size": (640, 360), "format": "YUV420"},
        "controls": {"FrameRate": 5.0},
    },
}


class PicamSession:
    _inst_lock = threading.Lock()
    _inst: Optional["PicamSession"] = None

    # Recovery pesante (stop go2rtc + hard_close + reopen) eseguito al
    # massimo una volta ogni N secondi: senza cooldown un consumer che
    # chiama acquire() ogni 3-5s (motion) lo rilancerebbe di continuo,
    # facendo thrash di go2rtc e floodando il journal.
    RECOVERY_COOLDOWN_SEC = 12.0

    @classmethod
    def instance(cls) -> "PicamSession":
        with cls._inst_lock:
            if cls._inst is None:
                cls._inst = PicamSession()
            return cls._inst

    def __init__(self):
        self._lock = threading.Lock()
        self._cam = None
        self._mode: Optional[str] = None
        self._held: Optional[str] = None
        self._available = True  # diventa False se libcamera non disponibile
        self._acquire_fail_count = 0
        self._last_recovery_ts = 0.0

    # ----------------------------- public API ------------------------------

    def set_call_mode(self, width: int, height: int, fps: float) -> None:
        """Registra/aggiorna il profilo 'call' usato dal publisher LiveKit.

        Cosi' la cattura durante la videochiamata passa per QUESTO stesso
        Picamera2 (switch di modo) invece di istanziare un secondo oggetto:
        su Pi5 due Picamera2 concorrenti o aperture/chiusure ripetute
        lasciano libcamera bloccata in stato 'Running/Configured' ->
        buffer vuoti -> immagine verde dalla 2a chiamata in poi."""
        MODE_CFG["call"] = {
            "main": {"size": (int(width), int(height)), "format": "YUV420"},
            "controls": {"FrameRate": float(fps)},
        }

    def is_available(self) -> bool:
        return self._available and self._import_ok()

    def hold(self, mode: str) -> None:
        """Impedisce agli altri consumatori di cambiare modo.

        LiveKit (chiamata o anteprima) tiene il sensore: senza hold il
        thread motion, restando su home, rifa' acquire('motion') e
        riconfigura a 320x240. Il publisher resta senza frame nuovi e
        il browser HA congela il primo fotogramma.
        """
        with self._lock:
            self._held = str(mode)

    def unhold(self, mode: Optional[str] = None) -> None:
        with self._lock:
            if mode is None or self._held == mode:
                self._held = None

    def acquire(self, mode: str) -> bool:
        """Garantisce che la camera sia avviata in `mode`. Idempotente.
        Restituisce True se ok, False altrimenti."""
        if mode not in MODE_CFG:
            LOG.error("PicamSession.acquire: mode sconosciuto %r", mode)
            return False
        with self._lock:
            if self._held and mode != self._held:
                LOG.warning(
                    "PicamSession.acquire(%s) ignorato: hold=%s",
                    mode, self._held)
                return False
            if not self._import_ok():
                self._available = False
                return False
            try:
                if self._cam is None:
                    self._open()
                if self._mode != mode:
                    self._switch(mode)
                ok = self._cam is not None and self._mode == mode
                if ok:
                    self._acquire_fail_count = 0
                return ok
            except Exception as e:
                now = time.monotonic()
                self._acquire_fail_count += 1
                # Log rate-limited (1a volta poi ogni 30 fail).
                if self._acquire_fail_count == 1 or self._acquire_fail_count % 30 == 0:
                    LOG.error("PicamSession.acquire(%s) err (#%d): %s",
                              mode, self._acquire_fail_count, e)
                # Recovery pesante con cooldown: il primo fail prova subito
                # (last_recovery_ts=0), i successivi al massimo ogni
                # RECOVERY_COOLDOWN_SEC -> niente thrash di go2rtc.
                if now - self._last_recovery_ts < self.RECOVERY_COOLDOWN_SEC:
                    return False
                self._last_recovery_ts = now
                # go2rtc (rpicam-vid) puo' tenere libcamera dopo una chiamata.
                try:
                    from modules.go2rtc_control import pause_for_camera, is_paused
                    if not is_paused():
                        pause_for_camera()
                    time.sleep(0.5)
                except Exception:
                    pass
                self._hard_close()
                try:
                    self._open()
                    self._switch(mode)
                    if self._cam is not None and self._mode == mode:
                        self._acquire_fail_count = 0
                        LOG.info("PicamSession recovery OK (mode=%s)", mode)
                        return True
                    return False
                except Exception as e2:
                    if self._acquire_fail_count <= 1 or self._acquire_fail_count % 30 == 0:
                        LOG.error("PicamSession recovery failed: %s", e2)
                    return False

    def capture(self, mode: str):
        """Cattura un frame solo se la sessione e' in `mode`. Ritorna None
        in caso di errore o mode mismatch."""
        with self._lock:
            if self._cam is None or self._mode != mode:
                return None
            try:
                return self._cam.capture_array("main")
            except Exception as e:
                LOG.warning("PicamSession.capture(%s) err: %s", mode, e)
                return None

    def release(self) -> None:
        """Chiude completamente la camera. Da usare quando un consumer
        esterno (LiveKit) deve avere accesso esclusivo alla libcamera.
        Idempotente."""
        with self._lock:
            self._hard_close()

    # ----------------------------- internal --------------------------------

    def _import_ok(self) -> bool:
        try:
            import picamera2  # noqa: F401
            return True
        except Exception as e:
            LOG.warning("picamera2 non disponibile: %s", e)
            return False

    def _open(self) -> None:
        from picamera2 import Picamera2  # type: ignore
        cam = Picamera2()
        # Configurazione iniziale: usiamo motion come default (carico minimo).
        cfg = cam.create_video_configuration(**MODE_CFG["motion"])
        cam.configure(cfg)
        cam.start()
        self._cam = cam
        self._mode = "motion"
        LOG.info("PicamSession opened (mode=motion 320x240@2fps)")

    def _switch(self, mode: str) -> None:
        cam = self._cam
        if cam is None:
            return
        # Picamera2 raccomanda stop -> configure -> start per cambio
        # significativo di formato/risoluzione/fps.
        try:
            cam.stop()
        except Exception as e:
            LOG.warning("PicamSession.stop pre-switch err: %s", e)
        cfg = cam.create_video_configuration(**MODE_CFG[mode])
        cam.configure(cfg)
        cam.start()
        self._mode = mode
        sz = MODE_CFG[mode]["main"]["size"]
        fr = MODE_CFG[mode]["controls"]["FrameRate"]
        LOG.info("PicamSession switched -> mode=%s (%dx%d@%.1ffps)",
                 mode, sz[0], sz[1], fr)

    def _hard_close(self) -> None:
        cam = self._cam
        self._cam = None
        self._mode = None
        if cam is None:
            return
        try:
            cam.stop()
        except Exception:
            pass
        try:
            cam.close()
        except Exception:
            pass
        # Lascia ~120ms al kernel per rilasciare il device.
        time.sleep(0.12)
