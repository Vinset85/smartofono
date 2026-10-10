"""Wrapper camera per preview UI (separato dallo stream WebRTC di go2rtc).

Usa picamera2 se disponibile (RPi camera native), altrimenti OpenCV come fallback.
"""
from __future__ import annotations

import logging
from typing import Optional

LOG = logging.getLogger(__name__)


class CameraPreview:
    """Espone get_frame() -> numpy ndarray BGR oppure None se non disponibile."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._cap = None
        self._picam = None
        self._kind = None
        if not cfg.get("enabled", False):
            LOG.info("Camera preview locale disabilitata (camera dedicata a go2rtc)")
            return
        self._init()

    def _init(self) -> None:
        # Tentativo picamera2 (preferito su RPi5)
        try:
            from picamera2 import Picamera2  # type: ignore
            self._picam = Picamera2()
            cfgp = self._picam.create_preview_configuration(
                main={"size": (self.cfg.get("preview_width", 640), self.cfg.get("preview_height", 480))}
            )
            self._picam.configure(cfgp)
            self._picam.start()
            self._kind = "picamera2"
            LOG.info("Camera preview: picamera2")
            return
        except Exception as e:
            LOG.info("picamera2 non disponibile: %s", e)
        # Fallback OpenCV
        try:
            import cv2  # type: ignore
            self._cap = cv2.VideoCapture(self.cfg.get("device", 0))
            if not self._cap.isOpened():
                self._cap = None
                LOG.warning("OpenCV VideoCapture non aperto")
                return
            self._cap.set(3, self.cfg.get("preview_width", 640))
            self._cap.set(4, self.cfg.get("preview_height", 480))
            self._kind = "opencv"
            LOG.info("Camera preview: opencv")
        except Exception as e:
            LOG.warning("OpenCV non disponibile: %s", e)

    def get_frame(self):
        if self._kind == "picamera2":
            try:
                arr = self._picam.capture_array()
                # picamera2 restituisce RGB; convertiamo a BGR
                import numpy as np
                return arr[:, :, ::-1].copy()
            except Exception as e:
                LOG.error("picamera2 capture error: %s", e)
                return None
        if self._kind == "opencv":
            try:
                ret, frame = self._cap.read()
                return frame if ret else None
            except Exception as e:
                LOG.error("opencv read error: %s", e)
                return None
        return None

    def stop(self) -> None:
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        try:
            if self._picam is not None:
                self._picam.stop()
        except Exception:
            pass

    def is_available(self) -> bool:
        return self._kind is not None
