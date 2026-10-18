"""Backup automatico volti + PIN + config.

Ogni N ore (default 24) crea un archivio tar.gz dei dati critici e li
ruota in `dest_dir` mantenendo solo gli ultimi `keep` snapshot.

Contenuto backup:
    data/faces/                       (immagini volti registrati)
    data/users.json                   (utenti+PIN, hash bcrypt)
    data/guest_pins.json
    data/nfc_tags.json
    config/config.override.yaml       (override applicati da HA)
    data/audit.sqlite                 (audit DB se presente)

Trigger:
    - all'avvio: cerca l'ultimo snapshot, se piu' vecchio di interval, ne fa uno
    - thread daemon che fa snapshot ogni interval

Uso:
    from modules.backup import BackupRunner
    runner = BackupRunner(cfg.get("backup", {}))
    runner.start()
"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import threading
import time
from typing import Any, Dict, Iterable, List, Optional


LOG = logging.getLogger(__name__)


def _list_snapshots(dest_dir: str) -> List[str]:
    if not os.path.isdir(dest_dir):
        return []
    items = []
    for fn in os.listdir(dest_dir):
        if fn.startswith("vc-backup-") and fn.endswith(".tar.gz"):
            items.append(os.path.join(dest_dir, fn))
    items.sort()
    return items


class BackupRunner:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None,
                 root: str = "/opt/videocitofono") -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.dest_dir = str(cfg.get("dest_dir", os.path.join(root, "backups")))
        self.interval_hours = float(cfg.get("interval_hours", 24))
        self.keep = int(cfg.get("keep", 7))
        self.root = root
        # Path da archiviare; supporta sia file singoli che dir.
        self.targets: List[str] = list(cfg.get("targets", [
            os.path.join(root, "data", "faces"),
            os.path.join(root, "data", "users.json"),
            os.path.join(root, "data", "guest_pins.json"),
            os.path.join(root, "data", "nfc_tags.json"),
            os.path.join(root, "data", "unknowns"),
            os.path.join(root, "data", "audit.sqlite"),
            os.path.join(root, "data", "audit.sqlite-wal"),
            os.path.join(root, "data", "audit.sqlite-shm"),
            os.path.join(root, "data", "shape_predictor_68_face_landmarks.dat"),
            os.path.join(root, "config", "config.override.yaml"),
        ]))
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.enabled:
            LOG.info("Backup disabilitato")
            return
        try:
            os.makedirs(self.dest_dir, exist_ok=True)
        except Exception as e:
            LOG.warning("backup mkdir err: %s", e)
            return
        if self._th and self._th.is_alive():
            return
        self._th = threading.Thread(target=self._loop, name="backup", daemon=True)
        self._th.start()
        LOG.info("BackupRunner attivo: dest=%s interval=%.1fh keep=%d",
                 self.dest_dir, self.interval_hours, self.keep)

    def restore(self, archive: str, dest_root: Optional[str] = None) -> bool:
        """Estrae uno snapshot in dest_root (default: self.root)."""
        dest = dest_root or self.root
        if not archive or not os.path.isfile(archive):
            LOG.error("restore: archivio assente %s", archive)
            return False
        try:
            os.makedirs(dest, exist_ok=True)
            with tarfile.open(archive, "r:gz") as tf:
                for m in tf.getmembers():
                    name = m.name.replace("\\", "/")
                    if name.startswith("/") or ".." in name.split("/"):
                        LOG.warning("restore skip path non sicuro: %s", m.name)
                        continue
                    tf.extract(m, path=dest)
            LOG.info("Backup ripristinato da %s -> %s", archive, dest)
            return True
        except Exception as e:
            LOG.error("restore fallito: %s", e)
            return False

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> Optional[str]:
        """Crea uno snapshot ora. Ritorna il path se ok, None su errore."""
        ts = time.strftime("%Y%m%d-%H%M%S")
        out_path = os.path.join(self.dest_dir, f"vc-backup-{ts}.tar.gz")
        tmp_path = out_path + ".tmp"
        try:
            with tarfile.open(tmp_path, "w:gz") as tf:
                for tgt in self.targets:
                    if not os.path.exists(tgt):
                        continue
                    try:
                        arc = os.path.relpath(tgt, self.root)
                    except Exception:
                        arc = os.path.basename(tgt)
                    try:
                        tf.add(tgt, arcname=arc, recursive=True)
                    except Exception as e:
                        LOG.warning("backup add %s err: %s", tgt, e)
            os.replace(tmp_path, out_path)
            self._rotate()
            size = os.path.getsize(out_path)
            LOG.info("Backup creato: %s (%d bytes)", out_path, size)
            return out_path
        except Exception as e:
            LOG.error("Backup fallito: %s", e)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return None

    def _rotate(self) -> None:
        try:
            snaps = _list_snapshots(self.dest_dir)
            excess = max(0, len(snaps) - self.keep)
            for old in snaps[:excess]:
                try:
                    os.remove(old)
                    LOG.info("Backup ruotato (rimosso): %s", old)
                except Exception as e:
                    LOG.debug("rm %s err: %s", old, e)
        except Exception as e:
            LOG.debug("rotate err: %s", e)

    def _last_snapshot_age_hours(self) -> float:
        snaps = _list_snapshots(self.dest_dir)
        if not snaps:
            return float("inf")
        try:
            return (time.time() - os.path.getmtime(snaps[-1])) / 3600.0
        except Exception:
            return float("inf")

    def _loop(self) -> None:
        # Snapshot all'avvio se l'ultimo e' vecchio
        if self._last_snapshot_age_hours() >= self.interval_hours:
            self.snapshot()
        # Ciclo: dorme fino al prossimo snapshot
        while not self._stop.is_set():
            sleep_for = max(60.0, self.interval_hours * 3600.0)
            self._stop.wait(sleep_for)
            if self._stop.is_set():
                break
            self.snapshot()
