"""Auto-enroll incrementale.

Quando un utente apre la porta tramite PIN o NFC, e c'e' una camera
disponibile, salviamo il frame corrente nella sua libreria volti come
ulteriore campione (es. `auto_<ts>.jpg`). Nel tempo ogni utente
accumula varianti (illuminazione, angolazioni, occhiali...) che
migliorano le successive recognition.

Per evitare di esplodere il dataset:
  - max N foto auto per utente (default 30, FIFO sulle piu' vecchie)
  - skip se l'ultimo auto e' < cooldown_sec (default 6h)
  - skip se nel frame non c'e' un volto (controllo via engine.encode_frame)

Le foto auto sono indistinguibili per nome dalle manuali, ma riconoscibili
dal prefisso "auto_". Possono essere bulk-deleted da HA se introducono
drift.

Ritorno `maybe_enroll`: "enrolled" | "rejected" | "skipped".
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Literal, Optional

import numpy as np

AutoEnrollStatus = Literal["enrolled", "rejected", "skipped"]

LOG = logging.getLogger(__name__)


def _safe_name(s: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join(c for c in (s or "").strip() if c not in bad).strip().replace(" ", "_")


class AutoEnroller:
    def __init__(self, cfg: Optional[dict] = None,
                 storage_dir: str = "data/faces") -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.max_per_user = int(cfg.get("max_per_user", 30))
        self.cooldown_sec = int(cfg.get("cooldown_sec", 6 * 3600))
        self.verify_identity = bool(cfg.get("verify_identity", True))
        self.storage_dir = storage_dir
        self._lock = threading.RLock()

    def _user_dir(self, nome: str) -> str:
        return os.path.join(self.storage_dir, _safe_name(nome))

    def _last_auto_age(self, ud: str) -> float:
        try:
            files = [f for f in os.listdir(ud) if f.startswith("auto_")]
            if not files:
                return float("inf")
            files.sort()
            mtime = os.path.getmtime(os.path.join(ud, files[-1]))
            return time.time() - mtime
        except Exception:
            return float("inf")

    def _rotate(self, ud: str) -> None:
        try:
            files = sorted(f for f in os.listdir(ud) if f.startswith("auto_"))
            excess = max(0, len(files) - self.max_per_user)
            for old in files[:excess]:
                try:
                    os.remove(os.path.join(ud, old))
                except Exception:
                    pass
        except Exception:
            pass

    def maybe_enroll(self, nome: str,
                     rgb: Optional[np.ndarray],
                     face_engine: Any = None) -> AutoEnrollStatus:
        """Tenta di salvare un nuovo campione 'auto_'."""
        if not self.enabled or not nome or rgb is None or rgb.size == 0:
            return "skipped"
        nome_s = _safe_name(nome)
        ud = self._user_dir(nome_s)
        if not os.path.isdir(ud):
            return "skipped"
        if self._last_auto_age(ud) < self.cooldown_sec:
            return "skipped"
        if face_engine is not None:
            try:
                emb = face_engine.encode_frame(rgb)
                if emb is None:
                    return "skipped"
                if self.verify_identity:
                    match = face_engine.scan_frame(rgb)
                    if not match or not match.get("match"):
                        LOG.debug(
                            "auto-enroll skip %s: volto non riconosciuto (dist=%s)",
                            nome_s,
                            None if not match else match.get("distance"),
                        )
                        return "rejected"
                    matched = _safe_name(str(match.get("nome", "")))
                    if matched != nome_s:
                        LOG.warning(
                            "auto-enroll rifiutato: atteso=%s rilevato=%s dist=%.3f margin=%.3f",
                            nome_s, matched,
                            float(match.get("distance", -1)),
                            float(match.get("margin", -1)),
                        )
                        return "rejected"
            except Exception as e:
                LOG.debug("auto-enroll verify err: %s", e)
                return "skipped"
        ts = time.strftime("%Y%m%d-%H%M%S")
        out = os.path.join(ud, f"auto_{ts}.jpg")
        try:
            import cv2
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            ok = cv2.imwrite(out, bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            if not ok:
                return "skipped"
        except Exception as e:
            LOG.debug("auto_enroll write err: %s", e)
            return "skipped"
        self._rotate(ud)
        if face_engine is not None:
            try:
                face_engine.reload_library()
            except Exception:
                pass
        LOG.info("auto-enroll: %s -> %s", nome_s, out)
        return "enrolled"
