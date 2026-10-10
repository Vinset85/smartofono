"""Schermata lettura tag NFC (stile coerente con PIN / Volto)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty

from modules.greetings import build_greeting
from modules.access_icons import resolve_access_icon
from .bg_screen import BgScreen

LOG = logging.getLogger(__name__)

_UNKNOWN_BACK_SEC = 7.0
# Max lato icona in dp (da PNG 500px: downscale, mai upscale).
_MAX_ICON_DP = 400


def _resolve_access_icon(app_ctx, icon_key: str, default_type: str) -> tuple[str, str]:
    return resolve_access_icon(app_ctx, icon_key, default_type)


class NfcScreen(BgScreen):
    """Lettura tag NFC con feedback esplicito (ok / tag sconosciuto)."""

    icona = StringProperty("")
    icon_type = StringProperty("nfc")
    # Dimensioni native PNG in pixel (nessun upscale).
    icon_px_w = NumericProperty(0)
    icon_px_h = NumericProperty(0)
    stato = StringProperty("In attesa del tag…")
    messaggio = StringProperty("Avvicina il badge al lettore")
    dettaglio = StringProperty("")
    errore = BooleanProperty(False)
    scanning = BooleanProperty(True)

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._auto_back = None
        self._busy = False

    def refresh_icon(self) -> None:
        """Aggiorna icona da config (es. dopo access_icons live) senza toccare il lettore."""
        icona, itype = _resolve_access_icon(self.app_ctx, "nfc", "nfc")
        self.icona = icona
        self.icon_type = itype
        self.icon_px_w = 0
        self.icon_px_h = 0
        if icona and not itype:
            try:
                from kivy.core.image import Image as Ki
                tex = Ki(icona).texture
                if tex:
                    tw, th = float(tex.width), float(tex.height)
                    max_side = dp(_MAX_ICON_DP)
                    scale = min(1.0, max_side / max(tw, th, 1.0))
                    self.icon_px_w = tw * scale
                    self.icon_px_h = th * scale
            except Exception as e:
                LOG.debug("NFC icon size err: %s", e)
        if not self.icon_px_w and self.icon_type:
            side = dp(_MAX_ICON_DP)
            self.icon_px_w = side
            self.icon_px_h = side

    def on_pre_enter(self, *_):
        self._busy = False
        try:
            self.refresh_icon()
            self._set_listening()
        except Exception as e:
            LOG.error("NFC on_pre_enter err: %s", e)
            side = dp(_MAX_ICON_DP)
            self.icon_type = "nfc"
            self.icona = ""
            self.icon_px_w = side
            self.icon_px_h = side
            self._set_listening()
        self._cancel_auto_back()

    def on_leave(self, *_):
        self._cancel_auto_back()

    def _cancel_auto_back(self) -> None:
        if self._auto_back is not None:
            self._auto_back.cancel()
            self._auto_back = None

    def _set_listening(self) -> None:
        self.errore = False
        self.scanning = True
        self.dettaglio = ""
        reader = self.app_ctx.nfc_reader
        if reader is not None and not reader.is_reader_ready():
            err = reader.last_error() or "avvio lettore"
            self.stato = "Lettore in avvio…"
            self.messaggio = "Attendi qualche secondo"
            self.dettaglio = err[:80] if err else ""
        else:
            self.stato = "In attesa del tag…"
            self.messaggio = "Avvicina il badge al lettore"

    def on_nfc_tag(self, uid: str) -> None:
        if self._busy:
            return
        self._busy = True
        self.scanning = False
        lib = self.app_ctx.nfc_lib
        rec = lib.find_by_uid(uid) if lib else None
        if not rec:
            LOG.warning("NFC schermata: tag %s non in libreria", uid)
            self.show_unknown_tag(uid)
            return
        nome = rec.get("nome", "")
        scope = rec.get("scope", "porta")
        self._open_for_user(nome, scope, rec)

    def show_unknown_tag(self, uid: str) -> None:
        """Tag letto ma non presente in libreria."""
        self._busy = True
        self.scanning = False
        uid_s = (uid or "").strip().lower()
        self.dettaglio = f"UID {uid_s}" if uid_s else "Nessun utente associato"
        try:
            self.app_ctx.sound.play("error")
        except Exception:
            pass
        try:
            self.app_ctx.record_open(
                method="nfc", user="", scope="porta", success=False,
                label=uid_s,
            )
        except Exception:
            pass
        self._cancel_auto_back()
        Clock.schedule_once(lambda *_: self._go_result_unknown(uid_s), 0)

    def _go_result_unknown(self, uid_s: str) -> None:
        try:
            result = self.manager.get_screen("result")
            result.mostra_risultato(
                success=False,
                titolo="Tag NFC non riconosciuto",
                dettaglio=self.dettaglio or "Avvicina un badge registrato",
                image_source="assets/icons8-high-risk-500.png",
                image_scale=0.50,
            )
            self.manager.current = "result"
        except Exception as e:
            LOG.warning("nfc unknown result err: %s", e)
            self._auto_back = Clock.schedule_once(
                lambda *_: self.go_home(), _UNKNOWN_BACK_SEC)

    def _open_for_user(self, nome: str, scope: str, rec: dict) -> None:
        self.errore = False
        self.stato = "Tag riconosciuto"
        self.messaggio = f"Benvenuto {nome.replace('_', ' ')}"
        self.dettaglio = "Apertura in corso…"
        ctx = self.app_ctx
        rest_ok = False
        try:
            rest_ok = (
                ctx.ha.apri_porta() if scope == "porta"
                else ctx.ha.apri_cancello()
            )
        except Exception as e:
            LOG.warning("nfc REST err: %s", e)
        try:
            ctx.mqtt.publish_apertura(metodo="nfc", utente=nome, scope=scope)
        except Exception:
            pass
        try:
            ctx.record_open(
                method="nfc", user=nome, scope=scope, success=True,
                label=rec.get("label", ""),
            )
        except Exception:
            pass
        # Saluto con nome utente (nome), non etichetta tag (label es. "cerchio blu").
        nome_h = nome.replace("_", " ")
        genere = (rec.get("genere") or "").upper()
        saluto = build_greeting(nome_h, genere) if nome_h else ""
        try:
            result = self.manager.get_screen("result")
            titolo = "Porta aperta" if scope == "porta" else "Cancello aperto"
            image = "assets/door_open.png" if scope == "porta" else ""
            result.mostra_risultato(
                success=True,
                titolo=titolo,
                dettaglio=saluto,
                image_source=image,
            )
            Clock.schedule_once(
                lambda *_: setattr(self.manager, "current", "result"), 0.25)
        except Exception as e:
            LOG.warning("nfc success result err: %s", e)
        try:
            if saluto and getattr(ctx, "tts", None):
                ctx.sound.play(
                    "success",
                    on_end=lambda t=saluto: ctx.tts.speak(t),
                    on_end_gap=0.25,
                )
            else:
                ctx.sound.play("success")
        except Exception:
            pass
        LOG.info("NFC UI ok scope=%s rest_ok=%s utente=%s", scope, rest_ok, nome)

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self._busy = False
        self.manager.current = "home"

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)
