"""Reed antimanomissione su GPIO (default BCM 27, pin fisico 13).

Contatto NC verso massa: GPIO basso = cassa chiusa, alto = aperta/tagliata.
Disabilitato di default finché il reed non è montato (GPIO floating = falsi
allarmi).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

LOG = logging.getLogger(__name__)

_CHIP_CANDIDATES = (4, 0)


class ReedSwitch:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None,
                 on_change: Optional[Callable[[str], None]] = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.gpio = int(cfg.get("gpio", 27))
        self.nc = bool(cfg.get("nc", True))
        self._on_change = on_change
        self._lgpio = None
        self._handle = None
        self._backend = "none"
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self._state = "off"
        self._last_error = ""
        if self.enabled:
            self._init_backend()
            if self._backend != "none":
                self._th = threading.Thread(
                    target=self._loop, name="reed", daemon=True)
                self._th.start()

    def status(self) -> str:
        return self._state

    def last_error(self) -> str:
        return self._last_error

    def stop(self) -> None:
        self._stop.set()
        if self._lgpio is not None and self._handle is not None:
            try:
                self._lgpio.gpiochip_close(self._handle)
            except Exception:
                pass
            self._handle = None

    def _init_backend(self) -> None:
        try:
            import lgpio  # type: ignore
            for chip in _CHIP_CANDIDATES:
                try:
                    h = lgpio.gpiochip_open(chip)
                    try:
                        lgpio.gpio_claim_input(h, self.gpio, lgpio.SET_PULL_UP)
                    except Exception:
                        lgpio.gpio_claim_input(h, self.gpio)
                    self._lgpio = lgpio
                    self._handle = h
                    self._backend = f"lgpio:{chip}"
                    LOG.info("Reed GPIO%s backend %s", self.gpio, self._backend)
                    return
                except Exception:
                    continue
        except Exception:
            pass
        if shutil.which("pinctrl"):
            try:
                subprocess.run(
                    ["pinctrl", "set", str(self.gpio), "ip", "pu"],
                    check=True, capture_output=True, text=True, timeout=2,
                )
                self._backend = "pinctrl"
                LOG.info("Reed GPIO%s backend pinctrl", self.gpio)
                return
            except Exception as e:
                self._last_error = str(e)
        self._backend = "none"
        self._last_error = "nessun backend GPIO"
        LOG.warning("Reed: %s", self._last_error)

    def _read_high(self) -> Optional[bool]:
        try:
            if self._lgpio is not None and self._handle is not None:
                return bool(self._lgpio.gpio_read(self._handle, self.gpio))
            if self._backend == "pinctrl":
                r = subprocess.run(
                    ["pinctrl", "get", str(self.gpio)],
                    check=True, capture_output=True, text=True, timeout=2,
                )
                txt = (r.stdout or "").lower()
                if "hi" in txt:
                    return True
                if "lo" in txt:
                    return False
        except Exception as e:
            self._last_error = str(e)
        return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            high = self._read_high()
            if high is None:
                nxt = "unknown"
            elif self.nc:
                nxt = "open" if high else "ok"
            else:
                nxt = "ok" if high else "open"
            if nxt != self._state:
                prev = self._state
                self._state = nxt
                LOG.warning("Reed %s -> %s (gpio=%s)", prev, nxt, self.gpio)
                if self._on_change:
                    try:
                        self._on_change(nxt)
                    except Exception as e:
                        LOG.debug("reed cb err: %s", e)
            self._stop.wait(0.4)
