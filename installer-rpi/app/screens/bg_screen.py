"""Mixin Screen con sfondo dinamico (`bg_source`) condiviso tra tutte
le schermate (Home, Calling, Pin, Face, Nfc, Result, ...).

Uso:
    class HomeScreen(BgScreen):
        ...
        # KV usa root.bg_source come sorgente del Rectangle del canvas.before

Quando `bg_source` cambia:
- invalida la cache Kivy (`kv.image`/`kv.texture`) per il path corrente
- richiede un redraw del canvas (utile quando il path coincide ma il file
  e' stato sostituito).
"""
from __future__ import annotations

from kivy.properties import StringProperty
from kivy.uix.screenmanager import Screen


class BgScreen(Screen):
    bg_source = StringProperty("")

    def __init__(self, *a, bg_source: str | None = None, **kw):
        super().__init__(*a, **kw)
        if bg_source:
            self.bg_source = bg_source

    def on_bg_source(self, *_):
        try:
            from kivy.cache import Cache
            if self.bg_source:
                for cat in ("kv.image", "kv.texture"):
                    try:
                        Cache.remove(cat, self.bg_source)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self.canvas.ask_update()
        except Exception:
            pass
