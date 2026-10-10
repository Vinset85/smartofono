"""Watchdog systemd: invia heartbeat WATCHDOG=1 al manager systemd.

Funziona solo se nel unit file e' presente:
    Type=notify       (o Type=simple con NotifyAccess=all)
    WatchdogSec=30
    NotifyAccess=main

Sul Pi usiamo Type=notify, NotifyAccess=main, WatchdogSec=30. Se il main
loop di Kivy si pianta o l'interprete blocca per >30s, systemd riavvia il
servizio.

Il modulo non dipende da `python-systemd`/`pystemd` (spesso assenti su
Raspberry OS): comunica con $NOTIFY_SOCKET via UDP unix datagram.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Optional

LOG = logging.getLogger(__name__)


def _send(msg: str) -> bool:
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return False
    try:
        addr = sock_path
        if addr.startswith("@"):  # abstract namespace
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
    """Invia READY=1 (chiamato a fine inizializzazione)."""
    return _send("READY=1")


def notify_status(status: str) -> bool:
    """STATUS=<line> (mostrato in `systemctl status`)."""
    return _send(f"STATUS={status}")


def notify_watchdog() -> bool:
    """Singolo ping di heartbeat."""
    return _send("WATCHDOG=1")


class WatchdogPinger:
    """Thread daemon che invia WATCHDOG=1 ogni `interval_sec`.

    Se NOTIFY_SOCKET non e' impostato (es. esecuzione manuale fuori da
    systemd), il thread non parte e tutti i metodi sono no-op.
    """

    def __init__(self, interval_sec: float = 10.0) -> None:
        self.interval = max(1.0, float(interval_sec))
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self._enabled = bool(os.environ.get("NOTIFY_SOCKET"))
        if not self._enabled:
            LOG.debug("WatchdogPinger disabilitato (NOTIFY_SOCKET assente)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled or self._th and self._th.is_alive():
            return
        self._th = threading.Thread(
            target=self._loop, name="sd-watchdog", daemon=True)
        self._th.start()
        LOG.info("WatchdogPinger avviato (interval=%.1fs)", self.interval)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            notify_watchdog()
            self._stop.wait(self.interval)


def watchdog_interval_from_env(default: float = 10.0) -> float:
    """Calcola un intervallo ragionevole partendo da WATCHDOG_USEC.

    systemd esporta WATCHDOG_USEC quando il unit ha WatchdogSec=N.
    Il pinger deve battere a < N/2 per non triggerare il timeout.
    """
    try:
        usec = int(os.environ.get("WATCHDOG_USEC", "0"))
        if usec > 0:
            return max(1.0, (usec / 1_000_000.0) / 3.0)
    except Exception:
        pass
    return default
