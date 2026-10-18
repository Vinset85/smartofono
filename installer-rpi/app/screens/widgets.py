"""Widget riutilizzabili: RoundButton, CallButton, PlaceholderScreen base."""
from __future__ import annotations

from kivy.properties import ColorProperty, ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

from modules.touch_controller import SafeTouchMixin
from .bg_screen import BgScreen
from .icons import VectorIcon  # noqa: F401  registrato per uso in KV


class SafeButtonBehavior(SafeTouchMixin, ButtonBehavior):
    """ButtonBehavior con validazione touch anti-ghost/doppio tap."""


class RoundButton(SafeButtonBehavior, Button):
    """Pulsante rounded con touch robusto."""
    bg_color = ColorProperty([0.27, 0.62, 0.96, 1])
    bg_color_pressed = ColorProperty([0.18, 0.45, 0.75, 1])
    radius = ListProperty([16])


class CallButton(SafeButtonBehavior, BoxLayout):
    """Card campanello (dark glass): avatar + nominativo."""
    nominativo = StringProperty("")
    icona = StringProperty("")
    icona_emoji = StringProperty("\U0001F465")
    radius = ListProperty([22])


class IconAccessButton(SafeButtonBehavior, BoxLayout):
    """Pulsante quadrato dark glass con icona vettoriale."""
    label = StringProperty("")
    simbolo = StringProperty("")
    icona = StringProperty("")
    icon_type = StringProperty("")
    radius = ListProperty([20])


class GlassNumButton(SafeButtonBehavior, Button):
    """Tasto numerico PIN: debounce leggero per digitazione veloce."""
    touch_profile = "pin"


class PinActionButton(SafeButtonBehavior, Button):
    """Tasti azione PIN (X, backspace): anti-ghost senza bloccare i numeri."""
    touch_profile = "action"


class PlaceholderScreenBase(BgScreen):
    """Base per schermate placeholder (NFC)."""
    titolo = StringProperty("")
    icona_emoji = StringProperty("")
    icon_type = StringProperty("")
    sottotitolo = StringProperty("")
    nota = StringProperty("")
