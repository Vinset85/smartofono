"""Anti-spoofing minimalista: blink detection con dlib 68 landmarks.

L'idea: una foto stampata o lo schermo di un cellulare mostrano occhi
sempre aperti; una persona reale, durante una scansione di 3-5 secondi,
batte le palpebre almeno una volta. Calcoliamo l'EAR (Eye Aspect Ratio)
sui 6 landmark di ciascun occhio e contiamo come "blink" il passaggio da
frame con EAR sopra soglia (occhi aperti) a `consec_frames` sotto soglia.

Riferimento: Soukupová & Čech, "Real-Time Eye Blink Detection using
Facial Landmarks" (2016). Tipicamente EAR ~0.30 ad occhi aperti, ~0.15
durante un blink.

API:
    from modules.liveness import LivenessChecker
    chk = LivenessChecker()
    chk.update(rgb_frame)        # chiamato ad ogni frame
    chk.blinks                   # int, n. ammiccamenti rilevati
    chk.is_alive(min_blinks=1)   # True dopo abbastanza blink

Se dlib non e' installato, `is_alive()` ritorna sempre True (no-op).
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np

LOG = logging.getLogger(__name__)

_PREDICTOR_PATHS = (
    "/opt/videocitofono/data/shape_predictor_68_face_landmarks.dat",
    "data/shape_predictor_68_face_landmarks.dat",
    "/usr/share/dlib/shape_predictor_68_face_landmarks.dat",
)


def _euclid(a, b) -> float:
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def _ear(eye_pts) -> float:
    # eye_pts: 6 landmark (p1..p6) come da convenzione iBug 68.
    a = _euclid(eye_pts[1], eye_pts[5])
    b = _euclid(eye_pts[2], eye_pts[4])
    c = _euclid(eye_pts[0], eye_pts[3])
    if c <= 0:
        return 0.0
    return (a + b) / (2.0 * c)


class LivenessChecker:
    def __init__(self,
                 ear_threshold: float = 0.21,
                 consec_frames: int = 2,
                 min_blinks: int = 1) -> None:
        self.ear_threshold = float(ear_threshold)
        self.consec_frames = max(1, int(consec_frames))
        self.min_blinks_default = int(min_blinks)
        self._below = 0
        self._seen_open = False
        self.blinks = 0
        # Diagnostica: quanti frame hanno prodotto un EAR e quanto in basso e'
        # arrivato. Senza questi numeri un liveness che non conferma mai non si
        # distingue da un volto che non viene mai trovato.
        self.frames_face = 0
        self.ear_min: Optional[float] = None
        self._available: Optional[bool] = None
        self._detector = None
        self._predictor = None

    def reset(self) -> None:
        self._below = 0
        self._seen_open = False
        self.blinks = 0
        self.frames_face = 0
        self.ear_min = None

    def _ensure(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import dlib  # type: ignore
        except Exception:
            self._available = False
            return False
        path = ""
        import os
        for p in _PREDICTOR_PATHS:
            if os.path.exists(p):
                path = p
                break
        if not path:
            LOG.warning("liveness: shape_predictor_68 mancante, disattivato")
            self._available = False
            return False
        try:
            self._detector = dlib.get_frontal_face_detector()
            self._predictor = dlib.shape_predictor(path)
            self._available = True
            LOG.info("liveness: blink detector pronto (model=%s)", path)
        except Exception as e:
            LOG.warning("liveness init err: %s", e)
            self._available = False
        return self._available

    def is_supported(self) -> bool:
        return self._ensure()

    def update(self, rgb: np.ndarray) -> Optional[float]:
        """Aggiorna lo stato col nuovo frame; ritorna EAR corrente."""
        if not self._ensure() or rgb is None or rgb.size == 0:
            return None
        try:
            gray = self._to_gray(rgb)
            # Downsample per velocità (dlib su 320px basta per EAR). La copia
            # contigua non è un vezzo: su una vista con stride dlib non solleva
            # errori, restituisce semplicemente zero volti, e il liveness non
            # confermerebbe mai nulla.
            if gray.shape[0] > 240:
                gray = np.ascontiguousarray(gray[::2, ::2])
            faces = self._detector(gray, 0)
            if not faces:
                return None
            f = max(faces, key=lambda r: (r.right() - r.left()) * (r.bottom() - r.top()))
            shape = self._predictor(gray, f)
            pts = [(shape.part(i).x, shape.part(i).y) for i in range(68)]
            left_eye = pts[36:42]
            right_eye = pts[42:48]
            ear = (_ear(left_eye) + _ear(right_eye)) / 2.0
            self.frames_face += 1
            if self.ear_min is None or ear < self.ear_min:
                self.ear_min = ear
            if ear < self.ear_threshold:
                self._below += 1
                # Il blink si conta appena gli occhi risultano chiusi per i
                # frame richiesti, senza attendere la riapertura: chi campiona
                # a pochi frame al secondo vedrebbe altrimenti la chiusura ma
                # non la riapertura, e il blink andrebbe perso. Il frame a
                # occhi aperti deve comunque essere arrivato prima, altrimenti
                # basterebbe una foto con gli occhi chiusi.
                if self._seen_open and self._below >= self.consec_frames:
                    self.blinks += 1
                    self._seen_open = False
            else:
                self._below = 0
                self._seen_open = True
            return ear
        except Exception as e:
            LOG.debug("liveness update err: %s", e)
            return None

    def is_alive(self, min_blinks: Optional[int] = None) -> bool:
        if not self._ensure():
            return True  # no-op se dlib mancante
        thr = self.min_blinks_default if min_blinks is None else int(min_blinks)
        return self.blinks >= thr

    @staticmethod
    def _to_gray(rgb: np.ndarray) -> np.ndarray:
        try:
            import cv2
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        except Exception:
            r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)
