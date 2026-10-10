"""Lettore impronte digitali — stub finche' non e' collegato hardware R503/ZFM."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

LOG = logging.getLogger(__name__)


class FingerprintReader:
    """API minima allineata a NfcReader (start/stop/enroll)."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.device = str(cfg.get("device", "/dev/ttyAMA0"))
        self._last_error = "hardware non collegato"

    def is_available(self) -> bool:
        return False

    def is_reader_ready(self) -> bool:
        return False

    def last_error(self) -> str:
        return self._last_error

    def start(self) -> bool:
        if not self.enabled:
            LOG.info("FingerprintReader disabilitato in config")
            return False
        LOG.warning("FingerprintReader: modulo hardware non installato (%s)", self.device)
        return False

    def stop(self) -> None:
        pass

    def enroll_next(self, timeout_sec: float = 30.0) -> Optional[int]:
        self._last_error = "enroll non disponibile: hardware assente"
        return None
