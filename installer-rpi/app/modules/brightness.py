"""Controllo luminosità schermo RPi.

Backend supportati (auto-detect, primo che funziona):
  1. sysfs `/sys/class/backlight/<name>/brightness` (DSI ufficiale Raspberry, Waveshare DSI, ecc.)
  2. software dim (overlay nero alpha sopra l'app) - SEMPRE disponibile, attivato esplicitamente
     o come fallback su display HDMI senza backlight hardware
  3. comando `vcgencmd display_power` (solo on/off, fallback minimo)
  4. no-op (logga e basta)

Il software dim è gestito da `set_overlay_setter()` che riceve una callback
chiamata dal main.py per aggiornare l'alpha di un overlay nero fullscreen.

Per scrivere in sysfs senza root, configurare udev:
  /etc/udev/rules.d/99-backlight.rules:
    SUBSYSTEM=="backlight", RUN+="/bin/chgrp video /sys/class/backlight/%k/brightness"
    SUBSYSTEM=="backlight", RUN+="/bin/chmod g+w /sys/class/backlight/%k/brightness"
  e aggiungere l'utente al gruppo `video`.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

LOG = logging.getLogger(__name__)


class BrightnessController:
    """Astrazione controllo luminosità (0-100%)."""

    def __init__(self, idle_pct: int = 20, active_pct: int = 100, prefer_software_dim: bool = False):
        self.idle_pct = max(1, min(100, idle_pct))
        self.active_pct = max(1, min(100, active_pct))
        self._backend: str = "noop"
        self._sysfs_path: Optional[Path] = None
        self._max_brightness: int = 255
        self._current_pct: int = -1
        self._overlay_setter = None  # callback(alpha:float) -> None
        self._prefer_software_dim = prefer_software_dim
        self._output_off = False
        self._wlr_output: Optional[str] = None
        self._init_backend()

    def set_overlay_setter(self, fn) -> None:
        """Registra callback per software dim (alpha 0..1, dove 0 = nessun dim,
        0.7 ≈ schermo molto scuro). Il main.py la collega all'overlay Kivy.
        Se il backend hardware non funziona o è insufficiente (es. solo on/off),
        il software dim diventa il backend principale."""
        self._overlay_setter = fn
        if self._backend in ("vcgencmd", "noop") or self._prefer_software_dim:
            self._backend = "software"
            LOG.info("Brightness backend: software dim (overlay)")

    def _init_backend(self) -> None:
        # 1) sysfs backlight
        bl_root = Path("/sys/class/backlight")
        if bl_root.exists():
            for entry in sorted(bl_root.iterdir()):
                br = entry / "brightness"
                mx = entry / "max_brightness"
                if br.exists() and mx.exists():
                    try:
                        self._max_brightness = int(mx.read_text().strip())
                        self._sysfs_path = br
                        # test scrittura
                        cur = int(br.read_text().strip())
                        br.write_text(str(cur))
                        self._backend = "sysfs"
                        LOG.info("Brightness backend: sysfs %s (max=%d)", br, self._max_brightness)
                        return
                    except PermissionError:
                        LOG.warning(
                            "sysfs %s non scrivibile (manca udev rule o utente in 'video')",
                            br,
                        )
                    except Exception as e:
                        LOG.warning("sysfs %s err: %s", br, e)

        # 2) vcgencmd (solo on/off)
        if self._has_cmd("vcgencmd"):
            self._backend = "vcgencmd"
            LOG.info("Brightness backend: vcgencmd (solo on/off)")
            return

        LOG.warning("Brightness backend: noop (nessun backlight controllabile)")

    @staticmethod
    def _has_cmd(name: str) -> bool:
        return subprocess.run(["which", name], capture_output=True).returncode == 0

    def set_pct(self, pct: int) -> None:
        pct = max(1, min(100, int(pct)))
        if pct == self._current_pct:
            return
        if self._backend == "sysfs" and self._sysfs_path:
            val = max(1, int(self._max_brightness * pct / 100))
            try:
                self._sysfs_path.write_text(str(val))
                self._current_pct = pct
                LOG.debug("Brightness sysfs -> %d%% (%d/%d)", pct, val, self._max_brightness)
            except Exception as e:
                LOG.error("Brightness write err: %s", e)
        elif self._backend == "software" and self._overlay_setter:
            # mappa pct (1..100) -> alpha (0.85..0.0)
            # 100% -> alpha 0  (nessun overlay)
            # 1%   -> alpha 0.85 (schermo molto scuro ma ancora leggibile)
            alpha = max(0.0, min(0.85, (100 - pct) / 100.0 * 0.85))
            try:
                self._overlay_setter(alpha)
                self._current_pct = pct
                LOG.debug("Brightness software -> %d%% (alpha=%.2f)", pct, alpha)
            except Exception as e:
                LOG.error("Brightness overlay err: %s", e)
        elif self._backend == "vcgencmd":
            try:
                state = "1" if pct >= 5 else "0"
                subprocess.run(["vcgencmd", "display_power", state],
                               capture_output=True, check=False)
                self._current_pct = pct
            except Exception as e:
                LOG.error("vcgencmd err: %s", e)
        else:
            self._current_pct = pct  # noop, ricorda solo

    def idle(self) -> None:
        self.set_pct(self.idle_pct)

    def active(self) -> None:
        self.ensure_on()
        self.set_pct(self.active_pct)

    def off(self) -> None:
        """Spegne l'uscita video (OLED: pixel a zero, niente burn-in)."""
        if self._output_off:
            return
        if self._wlr_set(False) or self._vcgencmd_power(False):
            self._output_off = True
            LOG.info("Display spento")
            return
        self.set_pct(1)
        self._output_off = True
        LOG.warning("Display: nessun wlr-randr/vcgencmd, overlay al minimo")

    def ensure_on(self) -> None:
        if not self._output_off:
            return
        self._wlr_set(True)
        self._vcgencmd_power(True)
        self._output_off = False
        self._current_pct = -1
        LOG.info("Display acceso")

    @property
    def is_off(self) -> bool:
        return self._output_off

    def _wlr_output_name(self) -> Optional[str]:
        if self._wlr_output:
            return self._wlr_output
        if not self._has_cmd("wlr-randr"):
            return None
        try:
            r = subprocess.run(
                ["wlr-randr"], capture_output=True, text=True, timeout=3)
            for line in r.stdout.splitlines():
                if line and not line[0].isspace():
                    self._wlr_output = line.split()[0]
                    return self._wlr_output
        except Exception as e:
            LOG.debug("wlr-randr list err: %s", e)
        return None

    def _wlr_set(self, on: bool) -> bool:
        name = self._wlr_output_name()
        if not name:
            return False
        try:
            r = subprocess.run(
                ["wlr-randr", "--output", name, "--on" if on else "--off"],
                capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception as e:
            LOG.debug("wlr-randr %s err: %s", "on" if on else "off", e)
            return False

    def _vcgencmd_power(self, on: bool) -> bool:
        if not self._has_cmd("vcgencmd"):
            return False
        try:
            subprocess.run(
                ["vcgencmd", "display_power", "1" if on else "0"],
                capture_output=True, check=False, timeout=3)
            return True
        except Exception as e:
            LOG.debug("vcgencmd display_power err: %s", e)
            return False

    @property
    def current_pct(self) -> int:
        return self._current_pct

    @property
    def backend(self) -> str:
        return self._backend
