"""Impulso GPIO verso il relè di apertura (indipendente da Home Assistant).

Pi 5, BCM GPIO12 = pin fisico 32 (porta), GPIO13 = pin 33 (cancello).
Il GPIO è 3,3 V: in quadro un relè/optoisolatore, non la serratura diretta.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)

_CHIP_CANDIDATES = (4, 0)  # Pi 5 RP1 = gpiochip4, fallback gpiochip0


class DoorRelay:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.porta_gpio = int(cfg.get("porta_gpio", 12))
        canc = cfg.get("cancello_gpio", 13)
        self.cancello_gpio = int(canc) if canc not in (None, "", False) else self.porta_gpio
        self.pulse_s = max(0.1, float(cfg.get("pulse_ms", 1000)) / 1000.0)
        self.active_high = bool(cfg.get("active_high", True))
        self._lgpio = None
        self._handle = None
        self._lock = threading.Lock()
        self._last_error = ""
        self._backend = "none"
        if self.enabled:
            self._init_backend()

    def last_error(self) -> str:
        return self._last_error

    def backend(self) -> str:
        return self._backend

    def gpio_for(self, scope: str) -> int:
        return self.cancello_gpio if scope == "cancello" else self.porta_gpio

    def pulse(self, scope: str = "porta") -> bool:
        """Alza il GPIO per pulse_ms, poi lo riabbassa. Non blocca il caller."""
        if not self.enabled:
            self._last_error = "disabilitato"
            return False
        gpio = self.gpio_for(scope)
        if gpio < 0:
            self._last_error = "gpio non configurato"
            return False
        try:
            self._claim_output(gpio)
            on = 1 if self.active_high else 0
            off = 0 if self.active_high else 1
            self._write(gpio, on)
        except Exception as e:
            self._last_error = str(e)
            LOG.error("relay pulse start gpio=%s: %s", gpio, e)
            return False

        def _hold() -> None:
            try:
                time.sleep(self.pulse_s)
                self._write(gpio, off)
            except Exception as e:
                LOG.warning("relay pulse end gpio=%s: %s", gpio, e)

        threading.Thread(target=_hold, daemon=True, name="door-relay").start()
        LOG.info("relay pulse gpio=%s scope=%s backend=%s dur=%.2fs",
                 gpio, scope, self._backend, self.pulse_s)
        return True

    def close(self) -> None:
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
                    self._lgpio = lgpio
                    self._handle = h
                    self._backend = f"lgpio:{chip}"
                    LOG.info("DoorRelay backend %s", self._backend)
                    return
                except Exception:
                    continue
        except Exception:
            pass
        if shutil.which("pinctrl"):
            self._backend = "pinctrl"
            LOG.info("DoorRelay backend pinctrl")
            return
        self._backend = "none"
        self._last_error = "nessun backend GPIO (lgpio/pinctrl)"
        LOG.warning("DoorRelay: %s", self._last_error)

    def _claim_output(self, gpio: int) -> None:
        if self._lgpio is not None and self._handle is not None:
            try:
                self._lgpio.gpio_claim_output(self._handle, gpio)
            except Exception:
                pass
            return
        if self._backend == "pinctrl":
            off = "dl" if self.active_high else "dh"
            subprocess.run(
                ["pinctrl", "set", str(gpio), "op", off],
                check=True, capture_output=True, text=True, timeout=2,
            )

    def _write(self, gpio: int, level: int) -> None:
        with self._lock:
            if self._lgpio is not None and self._handle is not None:
                self._lgpio.gpio_write(self._handle, gpio, 1 if level else 0)
                return
            if self._backend == "pinctrl":
                arg = "dh" if level else "dl"
                subprocess.run(
                    ["pinctrl", "set", str(gpio), arg],
                    check=True, capture_output=True, text=True, timeout=2,
                )
                return
            raise RuntimeError(self._last_error or "GPIO non disponibile")
