"""Gestione touch robusta per display capacitivo RPi (ghost tap, doppio invio)."""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

LOG = logging.getLogger(__name__)

T = TypeVar("T")

_PROFILES = {
    "default": {
        "min_hold_sec": 0.04,
        "cooldown_sec": 0.45,
        "same_spot_radius_px": 28.0,
        "same_spot_window_sec": 0.55,
    },
    "pin": {
        "min_hold_sec": 0.025,
        "cooldown_sec": 0.07,
        "same_spot_radius_px": 14.0,
        "same_spot_window_sec": 0.10,
    },
    "action": {
        "min_hold_sec": 0.035,
        "cooldown_sec": 0.28,
        "same_spot_radius_px": 22.0,
        "same_spot_window_sec": 0.35,
    },
}


class TouchController:
    """Filtra tap spurii e garantisce una sola azione per pressione valida."""

    MIN_HOLD_SEC = 0.04
    MAX_HOLD_SEC = 3.0
    COOLDOWN_SEC = 0.45
    SAME_SPOT_RADIUS_PX = 28.0
    SAME_SPOT_WINDOW_SEC = 0.55

    def __init__(self, cooldown_sec: float = COOLDOWN_SEC) -> None:
        self.cooldown_sec = float(cooldown_sec)
        self._press: dict[int, dict] = {}
        self._lock_until: dict[str, float] = {}
        self._widget_last: dict[str, float] = {}
        self._last_spot: tuple[float, float, float, str] | None = None
        self._global_busy_until = 0.0

    def _now(self) -> float:
        return time.monotonic()

    def _profile(self, name: str) -> dict:
        return _PROFILES.get(name, _PROFILES["default"])

    def _locked(self, key: str) -> bool:
        return self._now() < self._lock_until.get(key, 0.0)

    def lock(self, key: str, sec: float | None = None) -> None:
        dur = self.cooldown_sec if sec is None else float(sec)
        until = self._now() + dur
        self._lock_until[key] = until
        self._global_busy_until = max(
            self._global_busy_until, self._now() + dur * 0.55)

    def unlock(self, key: str | None = None) -> None:
        if key is None:
            self._lock_until.clear()
            self._global_busy_until = 0.0
        else:
            self._lock_until.pop(key, None)

    def try_action(self, key: str, sec: float | None = None) -> bool:
        """True se l'azione puo' procedere; imposta lock anti-ripetizione."""
        now = self._now()
        if now < self._global_busy_until:
            LOG.debug("touch global busy")
            return False
        if self._locked(key):
            LOG.debug("touch lock attivo: %s", key)
            return False
        self.lock(key, sec)
        return True

    def accept_press(self, touch, widget_id: str,
                     profile: str = "default") -> bool:
        """Registra touch_down valido sul widget."""
        prof = self._profile(profile)
        now = self._now()
        if now < self._global_busy_until:
            return False
        if self._press and touch.id not in self._press:
            return False
        if self._last_spot is not None:
            lx, ly, lt, lprof = self._last_spot
            win = prof["same_spot_window_sec"]
            if profile == lprof and now - lt < win:
                dx, dy = touch.x - lx, touch.y - ly
                r = prof["same_spot_radius_px"]
                if dx * dx + dy * dy < r * r:
                    LOG.debug("touch stesso punto ignorato (%s)", widget_id)
                    return False
        self._press[touch.id] = {
            "t": now,
            "widget": widget_id,
            "x": touch.x,
            "y": touch.y,
            "profile": profile,
        }
        return True

    def cancel_press(self, touch_id: int) -> None:
        self._press.pop(touch_id, None)

    def validate_release(self, touch, widget_id: str,
                         profile: str = "default") -> bool:
        """True se touch_up completa una pressione valida (poi cooldown widget)."""
        info = self._press.pop(touch.id, None)
        if info is None:
            return False
        if info["widget"] != widget_id:
            return False
        prof = self._profile(info.get("profile", profile))
        now = self._now()
        hold = now - info["t"]
        if hold < prof["min_hold_sec"]:
            LOG.debug("touch troppo breve %.0fms (%s)", hold * 1000, widget_id)
            return False
        if hold > self.MAX_HOLD_SEC:
            LOG.debug("touch troppo lungo (%.1fs) %s", hold, widget_id)
            return False
        last = self._widget_last.get(widget_id, 0.0)
        cd = prof["cooldown_sec"]
        if now - last < cd:
            LOG.debug("cooldown widget %s", widget_id)
            return False
        self._widget_last[widget_id] = now
        self._last_spot = (info["x"], info["y"], now, info.get("profile", profile))
        return True


def widget_touch_id(widget) -> str:
    return f"{widget.__class__.__name__}#{id(widget)}"


class SafeTouchMixin:
    """Mixin Kivy: grab + validazione press/release via TouchController."""

    touch_profile = "default"

    def _touch_controller(self) -> TouchController | None:
        try:
            from kivy.app import App
            app = App.get_running_app()
            ctx = getattr(app, "ctx", None)
            return getattr(ctx, "touch", None) if ctx else None
        except Exception:
            return None

    def _touch_widget_id(self) -> str:
        return widget_touch_id(self)

    def _touch_profile(self) -> str:
        return str(getattr(self, "touch_profile", "default"))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if getattr(self, "disabled", False):
            return super().on_touch_down(touch)
        tc = self._touch_controller()
        prof = self._touch_profile()
        if tc is not None and not tc.accept_press(touch, self._touch_widget_id(), prof):
            return True
        touch.grab(self)
        self.state = "down"
        self.dispatch("on_press")
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        self.state = "normal"
        tc = self._touch_controller()
        wid = self._touch_widget_id()
        prof = self._touch_profile()
        if tc is None or tc.validate_release(touch, wid, prof):
            self.dispatch("on_release")
        elif tc is not None:
            tc.cancel_press(touch.id)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        inside = self.collide_point(*touch.pos)
        self.state = "down" if inside else "normal"
        return True
