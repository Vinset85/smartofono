"""Schermata Home: header, lista pulsanti chiamata per nominativo, bottoniera metodi accesso (PIN/Volto/Impronta/NFC) filtrata in base ai flag enabled."""
from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path

from kivy.clock import Clock
from kivy.properties import StringProperty

from modules.access_icons import resolve_access_icon
from .bg_screen import BgScreen
from .widgets import CallButton, IconAccessButton

LOG = logging.getLogger(__name__)


class HomeScreen(BgScreen):
    titolo_app = StringProperty("Videocitofono")
    ora_corrente = StringProperty("--:--")
    offline_banner = StringProperty("")

    def __init__(self, app_ctx, bg_source: str | None = None, **kw):
        super().__init__(bg_source=bg_source, **kw)
        self.app_ctx = app_ctx
        self._clock_event = None

    # Definizione dei metodi di accesso. Ordine = ordine di rendering.
    # (config_section, icon_key, default_icon_type, label, screen_name).
    # config_section e' la chiave top-level di config dove leggere 'enabled'
    # (es. config['face_recognition']['enabled']). icon_key e' la chiave in
    # config['access_icons'] (allineata con HA input_select).
    _ACCESS_METHODS = (
        # (cfg_section,    icon_key,       icon_type,      label,      screen,    default_enabled)
        ("pin",             "pin",          "dialpad",      "PIN",      "pin",      True),
        ("face_recognition", "face",        "face",         "Volto",    "face",     False),
        ("fingerprint",     "fingerprint",  "fingerprint",  "Impronta", "finger",   False),
        ("nfc",             "nfc",          "nfc",          "NFC",      "nfc",      False),
    )

    def _compute_layout_key(self) -> tuple:
        cfg = self.app_ctx.config
        camp = cfg.get("campanelli", []) or []
        camp_key = tuple(
            (c.get("id"), c.get("nome"), c.get("icona"))
            for c in camp
        )
        access_key = tuple(
            (sec, self._is_method_enabled(sec, default))
            for sec, _, _, _, _, default in self._ACCESS_METHODS
        )
        icons = cfg.get("access_icons", {}) or {}
        icon_key = tuple(sorted(icons.items()))
        return (camp_key, access_key, icon_key)

    def on_pre_enter(self, *_):
        key = self._compute_layout_key()
        if getattr(self, "_cached_layout_key", None) != key:
            self._popola_campanelli()
            self._apply_access_methods()
            self._cached_layout_key = key
        self.app_ctx.touch.unlock()
        conn = getattr(self.app_ctx, "connectivity", None)
        if conn is not None:
            self.set_service_mode(conn.service_mode)
        self._tick()
        self._clock_event = Clock.schedule_interval(lambda *_: self._tick(), 1)

    def set_service_mode(self, mode: str) -> None:
        self.offline_banner = (
            "Servizio limitato" if mode == "limited" else "")

    # Wrapper retro-compatibile (chiamato da main._apply_access_icons_live
    # e _sync_icone_library): rifa' anche il filtro enabled cosi' un cambio
    # icona o un sync libreria riapplica tutto correttamente.
    def _apply_access_icons(self) -> None:
        self._apply_access_methods()

    def _is_method_enabled(self, cfg_section: str, default: bool) -> bool:
        """Legge config[<section>].enabled. PIN attivo di default (a meno
        che esplicitamente disabilitato). Gli altri (face/finger/nfc)
        disabilitati di default finche' non vengono attivati da HA.
        """
        sec = self.app_ctx.config.get(cfg_section, {}) or {}
        if not isinstance(sec, dict):
            return default
        v = sec.get("enabled", default)
        return bool(v) if v is not None else default

    def _apply_access_methods(self) -> None:
        """Ricostruisce la bottoniera dei metodi di accesso in base a
        config.<sec>.enabled, applicando icone custom da access_icons.

        - Servizi disabilitati: pulsante NON renderizzato.
        - Servizio attivo: IconAccessButton con icona custom (da
          assets/avatars/<filename>) o VectorIcon di default.
        - cols del GridLayout = numero di pulsanti attivi (max 4) per
          mantenere bottoni quadrati su qualsiasi numero di metodi.
        """
        bar = self.ids.get("bottoniera_accessi")
        if bar is None:
            LOG.warning("_apply_access_methods: bottoniera_accessi non trovata")
            return
        bar.clear_widgets()
        avatars_dir = Path(__file__).resolve().parents[1] / "assets" / "avatars"
        access_icons = self.app_ctx.config.get("access_icons", {}) or {}
        attivi = []
        for cfg_section, icon_key, icon_type, label, screen, default_on in self._ACCESS_METHODS:
            if not self._is_method_enabled(cfg_section, default_on):
                continue
            attivi.append((cfg_section, icon_key, icon_type, label, screen))
        if not attivi:
            LOG.info("nessun metodo di accesso attivo, bottoniera vuota")
            bar.cols = 1
            return
        bar.cols = len(attivi)
        for cfg_section, icon_key, default_icon_type, label, screen in attivi:
            icona, itype = resolve_access_icon(
                self.app_ctx, icon_key, default_icon_type)
            if not icona and not itype:
                raw = (access_icons.get(icon_key) or "").strip()
                if raw:
                    LOG.warning("access_icons[%s]: %s non trovata",
                                icon_key, avatars_dir / raw)
            btn = IconAccessButton(label=label)
            if icona:
                btn.icon_type = ""
                btn.icona = icona
            else:
                btn.icona = ""
                btn.icon_type = itype
            btn.bind(on_release=lambda inst, s=screen: self.go(s))
            bar.add_widget(btn)
        LOG.info("bottoniera accessi: %d metodi attivi (%s)",
                 len(attivi), ",".join(a[0] for a in attivi))
        self._cached_layout_key = self._compute_layout_key()

    def on_leave(self, *_):
        if self._clock_event:
            self._clock_event.cancel()
            self._clock_event = None

    def _tick(self) -> None:
        self.ora_corrente = datetime.datetime.now().strftime("%H:%M")

    def _popola_campanelli(self) -> None:
        container = self.ids.get("lista_campanelli")
        if not container:
            LOG.warning("_popola_campanelli: container ids non trovato")
            return
        container.clear_widgets()
        campanelli = self.app_ctx.config.get("campanelli", [])
        for c in campanelli:
            icona = c.get("icona") or ""
            if icona and not os.path.isabs(icona):
                # Risoluzione progressiva del filename:
                # 1) path relativo all'app/ (es. "assets/avatars/x.png" gia' completo)
                # 2) solo basename → cerca in app/assets/avatars/<filename>
                # Ricaduta a "" se nessun candidato esiste (CallButton mostra default).
                from pathlib import Path
                base = Path(__file__).resolve().parents[1]
                candidates = [base / icona, base / "assets" / "avatars" / icona]
                resolved = next((p for p in candidates if p.exists()), None)
                if resolved is None:
                    LOG.warning("Icona non trovata: %s (cercata in %s), uso default",
                                icona, [str(p) for p in candidates])
                    icona = ""
                else:
                    icona = str(resolved)
            btn = CallButton(nominativo=c.get("nome", "?"), icona=icona)
            btn.bind(on_release=lambda inst, cid=c["id"], cn=c.get("nome", "?"): self._chiama(cid, cn))
            container.add_widget(btn)
        self._cached_layout_key = self._compute_layout_key()

    def _chiama(self, campanello_id: str, nominativo: str) -> None:
        if self.manager.current != "home":
            return
        if not self.app_ctx.touch.try_action(f"call:{campanello_id}", sec=0.9):
            return
        conn = getattr(self.app_ctx, "connectivity", None)
        if conn is not None and not conn.is_online():
            conn.queue_call(campanello_id, nominativo)
            self.offline_banner = "Servizio limitato"
            LOG.warning("chiamata accodata (offline): %s", campanello_id)
            return
        LOG.info("Chiamata campanello: %s (%s)", campanello_id, nominativo)
        self.app_ctx.activity_touch()
        try:
            self.app_ctx.sound.play("bell")
        except Exception:
            pass
        # Configura sia CallingScreen (fallback se conversation non e'
        # disponibile) sia ConversationScreen.
        calling = self.manager.get_screen("calling")
        calling.imposta_chiamata(campanello_id, nominativo)
        # Publish MQTT chiamata_in_corso PRIMA del transition.
        try:
            self.app_ctx.mqtt.publish_chiamata("chiamata_in_corso", campanello_id)
        except Exception as e:
            LOG.warning("publish chiamata_in_corso err: %s", e)
        # Flusso ring->answer (2026-05): squillo in CallingScreen
        # (titolo "Chiamata in corso" + Annulla). La ConversationScreen
        # parte solo dopo che il rispondente HA preme "Rispondi"
        # (MQTT chiamata=risposto -> _handle_chiamata transitiona a
        # conversation). Vedi main.py:_handle_chiamata.
        self.manager.current = "calling"

    def go(self, screen_name: str) -> None:
        if not self.app_ctx.touch.try_action(f"nav:{screen_name}", sec=0.5):
            return
        self.app_ctx.activity_touch()
        try:
            self.app_ctx.sound.play("click")
        except Exception:
            pass
        instant = screen_name in ("face", "pin", "nfc", "finger")
        self.app_ctx.go_screen(screen_name, instant=instant)

    def on_touch_down(self, touch):
        self.app_ctx.activity_touch()
        return super().on_touch_down(touch)
