"""Pausa/riprendi go2rtc per liberare libcamera a LiveKit, volto, auto-face.

go2rtc tiene `rpicam-vid` sempre attivo (stream pi5cam_h264). Picamera2
(LiveKit, motion picamera, face) non puo' condividere il sensore IMX708.

Usa reference counting: piu' consumer (chiamata, face, auto_face) possono
richiedere la pausa; go2rtc riparte solo quando tutti hanno rilasciato.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time

LOG = logging.getLogger(__name__)

SERVICE = "go2rtc.service"
RPICAM_GONE_TIMEOUT = 8.0
RPICAM_POLL = 0.2
RPICAM_READY_TIMEOUT = 12.0
RESTART_COOLDOWN_SEC = 15.0

_lock = threading.Lock()
_pause_refs = 0
_paused = False
_last_restart_ts = 0.0
_idle_go2rtc_allowed = True


def set_idle_go2rtc_allowed(allowed: bool) -> None:
    """False = dopo pause non riavviare go2rtc (motion picamera / eco)."""
    global _idle_go2rtc_allowed
    _idle_go2rtc_allowed = bool(allowed)


def idle_go2rtc_allowed() -> bool:
    with _lock:
        return _idle_go2rtc_allowed


def is_paused() -> bool:
    with _lock:
        return _paused


def pause_refs() -> int:
    with _lock:
        return _pause_refs


def _rpicam_running() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-x", "rpicam-vid"],
            capture_output=True, timeout=3, check=False)
        return r.returncode == 0
    except Exception:
        return False


def _wait_rpicam_running(timeout: float = RPICAM_READY_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _rpicam_running():
            return True
        time.sleep(RPICAM_POLL)
    return False


def wait_camera_free(timeout: float = 10.0) -> bool:
    """Attende che rpicam-vid sia assente (libcamera libera per go2rtc)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _rpicam_running():
            return True
        time.sleep(RPICAM_POLL)
    return not _rpicam_running()


def _wait_rpicam_gone(timeout: float = RPICAM_GONE_TIMEOUT) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _rpicam_running():
            return
        time.sleep(RPICAM_POLL)
    LOG.warning("rpicam-vid ancora attivo dopo stop go2rtc (timeout %.0fs)",
                timeout)


def _service_active() -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "--quiet", SERVICE],
            capture_output=True, timeout=5, check=False)
        return r.returncode == 0
    except Exception:
        return False


def pause_for_camera(tag: str = "") -> bool:
    """Ferma go2rtc e attende rilascio libcamera. Reference-counted."""
    global _paused, _pause_refs
    with _lock:
        if _paused and not _rpicam_running():
            _pause_refs += 1
            LOG.debug("go2rtc gia' fermo, ref=%d (%s)", _pause_refs, tag or "-")
            return True
        _pause_refs += 1
        if _pause_refs > 1:
            LOG.debug("go2rtc pause ref=%d (%s)", _pause_refs, tag or "-")
            return True
    try:
        if not _service_active() and not _rpicam_running():
            with _lock:
                _paused = True
            LOG.debug("go2rtc gia' assente (%s)", tag or "-")
            return True
        r = subprocess.run(
            ["sudo", "-n", "/bin/systemctl", "stop", SERVICE],
            capture_output=True, text=True, timeout=30, check=False)
        if r.returncode != 0:
            LOG.warning(
                "go2rtc stop rc=%s: %s",
                r.returncode, (r.stderr or r.stdout or "")[-200:])
            with _lock:
                _pause_refs = max(0, _pause_refs - 1)
            return False
        _wait_rpicam_gone()
        with _lock:
            _paused = True
        LOG.info("go2rtc fermato (camera libera%s)",
                 f", {tag}" if tag else "")
        return True
    except Exception as e:
        LOG.warning("go2rtc pause err: %s", e)
        with _lock:
            _pause_refs = max(0, _pause_refs - 1)
        return False


def resume_after_camera(tag: str = "", *, start_service: bool | None = None) -> bool:
    """Riavvia go2rtc quando l'ultimo consumer rilascia la camera."""
    global _paused, _pause_refs
    with _lock:
        if _pause_refs <= 0:
            return True
        _pause_refs -= 1
        if _pause_refs > 0:
            LOG.debug("go2rtc resume skipped ref=%d (%s)", _pause_refs, tag or "-")
            return True
    if start_service is None:
        start_service = _idle_go2rtc_allowed
    if not start_service:
        with _lock:
            _paused = True
        LOG.info("go2rtc ref rilasciato (%s), servizio lasciato fermo (eco)",
                 tag or "-")
        return True
    try:
        r = subprocess.run(
            ["sudo", "-n", "/bin/systemctl", "start", SERVICE],
            capture_output=True, text=True, timeout=30, check=False)
        if r.returncode != 0:
            LOG.warning(
                "go2rtc start rc=%s: %s",
                r.returncode, (r.stderr or r.stdout or "")[-200:])
            return False
        with _lock:
            _paused = False
        LOG.info("go2rtc riavviato (stream RTSP keep-alive%s)",
                 f", {tag}" if tag else "")
        return True
    except Exception as e:
        LOG.warning("go2rtc resume err: %s", e)
        return False


def _restart_service() -> bool:
    global _paused, _last_restart_ts
    now = time.time()
    if now - _last_restart_ts < RESTART_COOLDOWN_SEC:
        LOG.debug("go2rtc restart skipped (cooldown)")
        return False
    try:
        r = subprocess.run(
            ["sudo", "-n", "/bin/systemctl", "restart", SERVICE],
            capture_output=True, text=True, timeout=45, check=False)
        if r.returncode != 0:
            LOG.warning(
                "go2rtc restart rc=%s: %s",
                r.returncode, (r.stderr or r.stdout or "")[-200:])
            return False
        _last_restart_ts = now
        with _lock:
            _paused = False
        LOG.info("go2rtc riavviato (watchdog restart)")
        return True
    except Exception as e:
        LOG.warning("go2rtc restart err: %s", e)
        return False


def recover_stale_pause(*, idle_screen: bool, camera_consumer_active: bool) -> bool:
    """Su schermate idle senza consumer camera: sblocca ref go2rtc incastrati."""
    global _paused, _pause_refs
    if not idle_screen or camera_consumer_active:
        return False
    with _lock:
        refs = _pause_refs
        if refs <= 0:
            return False
    if _service_active() and _rpicam_running():
        with _lock:
            LOG.warning("go2rtc: reset %d ref stale, stream gia' attivo", refs)
            _pause_refs = 0
            _paused = False
        return True
    with _lock:
        LOG.warning("go2rtc: reset %d ref stale, rpicam assente -> restart", refs)
        _pause_refs = 0
    if not wait_camera_free(timeout=6.0):
        LOG.warning("go2rtc: libcamera occupata, skip restart stale ref")
        return False
    return _restart_service()


def stop_idle_service() -> bool:
    """Ferma go2rtc se nessun consumer camera (modalita' eco / risparmio termico)."""
    global _paused, _pause_refs
    with _lock:
        if _pause_refs > 0:
            LOG.debug("stop_idle_service skip (ref=%d)", _pause_refs)
            return False
    if not _service_active() and not _rpicam_running():
        with _lock:
            _paused = True
        return True
    try:
        r = subprocess.run(
            ["sudo", "-n", "/bin/systemctl", "stop", SERVICE],
            capture_output=True, text=True, timeout=30, check=False)
        _wait_rpicam_gone()
        with _lock:
            _paused = True
        LOG.info("go2rtc fermato (idle/eco, rc=%s)", r.returncode)
        return r.returncode == 0
    except Exception as e:
        LOG.warning("stop_idle_service err: %s", e)
        return False


def ensure_running_for_motion(*, wait_rpicam: bool = False) -> bool:
    """Se go2rtc e' fermo o rpicam-vid e' assente, riavvialo."""
    global _paused, _pause_refs
    with _lock:
        refs = _pause_refs
    if refs > 0:
        return False
    if _service_active() and _rpicam_running():
        with _lock:
            _paused = False
        return True
    if not wait_camera_free(timeout=4.0):
        return False
    ok = False
    if _service_active() and not _rpicam_running():
        LOG.warning("go2rtc attivo ma rpicam-vid assente -> restart")
        ok = _restart_service()
    elif not _service_active():
        ok = _restart_service()
    else:
        ok = resume_after_camera("watchdog")
    if ok and wait_rpicam:
        if not _wait_rpicam_running():
            LOG.warning("rpicam-vid non partito entro %.0fs dopo resume",
                        RPICAM_READY_TIMEOUT)
            return False
    return ok
