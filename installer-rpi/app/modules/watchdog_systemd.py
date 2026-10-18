"""Watchdog systemd: heartbeat WATCHDOG=1.

Il ping deve partire dal clock Kivy: se l'UI si pianta, systemd riavvia.
Un thread dedicato continuerebbe a pingare anche a schermo morto.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Optional

LOG = logging.getLogger(__name__)


def _send(msg: str) -> bool:
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return False
    try:
        addr = sock_path
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.sendto(msg.encode("utf-8"), addr)
            return True
        finally:
            s.close()
    except Exception as e:
        LOG.debug("sd_notify err: %s", e)
        return False


def notify_ready() -> bool:
    return _send("READY=1")


def notify_status(status: str) -> bool:
    return _send(f"STATUS={status}")


def notify_watchdog() -> bool:
    return _send("WATCHDOG=1")


class WatchdogPinger:
    """Heartbeat dal clock Kivy (main thread)."""

    def __init__(self, interval_sec: float = 10.0) -> None:
        self.interval = max(1.0, float(interval_sec))
        self._ev: Any = None
        self._enabled = bool(os.environ.get("NOTIFY_SOCKET"))
        if not self._enabled:
            LOG.debug("WatchdogPinger disabilitato (NOTIFY_SOCKET assente)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled or self._ev is not None:
            return
        try:
            from kivy.clock import Clock
        except Exception:
            LOG.warning("WatchdogPinger: Kivy Clock assente, nessun ping")
            return
        self._ev = Clock.schedule_interval(self._tick, self.interval)
        notify_watchdog()
        LOG.info("WatchdogPinger avviato sul clock Kivy (interval=%.1fs)",
                 self.interval)

    def stop(self) -> None:
        ev = self._ev
        self._ev = None
        if ev is not None:
            try:
                ev.cancel()
            except Exception:
                pass

    def _tick(self, *_dt) -> None:
        notify_watchdog()


def watchdog_interval_from_env(default: float = 10.0) -> float:
    try:
        usec = int(os.environ.get("WATCHDOG_USEC", "0"))
        if usec > 0:
            return max(1.0, (usec / 1_000_000.0) / 3.0)
    except Exception:
        pass
    return default
