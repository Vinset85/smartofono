"""Riconoscimento volto del visitatore durante lo squillo (CallingScreen).

Analizza frame dalla stessa Picamera2 usata da LiveKit (callback opzionale
in livekit_client) e, con voting multi-frame, pubblica su MQTT:
  videocitofono/evento  {"tipo":"visitatore_riconosciuto","dati":{"nome":...}}

Se entro timeout_sec non c'e' match, non pubblica nulla (nessun annuncio).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from typing import Any, Callable, Dict, Optional

import numpy as np

LOG = logging.getLogger(__name__)

CameraFrameCallback = Callable[[np.ndarray, int, int], None]


def _display_name(nome: str, meta: Optional[Dict[str, Any]] = None) -> str:
    meta = meta or {}
    for key in ("display_nome", "label", "nome"):
        v = str(meta.get(key, "") or "").strip()
        if v:
            return v
    return (nome or "").replace("_", " ").strip()


class CallVisitorRecognizer:
    def __init__(self, face, mqtt, cfg: Optional[dict] = None) -> None:
        cfg = cfg or {}
        self._face = face
        self._mqtt = mqtt
        self._enabled = bool(cfg.get("enabled", True))
        self._timeout_sec = float(cfg.get("timeout_sec", 10.0))
        self._scan_interval = float(cfg.get("scan_interval_sec", 0.45))
        self._vote_window = int(cfg.get("vote_window", 5))
        self._vote_required = int(cfg.get("vote_required", 3))
        self._camera_rotation = int(cfg.get("camera_rotation", 0))
        self._match_threshold = float(cfg.get("match_threshold", 0.0))
        self._lock = threading.Lock()
        self._scan_busy = False
        self._scan_count = 0
        self._active = False
        self._done = False
        self._votes: list[str] = []
        self._last_scan = 0.0
        self._t0 = 0.0
        self._lk = None

    def start(self, lk_session) -> None:
        if not self._enabled:
            return
        if getattr(self._face, "engine_name", "disabled") == "disabled":
            LOG.info("call_visitor_recognition: face engine disabilitato, skip")
            return
        # Non chiamare stop() qui: start() tiene gia' _lock e stop() ri-acquisisce
        # lo stesso Lock -> deadlock sul main thread Kivy (UI congelata).
        with self._lock:
            self._active = False
            self._done = False
            self._scan_busy = False
            self._votes = []
            self._last_scan = 0.0
            self._t0 = time.monotonic()
            self._lk = lk_session
            self._active = True
        try:
            lk_session.set_on_camera_frame(self._on_frame)
        except Exception as e:
            LOG.warning("call_visitor_recognition: hook frame err: %s", e)
        LOG.info("call_visitor_recognition: avviato (timeout=%.0fs)", self._timeout_sec)

    def stop(self, unhook: bool = True) -> None:
        lk = self._lk
        with self._lock:
            self._active = False
            self._lk = None
        if unhook and lk is not None:
            try:
                lk.set_on_camera_frame(None)
            except Exception:
                pass

    def _on_frame(self, rgb: np.ndarray, width: int, height: int) -> None:
        with self._lock:
            if not self._active or self._done or self._scan_busy:
                return
            now = time.monotonic()
            if now - self._last_scan < self._scan_interval:
                return
            if now - self._t0 > self._timeout_sec:
                self._active = False
                LOG.info("call_visitor_recognition: timeout senza match")
                return
            self._last_scan = now
            self._scan_busy = True
        rgb_scan = self._prepare_rgb(rgb.copy())
        try:
            match = self._face.scan_frame(rgb_scan)
        except Exception as e:
            LOG.debug("call_visitor_recognition scan err: %s", e)
            return
        finally:
            with self._lock:
                self._scan_busy = False
                self._scan_count += 1
        if not match or not match.get("match"):
            if match and match.get("best_user"):
                if self._scan_count <= 3 or self._scan_count % 8 == 0:
                    LOG.info(
                        "call_visitor_recognition: no match (best=%s dist=%.3f)",
                        match.get("best_user"),
                        float(match.get("distance", 0)),
                    )
            elif self._scan_count <= 2 or self._scan_count % 10 == 0:
                LOG.info("call_visitor_recognition: scan #%d, volto non rilevato",
                         self._scan_count)
            return
        nome_key = str(match.get("nome") or "")
        if not nome_key:
            return
        with self._lock:
            if self._done:
                return
            self._votes.append(nome_key)
            if len(self._votes) > self._vote_window:
                self._votes = self._votes[-self._vote_window:]
            counts = Counter(self._votes)
            best, n = counts.most_common(1)[0]
            if n < self._vote_required:
                LOG.info("call_visitor_recognition: voto %s (%d/%d)",
                         best, n, self._vote_required)
                return
            self._done = True
            self._active = False
        try:
            meta = {}
            try:
                meta = self._face.get_user_meta(best) or {}
            except Exception:
                pass
            display = _display_name(best, meta)
            self._mqtt.publish_evento(
                "visitatore_riconosciuto",
                {
                    "nome": display,
                    "id": best,
                    "distance": float(match.get("distance", 0)),
                },
            )
            try:
                from modules.log_setup import audit as _audit
                _audit(LOG, "visitatore_riconosciuto", nome=display,
                       id=best, distance=float(match.get("distance", 0)))
            except Exception:
                pass
            LOG.info("call_visitor_recognition: match %s (%d/%d voti)",
                     display, n, self._vote_window)
        except Exception as e:
            LOG.warning("call_visitor_recognition mqtt err: %s", e)
        finally:
            lk = self._lk
            if lk is not None:
                try:
                    lk.set_on_camera_frame(None)
                except Exception:
                    pass

    def _prepare_rgb(self, rgb: np.ndarray) -> np.ndarray:
        rot = int(self._camera_rotation or 0) % 360
        if rot == 180:
            return np.rot90(rgb, 2)
        if rot == 90:
            return np.rot90(rgb, 1)
        if rot == 270:
            return np.rot90(rgb, 3)
        return rgb
