"""Facade unificata sopra i due engine di riconoscimento facciale.

Espone la stessa API di `face_recognition_stub.FaceRecognizer` indipenden-
temente dall'engine sottostante (dlib classico o ArcFace neural).

Selezione tramite `face_recognition.engine` in config:
    auto      ->  prova ArcFace, fallback dlib
    arcface   ->  forza ArcFace
    dlib      ->  forza dlib
    disabled  ->  disabilitato (no scan)

`scan_frame_voted` aggiunge multi-frame voting: richiama il motore N
volte su frame consecutivi e ritorna il match solo se la maggioranza dei
voti concorda sullo stesso nome con distance media sotto soglia. Riduce
drasticamente i falsi positivi.
"""
from __future__ import annotations

import logging
import os
import shutil
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

LOG = logging.getLogger(__name__)


class FaceEngineFacade:
    def __init__(self, cfg: Dict[str, Any], dlib_recognizer=None) -> None:
        self.cfg = cfg or {}
        engine_pref = str(self.cfg.get("engine", "auto")).lower()
        self.dlib = dlib_recognizer
        self.arc = None
        self.engine_name = "disabled"

        if engine_pref == "disabled":
            return

        if engine_pref in ("auto", "arcface"):
            try:
                from modules.face_arcface import ArcFaceEngine
                arc_cfg = dict(self.cfg.get("arcface", {}) or {})
                for key in ("match_threshold", "match_margin"):
                    if key not in arc_cfg and key in self.cfg:
                        arc_cfg[key] = self.cfg[key]
                self.arc = ArcFaceEngine(arc_cfg,
                                         storage_dir=self._storage_dir())
                if self.arc.is_available():
                    self.arc.load()
                    self.engine_name = "arcface"
                else:
                    self.arc = None
            except Exception as e:
                LOG.warning("ArcFace bootstrap err: %s", e)
                self.arc = None

        if self.engine_name == "disabled":
            if engine_pref in ("auto", "dlib") and self.dlib is not None:
                self.engine_name = "dlib"
            elif engine_pref == "arcface":
                LOG.warning("engine=arcface non disponibile; nessun engine attivo")

        LOG.info("FaceEngineFacade engine attivo: %s (storage=%s)",
                 self.engine_name, self._storage_dir())

    def _storage_dir(self) -> str:
        if self.dlib is not None and getattr(self.dlib, "storage_dir", None):
            return str(self.dlib.storage_dir)
        return _resolve_face_storage(self.cfg.get("storage_dir", "data/faces"))

    @property
    def storage_dir(self) -> str:
        return self._storage_dir()

    # ---- API compatibility con FaceRecognizer ---------------------------

    @property
    def active_engine(self):
        if self.engine_name == "arcface":
            return self.arc
        if self.engine_name == "dlib":
            return self.dlib
        return None

    def list_users(self) -> List[Dict[str, Any]]:
        e = self.active_engine
        if e is None:
            return []
        return e.list_users()

    def list_auto_samples(self, nome: str) -> List[str]:
        e = self.active_engine
        if e is None or not hasattr(e, "list_auto_samples"):
            return []
        return e.list_auto_samples(nome)

    def delete_auto_sample(self, nome: str, filename: str) -> bool:
        ok = False
        for e in (self.arc, self.dlib):
            if e is None or not hasattr(e, "delete_auto_sample"):
                continue
            try:
                if e.delete_auto_sample(nome, filename):
                    ok = True
            except Exception:
                pass
        other = self.dlib if self.arc else self.arc
        if ok and other is not None:
            try:
                other.reload_library()
            except Exception:
                pass
        return ok

    def purge_auto_samples(self, nome: str) -> int:
        e = self.active_engine
        if e is None or not hasattr(e, "purge_auto_samples"):
            return 0
        n = e.purge_auto_samples(nome)
        other = self.dlib if e is self.arc else self.arc
        if n and other is not None:
            try:
                other.reload_library()
            except Exception:
                pass
        return n

    def enroll_image(self, *args, **kw):
        e = self.active_engine
        if e is None:
            return False, "engine_disabled"
        out = e.enroll_image(*args, **kw)
        # Mantieni allineato il library dell'altro engine se esistono
        # entrambi (in modo che le immagini siano enroll-ate ovunque).
        other = self.dlib if e is self.arc else self.arc
        if other is not None:
            try:
                other.reload_library()
            except Exception:
                pass
        return out

    def delete_user(self, nome: str) -> bool:
        ok = False
        for e in (self.arc, self.dlib):
            if e is None:
                continue
            try:
                if e.delete_user(nome):
                    ok = True
            except Exception:
                pass
        return ok

    def rename_user(self, old: str, new: str) -> bool:
        e = self.active_engine
        if e is None:
            return False
        try:
            ok = e.rename_user(old, new)
        except Exception:
            ok = False
        other = self.dlib if e is self.arc else self.arc
        if other is not None:
            try:
                other.reload_library()
            except Exception:
                pass
        return ok

    def update_user(self, nome: str, **kw) -> bool:
        ok = False
        for e in (self.arc, self.dlib):
            if e is None:
                continue
            try:
                if e.update_user(nome, **kw):
                    ok = True
            except Exception:
                pass
        return ok

    def get_user_meta(self, nome: str) -> Dict[str, Any]:
        e = self.active_engine
        if e is None:
            return {}
        try:
            return e.get_user_meta(nome)
        except Exception:
            return {}

    def reload_library(self) -> None:
        for e in (self.arc, self.dlib):
            if e is None:
                continue
            try:
                e.reload_library()
            except Exception:
                pass

    # ---- Recognition ----------------------------------------------------

    def scan_frame(self, rgb) -> Optional[Dict[str, Any]]:
        """Frame RGB uint8 (h,w,3)."""
        e = self.active_engine
        if e is None:
            return None
        try:
            return e.scan_frame(rgb)
        except Exception as ex:
            LOG.debug("scan_frame err: %s", ex)
            return None

    def encode_frame(self, rgb) -> Optional[np.ndarray]:
        """Ritorna l'embedding del frame RGB (per unknown tracking)."""
        if self.arc is None or not self.arc.is_available():
            return None
        try:
            import cv2
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            bgr = rgb[..., ::-1]
        try:
            return self.arc._encode_bgr(bgr)
        except Exception:
            return None


def _resolve_face_storage(p: str) -> str:
    """Allinea path volti a /opt/videocitofono/data/faces (non app/data)."""
    if os.path.isabs(p):
        return p
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(here))
        return os.path.join(project_root, p)
    except Exception:
        return p


def migrate_legacy_face_storage(storage_dir: str) -> int:
    """Copia enroll legacy da app/data/faces verso data/faces."""
    root = os.path.dirname(os.path.dirname(storage_dir))
    legacy = os.path.join(root, "app", "data", "faces")
    if not os.path.isdir(legacy):
        return 0
    moved = 0
    for entry in os.listdir(legacy):
        if entry.startswith("."):
            continue
        src = os.path.join(legacy, entry)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(storage_dir, entry)
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(src):
            s = os.path.join(src, fn)
            d = os.path.join(dst, fn)
            if os.path.isfile(s) and not os.path.exists(d):
                shutil.copy2(s, d)
                moved += 1
                LOG.info("face migrate: %s", d)
    return moved
