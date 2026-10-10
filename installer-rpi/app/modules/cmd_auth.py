"""Autenticazione e rate-limit comandi MQTT videocitofono/cmd."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Set

LOG = logging.getLogger(__name__)

_DANGEROUS: Set[str] = {
    "restart_app", "reboot", "set_admin_pin", "install_deps",
}


class CmdAuthGuard:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg or {}
        self.secret = str(cfg.get("cmd_secret") or "").strip()
        self.rate_limit_sec = float(cfg.get("cmd_rate_limit_sec", 30.0))
        self._last_dangerous_ts = -self.rate_limit_sec

    @property
    def enabled(self) -> bool:
        return bool(self.secret)

    def verify(self, payload: dict) -> bool:
        """True se il comando puo' procedere."""
        if not isinstance(payload, dict):
            return False
        if not self.enabled:
            return True
        token = str(payload.get("token") or payload.get("cmd_token") or "")
        if token != self.secret:
            LOG.warning("MQTT cmd rifiutato: token mancante o non valido")
            return False
        return True

    def allow_dangerous(self, action: str) -> bool:
        if action not in _DANGEROUS:
            return True
        now = time.monotonic()
        if now - self._last_dangerous_ts < self.rate_limit_sec:
            LOG.warning("MQTT cmd %s rate-limited (%.0fs)", action, self.rate_limit_sec)
            return False
        self._last_dangerous_ts = now
        return True
