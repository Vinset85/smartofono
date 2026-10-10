"""Schermate placeholder per Fingerprint e NFC (UI completa, hardware non ancora installato)."""
from __future__ import annotations

from kivy.clock import Clock
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.screenmanager import Screen

from .bg_screen import BgScreen
from .widgets import PlaceholderScreenBase


class PlaceholderScreen(PlaceholderScreenBase):
    AUTO_BACK_SEC = 6

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._auto_back = None

    def on_enter(self, *_):
        self._auto_back = Clock.schedule_once(lambda *_: self.go_home(), self.AUTO_BACK_SEC)

    def on_leave(self, *_):
        if self._auto_back:
            self._auto_back.cancel()
            self._auto_back = None

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self.app_ctx.go_screen("home", instant=True)

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)


class FingerScreen(PlaceholderScreen):
    pass


class ResultScreen(BgScreen):
    success = BooleanProperty(False)
    titolo = StringProperty("")
    dettaglio = StringProperty("")
    icona_emoji = StringProperty("\u2713")
    # Path opzionale di un'immagine da mostrare al posto dell'emoji
    # (es. "assets/door_open.png" per la conferma di "Porta aperta").
    image_source = StringProperty("")
    # Frazione del contenitore (0..1) per l'immagine risultato.
    image_scale = NumericProperty(0.65)

    AUTO_BACK_SEC = 4

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._auto_back = None

    def mostra_risultato(
        self,
        success: bool,
        titolo: str,
        dettaglio: str = "",
        image_source: str = "",
        image_scale: float = 0.65,
    ) -> None:
        self.success = success
        self.titolo = titolo
        self.dettaglio = dettaglio
        self.icona_emoji = "\u2713" if success else "\u2715"
        self.image_source = image_source or ""
        self.image_scale = float(image_scale)

    def on_enter(self, *_):
        self._auto_back = Clock.schedule_once(lambda *_: self.go_home(), self.AUTO_BACK_SEC)

    def on_leave(self, *_):
        if self._auto_back:
            self._auto_back.cancel()
            self._auto_back = None

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self.app_ctx.go_screen("home", instant=True)

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)


_ITA_GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
_ITA_MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# Il pannello e' OLED: i pixel accesi invecchiano, quelli neri no. Lo
# screensaver e' lo stato in cui il videocitofono passa quasi tutta la sua
# vita, e ci tiene dentro l'indirizzo in 96sp sempre nello stesso posto, che
# e' la ricetta del burn-in. Spostare il blocco di pochi dp lungo un giro
# chiuso distribuisce l'usura sui bordi dei glifi: nove posizioni ogni tre
# minuti fanno un giro ogni mezz'ora, e l'occhio non vede 8 dp che si muovono
# una volta ogni tanto.
_SHIFT_GIRO = ((0, 0), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
_SHIFT_AMPIEZZA_DP = 8
_SHIFT_PERIODO_SEC = 180


class ScreensaverScreen(Screen):
    ora_corrente = StringProperty("--:--")
    data_corrente = StringProperty("")
    indirizzo = StringProperty("Via Roma 1")
    bg_source = StringProperty("")
    shift_x = NumericProperty(0)
    shift_y = NumericProperty(0)

    def __init__(self, app_ctx, indirizzo: str | None = None, bg_source: str | None = None, **kw):
        super().__init__(**kw)
        self.app_ctx = app_ctx
        if indirizzo:
            self.indirizzo = indirizzo
        if bg_source:
            self.bg_source = bg_source
        self._tick_ev = None
        self._shift_ev = None
        self._shift_i = 0

    def on_bg_source(self, *_):
        """Aggiorna esplicitamente l'Image: il binding KV puo' non scattare
        in tempo, e Kivy cacha le texture per source path. Settiamo il
        source manualmente, invalidando la cache prima del reload."""
        from kivy.clock import Clock
        Clock.schedule_once(self._apply_bg_to_image, 0)

    def _apply_bg_to_image(self, *_):
        import os as _os
        from kivy.logger import Logger as _Log
        bs = self.bg_source or ""
        img = self.ids.get("bg_image") if hasattr(self, "ids") else None
        if img is None:
            _Log.warning("VC_SFONDO: bg_image id non trovato (ids=%s)",
                         list(self.ids.keys()) if hasattr(self, "ids") else None)
            return
        try:
            from kivy.cache import Cache
            if bs:
                for cat in ("kv.image", "kv.texture"):
                    try:
                        Cache.remove(cat, bs)
                    except Exception:
                        pass
        except Exception:
            pass
        img.source = ""
        if bs and _os.path.exists(bs):
            img.source = bs
            try:
                img.reload()
            except Exception:
                pass
            img.opacity = 1
            _Log.info("VC_SFONDO: applied source=%r", img.source)
        else:
            img.opacity = 0
            _Log.info("VC_SFONDO: cleared (path=%r exists=%s)",
                      bs, _os.path.exists(bs) if bs else False)

    def on_enter(self, *_):
        self._tick()
        self._tick_ev = Clock.schedule_interval(lambda *_: self._tick(), 1)
        # Il giro riparte da dove era rimasto: cosi' rientri ripetuti nello
        # screensaver non riportano sempre il testo nella stessa posizione.
        self._sposta()
        self._shift_ev = Clock.schedule_interval(
            lambda *_: self._sposta(), _SHIFT_PERIODO_SEC)

    def on_leave(self, *_):
        if self._tick_ev:
            self._tick_ev.cancel()
            self._tick_ev = None
        if self._shift_ev:
            self._shift_ev.cancel()
            self._shift_ev = None

    def _sposta(self) -> None:
        from kivy.metrics import dp
        dx, dy = _SHIFT_GIRO[self._shift_i]
        self._shift_i = (self._shift_i + 1) % len(_SHIFT_GIRO)
        self.shift_x = dx * dp(_SHIFT_AMPIEZZA_DP)
        self.shift_y = dy * dp(_SHIFT_AMPIEZZA_DP)

    def _tick(self) -> None:
        import datetime
        now = datetime.datetime.now()
        self.ora_corrente = now.strftime("%H:%M")
        # Locale-indipendente: forziamo italiano (il locale di sistema
        # potrebbe non essere it_IT.UTF-8 sul RPi OS base).
        giorno = _ITA_GIORNI[now.weekday()]
        mese = _ITA_MESI[now.month - 1]
        self.data_corrente = f"{giorno} {now.day} {mese} {now.year}"

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self.app_ctx.go_screen("home", instant=True)

    def on_touch_down(self, touch):
        self.go_home()
        return True
