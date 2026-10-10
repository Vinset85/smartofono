"""Tracking volti sconosciuti ricorrenti.

Quando il riconoscimento facciale fallisce ma viene comunque rilevato
un volto, salviamo:
  - l'embedding (per accorpare visite della stessa persona)
  - una thumbnail per l'UI HA
  - un contatore "n. visite" e timestamp first/last seen

Se lo stesso embedding ricompare >= `notify_threshold` volte (default 3)
in `notify_window_days` (default 7), pubblichiamo un evento MQTT
`videocitofono/face/unknown_freq` con la thumbnail b64, cosi' HA puo'
notificare l'utente: "Volto sconosciuto visto 3 volte questa settimana,
vuoi enrollarlo?".

Storage:
    data/audit.sqlite    - tabella `unknowns` (vedi audit_db.py)
    data/unknowns/<id>.jpg
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import threading
import time
from typing import Any, Optional

import numpy as np

LOG = logging.getLogger(__name__)


def _embedding_id(emb: np.ndarray) -> str:
    """Hash stabile derivato dall'embedding (quantizzato per tolleranza)."""
    q = (emb * 64).astype(np.int8)  # quantizza a 8-bit
    return hashlib.sha1(q.tobytes()).hexdigest()[:16]


class UnknownFaceTracker:
    def __init__(self,
                 audit_db,
                 storage_dir: str = "data/unknowns",
                 cooldown_sec: int = 300,
                 notify_threshold: int = 3,
                 notify_window_days: int = 7,
                 dist_threshold: float = 0.4,
                 mqtt_publish=None) -> None:
        self.db = audit_db
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        self.cooldown_sec = int(cooldown_sec)
        self.notify_threshold = int(notify_threshold)
        self.notify_window_days = int(notify_window_days)
        self.dist_threshold = float(dist_threshold)
        self.mqtt_publish = mqtt_publish
        self._lock = threading.RLock()
        self._last_seen_ts: dict = {}      # id -> ts
        self._cache_emb: dict = {}         # id -> emb (per match approssimato)

    def _match_existing(self, emb: np.ndarray) -> Optional[str]:
        """Se l'embedding e' vicino a uno gia' noto, ritorna il suo id."""
        if not self._cache_emb:
            return None
        ids = list(self._cache_emb.keys())
        mat = np.stack([self._cache_emb[i] for i in ids], axis=0)
        sims = mat @ emb
        idx = int(np.argmax(sims))
        sim = float(sims[idx])
        if (1.0 - sim) <= self.dist_threshold:
            return ids[idx]
        return None

    def observe(self, emb: np.ndarray, rgb_thumb: Optional[np.ndarray] = None) -> None:
        """Registra una osservazione di volto sconosciuto."""
        if emb is None:
            return
        try:
            with self._lock:
                fid = self._match_existing(emb) or _embedding_id(emb)
                last = self._last_seen_ts.get(fid, 0)
                now = time.time()
                if now - last < self.cooldown_sec:
                    return  # debounce: stesso volto entro cooldown
                self._last_seen_ts[fid] = now
                self._cache_emb[fid] = emb

                thumb_path = ""
                if rgb_thumb is not None:
                    thumb_path = self._save_thumb(fid, rgb_thumb)

                count, is_new = self.db.upsert_unknown(fid, thumb_path)

                self.db.add_event("face_unknown",
                                  method="face", success=False,
                                  user="unknown",
                                  meta={"face_id": fid, "count": count})

                if count >= self.notify_threshold and self.mqtt_publish is not None:
                    self._notify(fid, count, thumb_path)
        except Exception as e:
            LOG.debug("UnknownTracker observe err: %s", e)

    def _save_thumb(self, fid: str, rgb: np.ndarray) -> str:
        path = os.path.join(self.storage_dir, f"{fid}.jpg")
        try:
            import cv2
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            # Resize a 128 lato lungo
            h, w = bgr.shape[:2]
            scale = 128.0 / max(h, w)
            if scale < 1.0:
                bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)))
            cv2.imwrite(path, bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        except Exception as e:
            LOG.debug("save_thumb err: %s", e)
            return ""
        return path

    def _notify(self, fid: str, count: int, thumb_path: str) -> None:
        if self.mqtt_publish is None:
            return
        thumb_b64 = ""
        try:
            if thumb_path and os.path.exists(thumb_path):
                with open(thumb_path, "rb") as f:
                    thumb_b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception:
            pass
        payload = {
            "face_id": fid,
            "count": count,
            "thumb_b64": thumb_b64,
            "ts": int(time.time()),
        }
        try:
            self.mqtt_publish("videocitofono/face/unknown_freq",
                              json.dumps(payload), False)
        except Exception as e:
            LOG.debug("unknown notify err: %s", e)
