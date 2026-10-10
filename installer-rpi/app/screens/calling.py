"""Schermata Chiamata: pubblica MQTT (chiamata_in_corso), mostra titolo
grande "Chiamata in corso", nominativo del campanello, timer e bottone
"Annulla chiamata" gigante.

Niente preview camera in questa schermata: il visitatore vede solo il
testo + bottone (UI minimal/visibile a distanza). La camera viene gia'
trasmessa via go2rtc al popup HA del rispondente.

Quando il rispondente preme "videocamera" da HA arriva MQTT
`videocitofono/responder/video=on` -> si passa a ConversationScreen che
mostra il video del rispondente in fullscreen.
"""
from __future__ import annotations

import logging
import time

from kivy.clock import Clock
from kivy.properties import StringProperty

from .bg_screen import BgScreen

LOG = logging.getLogger(__name__)


class CallingScreen(BgScreen):
    nominativo = StringProperty("")
    timer_text = StringProperty("00:00")
    # title_text e' bindato dal KV: di default "Chiamata in corso", viene
    # cambiato in "Porta aperta" quando il rispondente apre il cancello dal
    # popup HA (feedback visivo prima della chiusura automatica).
    title_text = StringProperty("Chiamata in corso")

    TIMEOUT_SEC = 60  # auto-annulla dopo 60s senza interazione
    PORTA_APERTA_HOLD_SEC = 3  # mostra "Porta aperta" prima di chiudere

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._campanello_id = ""
        self._t0 = 0.0
        self._tick_event = None
        self._porta_event = None  # Clock.schedule_once per chiusura post-apertura
        self._annulling = False

    def on_pre_enter(self, *_):
        self._annulling = False
        self.app_ctx.touch.unlock("annulla_chiamata")

    def imposta_chiamata(self, campanello_id: str, nominativo: str) -> None:
        self._campanello_id = campanello_id
        self.nominativo = nominativo

    def on_enter(self, *_):
        self._t0 = time.time()
        # Reset del titolo (potrebbe essere rimasto "Porta aperta" da una
        # chiamata precedente se la screen non e' stata distrutta).
        self.title_text = "Chiamata in corso"
        self._update_timer()
        # NB: il publish MQTT chiamata_in_corso e' fatto da chi avvia
        # la chiamata (HomeScreen._chiama o pulsante GPIO in main.py).
        # NON pubblicare qui: la CallingScreen viene attivata anche a
        # seguito di responder/video=off (pre-fix) o per altri transition
        # interni; pubblicare qui causerebbe falsi trigger di nuova
        # chiamata in HA.
        self._tick_event = Clock.schedule_interval(lambda *_: self._update_timer(), 1)
        # LiveKit + riconoscimento visitatore: avviati da main._enter_call_camera_mode
        # dopo pausa go2rtc (evita conflitto libcamera con rpicam-vid).

    def on_leave(self, *_):
        if self._tick_event:
            self._tick_event.cancel()
            self._tick_event = None
        if self._porta_event:
            self._porta_event.cancel()
            self._porta_event = None
        # Reset titolo per la prossima entrata.
        self.title_text = "Chiamata in corso"

    def _update_timer(self) -> None:
        elapsed = int(time.time() - self._t0)
        m, s = divmod(elapsed, 60)
        self.timer_text = f"{m:02d}:{s:02d}"
        if elapsed >= self.TIMEOUT_SEC:
            self.annulla(timeout=True)

    def annulla(self, timeout: bool = False) -> None:
        if self._annulling:
            return
        if not timeout and not self.app_ctx.touch.try_action("annulla_chiamata", sec=0.7):
            return
        self._annulling = True
        LOG.info("Chiamata annullata (timeout=%s)", timeout)
        # Pubblicando 'annullata' l'automation HA chiude popup + cleanup
        # video uplink/talkback. Questo path copre anche il caso "il
        # rispondente sta gia' parlando" (siamo in conversation): il
        # binary_sensor in HA torna off su questo payload.
        self.app_ctx.mqtt.publish_chiamata("annullata", self._campanello_id)
        try:
            self.manager.current = "home"
        except Exception as e:
            LOG.error("transition home err: %s", e)

    def mostra_risposto_audio(self) -> None:
        """Rispondente HA ha risposto in solo audio: restiamo su questa
        schermata; l'audio del rispondente arriva via LiveKitSubscribeClient
        gia' avviato in on_pre_enter."""
        LOG.info("mostra_risposto_audio")
        self.title_text = "Conversazione audio"

    def mostra_porta_aperta(self) -> None:
        """Mostra la schermata 'Porta aperta' (stessa di apertura via PIN):
        icona door_open + titolo grande, auto-back a home dopo AUTO_BACK_SEC.
        """
        LOG.info("mostra_porta_aperta -> result screen")
        if self._tick_event:
            self._tick_event.cancel()
            self._tick_event = None
        if self._porta_event:
            self._porta_event.cancel()
            self._porta_event = None
        try:
            result = self.manager.get_screen("result")
            result.mostra_risultato(
                success=True,
                titolo="Porta aperta",
                dettaglio="",
                image_source="assets/door_open.png",
            )
            self.manager.current = "result"
        except Exception as e:
            LOG.error("transition result err: %s", e)

    def mostra_chiamata_terminata(self) -> None:
        """Overlay "Chiamata terminata" 3s -> home. Vedi _hold_e_chiudi."""
        self._hold_e_chiudi("Chiamata terminata")

    def _hold_e_chiudi(self, testo: str) -> None:
        """Cambia il titolo della CallingScreen, ferma il timer chiamata
        e schedula il torna-a-home dopo PORTA_APERTA_HOLD_SEC secondi.

        Usato per dare feedback visivo al visitatore esterno quando il
        rispondente compie un'azione decisiva dal popup HA:
          - "Porta aperta"      (azione apri porta)
          - "Chiamata terminata" (azione chiudi chiamata)
        """
        LOG.info("Hold messaggio %r per %ds poi home",
                 testo, self.PORTA_APERTA_HOLD_SEC)
        self.title_text = testo
        # Stoppa timer chiamata: non vogliamo che lo scadere del TIMEOUT
        # durante l'hold di 3s pubblichi 'annullata' (sarebbe gia' uscito
        # dalla schermata, ma evitiamo il publish MQTT inutile).
        if self._tick_event:
            self._tick_event.cancel()
            self._tick_event = None
        # Cancella eventuale schedule precedente (azioni in rapida
        # successione: apri porta poi chiudi).
        if self._porta_event:
            self._porta_event.cancel()
        def _to_home(*_):
            try:
                self.manager.current = "home"
            except Exception as e:
                LOG.error("hold -> home err: %s", e)
        self._porta_event = Clock.schedule_once(_to_home, self.PORTA_APERTA_HOLD_SEC)

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)
