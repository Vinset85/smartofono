"""Schermata PIN: tastierino numerico iOS-style con verifica continua e apertura automatica della porta al primo match valido."""
from __future__ import annotations

import logging

from kivy.clock import Clock
from kivy.properties import BooleanProperty, StringProperty

from .bg_screen import BgScreen
from modules.greetings import build_greeting

LOG = logging.getLogger(__name__)


class PinScreen(BgScreen):
    pin_display = StringProperty("")
    messaggio = StringProperty("")
    errore = BooleanProperty(False)

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._pin = ""
        # Flag per impedire ulteriori inserimenti durante la transizione
        # post-success (~200ms a "result"): senza questo, un secondo tap
        # rapido potrebbe aprire una seconda volta o triggerare errori.
        self._submitting = False

    def on_pre_enter(self, *_):
        self._pin = ""
        self._submitting = False
        self._refresh()
        self.errore = False
        if self.app_ctx.pin_manager.in_lockout:
            self.errore = True
            self.messaggio = f"Bloccato per {self.app_ctx.pin_manager.lockout_remaining}s"
        else:
            self.messaggio = ""

    def _refresh(self) -> None:
        # Pallini pieni (stile iOS lock-screen): 1 cerchio per ogni cifra
        # digitata, niente placeholder vuoti. Usiamo BLACK CIRCLE U+25CF
        # (universalmente supportato da Roboto/DejaVu) invece di HEAVY
        # ASTERISK U+2731 che spesso manca nei font Linux di sistema.
        # Non-breaking space quando vuoto per preservare l'altezza riga.
        n = len(self._pin)
        self.pin_display = ("\u25CF  " * n).rstrip() if n else "\u00A0"

    def add_digit(self, d: str) -> None:
        if self._submitting:
            return
        self.app_ctx.activity_touch()
        max_len = int(self.app_ctx.config["pin"].get("lunghezza_max", 8))
        min_len = int(self.app_ctx.config["pin"].get("lunghezza_min", 4))
        if len(self._pin) >= max_len:
            return
        self._pin += d
        self._refresh()
        try:
            self.app_ctx.sound.play("key")
        except Exception:
            pass
        self.errore = False
        self.messaggio = ""
        # Auto-verifica appena raggiunta la lunghezza minima.
        # Se non c'e' match si continua a digitare (PIN piu' lungo); al
        # raggiungimento della lunghezza max si dichiara fallimento.
        if len(self._pin) < min_len:
            return
        try:
            utente = self.app_ctx.pin_manager.try_match(self._pin)
        except PermissionError as e:
            self.errore = True
            self.messaggio = str(e)
            self._pin = ""
            self._refresh()
            try:
                self.app_ctx.sound.play("error")
            except Exception:
                pass
            return
        if utente is not None:
            self._submitting = True
            self.errore = False
            self.messaggio = f"Benvenuto {utente['nome']}"
            self._apri(utente)
            return
        # Tentativo PIN ospite (scadenza/max_uses gestiti internamente)
        try:
            gp = getattr(self.app_ctx, "guest_pins", None)
            if gp is not None:
                guest = gp.try_match(self._pin)
                if guest is not None:
                    self._submitting = True
                    self.errore = False
                    label = guest.get("label") or "Ospite"
                    self.messaggio = f"Benvenuto {label}"
                    self._apri({
                        "nome": "ospite",
                        "label": label,
                        "apre": guest.get("scope", "porta"),
                        "genere": "",
                        "_guest_id": guest.get("id"),
                    })
                    return
        except Exception as e:
            LOG.debug("guest pin check err: %s", e)
        if len(self._pin) >= max_len:
            # Lunghezza max raggiunta senza match: fallimento, reset.
            self.app_ctx.pin_manager.register_failure()
            self.errore = True
            self.messaggio = "PIN errato"
            self._pin = ""
            try:
                self.app_ctx.sound.play("error")
            except Exception:
                pass
            try:
                self.app_ctx.record_event("pin_fail", method="pin",
                                          success=False)
            except Exception:
                pass
            Clock.schedule_once(lambda *_: self._refresh(), 0.4)

    def backspace(self) -> None:
        if self._submitting:
            return
        self.app_ctx.activity_touch()
        self._pin = self._pin[:-1]
        self._refresh()
        self.errore = False
        if not self.messaggio.startswith("Bloccato"):
            self.messaggio = ""

    def _apri(self, utente: dict) -> None:
        scope = utente.get("apre", "porta")
        # Triggeriamo l'apertura via DUE canali (ridondanza):
        #  1) REST diretto a HA (richiede long-lived token in config)
        #  2) MQTT publish su videocitofono/apertura, ascoltato da
        #     un'automazione HA che esegue lo stesso script.
        # Il successo finale e' garantito dal canale MQTT (sempre attivo)
        # quindi il feedback all'utente non dipende dal codice di ritorno
        # REST: se il PIN e' valido la conferma "Porta aperta" e' mostrata
        # comunque. Eventuali fallimenti del canale REST sono solo loggati.
        rest_ok = False
        try:
            rest_ok = (
                self.app_ctx.ha.apri_porta() if scope == "porta"
                else self.app_ctx.ha.apri_cancello()
            )
        except Exception as e:
            LOG.warning("apri (REST) failed: %s", e)
        is_guest = bool(utente.get("_guest_id"))
        method = "guest" if is_guest else "pin"
        utente_audit = utente.get("nome") or ""
        self.app_ctx.mqtt.publish_apertura(metodo=method, utente=utente_audit, scope=scope)
        LOG.info("apri scope=%s method=%s rest_ok=%s mqtt=published",
                 scope, method, rest_ok)
        try:
            self.app_ctx.record_open(
                method=method, user=utente_audit, scope=scope, success=True,
                guest_id=utente.get("_guest_id"),
                label=utente.get("label", ""),
            )
        except Exception:
            pass
        # Auto-enroll incrementale: salva un sample del volto nella libreria
        # dell'utente che ha appena aperto col PIN. Skippa se ospite.
        if not is_guest:
            try:
                self._maybe_auto_enroll(utente_audit)
            except Exception as _e:
                LOG.debug("auto_enroll trigger err: %s", _e)
        nome_h = (utente.get("label") or utente.get("nome") or "").replace("_", " ")
        genere = (utente.get("genere") or "").upper()
        saluto = build_greeting(nome_h, genere)
        result = self.manager.get_screen("result")
        titolo = "Porta aperta" if scope == "porta" else "Cancello aperto"
        image = "assets/door_open.png" if scope == "porta" else ""
        result.mostra_risultato(
            success=True,
            titolo=titolo,
            dettaglio=saluto,
            image_source=image,
        )
        Clock.schedule_once(lambda *_: setattr(self.manager, "current", "result"), 0.2)
        try:
            if saluto and getattr(self.app_ctx, "tts", None):
                tts = self.app_ctx.tts
                self.app_ctx.sound.play(
                    "success",
                    on_end=lambda t=saluto: tts.speak(t),
                    on_end_gap=0.25,
                )
            else:
                self.app_ctx.sound.play("success")
        except Exception as e:
            LOG.debug("tts pin saluto err: %s", e)

    def _maybe_auto_enroll(self, nome: str) -> None:
        ae = getattr(self.app_ctx, "auto_enroller", None)
        if ae is None or not nome:
            return
        # Cattura un singolo frame con la PicamSession se disponibile.
        rgb = None
        try:
            from modules.camera_session import PicamSession  # type: ignore
            sess = PicamSession.instance()
            sess.acquire("face")
            rgb = sess.capture("face")
            sess.release()
        except Exception:
            rgb = None
        if rgb is None:
            return
        try:
            status = ae.maybe_enroll(nome, rgb, face_engine=self.app_ctx.face)
            if status == "rejected":
                try:
                    self.app_ctx.mqtt.publish_evento(
                        "auto_enroll_rejected",
                        {"nome": nome, "method": "pin"},
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def go_home(self) -> None:
        self.app_ctx.activity_touch()
        self.manager.current = "home"

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)
