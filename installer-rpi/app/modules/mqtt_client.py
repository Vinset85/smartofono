"""Client MQTT per pubblicare eventi e ricevere comandi/segnali da Home Assistant.

Pubblica su:
  videocitofono/chiamata           "chiamata_in_corso" | "annullata"
  videocitofono/apertura           {"metodo": "pin|face|nfc|admin", "utente": "...", "scope": "porta|cancello"}
  videocitofono/evento             eventi diagnostica (boot, errore, ecc)

Si sottoscrive a:
  videocitofono/wake               qualunque payload -> sveglia schermo (motion detection lato HA)
  videocitofono/cmd                comandi remoti opzionali ({"action": "show", "screen": "home"})
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

LOG = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        try:
            # paho 2.x richiede CallbackAPIVersion
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id="videocitofono-rpi",
            )
        except (AttributeError, TypeError):
            self._client = mqtt.Client(client_id="videocitofono-rpi")  # paho 1.x
        if cfg.get("username"):
            self._client.username_pw_set(cfg["username"], cfg.get("password", ""))
        # Availability / Last-Will. Il broker pubblichera' "offline" (retain)
        # su questo topic se la connessione cade in modo non pulito
        # (crash/rete/spina). Va impostato PRIMA di connect(). Alla
        # connessione pubblichiamo "online" (retain) come birth message.
        self._status_topic = cfg.get("topic_status", "videocitofono/status")
        try:
            self._client.will_set(
                self._status_topic, payload="offline", qos=1, retain=True
            )
        except Exception as e:
            LOG.warning("MQTT will_set fallito: %s", e)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._connected = threading.Event()
        self._wake_cb: Optional[Callable[[Dict[str, Any]], None]] = None
        self._cmd_cb: Optional[Callable[[Dict[str, Any]], None]] = None
        self._responder_video_cb: Optional[Callable[[str], None]] = None
        self._responder_audio_cb: Optional[Callable[[str], None]] = None
        self._chiamata_cb: Optional[Callable[[str], None]] = None
        self._on_connected_cb: Optional[Callable[[], None]] = None
        # Ultimo campanello visto in un payload chiamata JSON. Usato dal
        # main per recuperare l'ID quando chiamata_in_corso arriva via
        # MQTT (test da HA) e va aperta CallingScreen con nominativo.
        self.last_campanello: str = ""

    def on_wake(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        """Registra callback chiamata su msg in `videocitofono/wake`.
        Riceve dict (vuoto se payload non JSON)."""
        self._wake_cb = cb

    def on_cmd(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        """Registra callback su `videocitofono/cmd` per comandi remoti."""
        self._cmd_cb = cb

    def on_responder_video(self, cb: Callable[[str], None]) -> None:
        """Registra callback su `videocitofono/responder/video`. Riceve
        la stringa raw del payload ("on" / "off"). Usato dal main per
        switchare alla schermata Conversazione quando il browser HA
        avvia il video uplink WHIP."""
        self._responder_video_cb = cb

    def on_responder_audio(self, cb: Callable[[str], None]) -> None:
        """Registra callback su `videocitofono/responder/audio`. Riceve
        "on" / "off". Usato dal main per attivare il consumer
        WebRTCAudioController quando il rispondente HA risponde in
        modalita' audio-only (nessun video downlink, RPi resta su
        CallingScreen ma riceve l'audio del rispondente via WebRTC)."""
        self._responder_audio_cb = cb

    def on_chiamata(self, cb: Callable[[str], None]) -> None:
        """Registra callback su `videocitofono/chiamata`. Riceve "stato"
        normalizzato ("chiamata_in_corso" | "annullata"). Usato dal main
        per tornare a home quando HA chiude la chiamata (popup chiudi,
        timeout 60s, browser_mod.close_popup): cosi' il RPi non resta
        bloccato su CallingScreen/ConversationScreen aspettando il proprio
        timeout interno."""
        self._chiamata_cb = cb

    def on_connected(self, cb: Callable[[], None]) -> None:
        """Dopo un connect riuscito (anche in riconnessione)."""
        self._on_connected_cb = cb

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            LOG.info("MQTT connesso a %s:%s", self.cfg["broker"], self.cfg["port"])
            self._connected.set()
            try:
                client.subscribe(self.cfg.get("topic_wake", "videocitofono/wake"), qos=0)
                client.subscribe(self.cfg.get("topic_cmd", "videocitofono/cmd"), qos=1)
                client.subscribe(
                    self.cfg.get("topic_responder_video", "videocitofono/responder/video"),
                    qos=1,
                )
                client.subscribe(
                    self.cfg.get("topic_responder_audio", "videocitofono/responder/audio"),
                    qos=1,
                )
                client.subscribe(
                    self.cfg.get("topic_chiamata", "videocitofono/chiamata"),
                    qos=1,
                )
            except Exception as e:
                LOG.error("MQTT subscribe err: %s", e)
            # Birth message: ci dichiariamo online (retain) cosi' HA marca
            # le entita' come disponibili anche se si (ri)connette dopo.
            try:
                client.publish(self._status_topic, "online", qos=1, retain=True)
                LOG.info("MQTT availability: online (%s)", self._status_topic)
            except Exception as e:
                LOG.error("MQTT birth publish err: %s", e)
            if self._on_connected_cb:
                try:
                    self._on_connected_cb()
                except Exception as e:
                    LOG.error("MQTT on_connected cb err: %s", e)
        else:
            LOG.error("MQTT connect rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        LOG.warning("MQTT disconnesso rc=%s", rc)
        self._connected.clear()

    def _on_message(self, client, userdata, msg):
        LOG.info("MQTT msg %s = %s", msg.topic, msg.payload[:200])
        topic_wake = self.cfg.get("topic_wake", "videocitofono/wake")
        topic_cmd = self.cfg.get("topic_cmd", "videocitofono/cmd")
        topic_responder_video = self.cfg.get(
            "topic_responder_video", "videocitofono/responder/video"
        )
        topic_responder_audio = self.cfg.get(
            "topic_responder_audio", "videocitofono/responder/audio"
        )
        topic_chiamata = self.cfg.get("topic_chiamata", "videocitofono/chiamata")
        # Per responder_video/audio il payload e' "on"/"off" (non JSON).
        # Lo gestiamo prima per evitare il JSON parse warning.
        if msg.topic == topic_responder_video:
            raw = (msg.payload or b"").decode(errors="ignore").strip().lower()
            try:
                if self._responder_video_cb:
                    self._responder_video_cb(raw)
            except Exception as e:
                LOG.error("MQTT responder_video cb err: %s", e)
            return
        if msg.topic == topic_responder_audio:
            raw = (msg.payload or b"").decode(errors="ignore").strip().lower()
            try:
                if self._responder_audio_cb:
                    self._responder_audio_cb(raw)
            except Exception as e:
                LOG.error("MQTT responder_audio cb err: %s", e)
            return
        # Topic chiamata accetta sia stringa raw ("annullata",
        # "chiamata_in_corso") sia JSON ({"stato": "...", "campanello":
        # "..."}). Normalizziamo a stringa "stato".
        if msg.topic == topic_chiamata:
            raw_bytes = msg.payload or b""
            raw = raw_bytes.decode(errors="ignore").strip()
            stato = raw
            campanello = ""
            if raw.startswith("{"):
                try:
                    parsed = json.loads(raw) or {}
                    stato = parsed.get("stato", "")
                    campanello = str(parsed.get("campanello", "") or "")
                except Exception:
                    stato = ""
            # Memorizza ultimo campanello cosi' chi gestisce
            # "chiamata_in_corso" arrivato via MQTT (es. test da HA, in
            # cui non c'e' button fisico) puo' recuperare l'id e impostare
            # la CallingScreen con il nominativo corretto.
            if campanello:
                self.last_campanello = campanello
            try:
                if self._chiamata_cb:
                    self._chiamata_cb(stato)
            except Exception as e:
                LOG.error("MQTT chiamata cb err: %s", e)
            return
        try:
            payload = json.loads(msg.payload.decode()) if msg.payload else {}
        except Exception:
            payload = {"raw": msg.payload.decode(errors="ignore")}
        try:
            if msg.topic == topic_wake and self._wake_cb:
                self._wake_cb(payload)
            elif msg.topic == topic_cmd and self._cmd_cb:
                if getattr(msg, "retain", False):
                    LOG.info("MQTT cmd retain ignorato (pulire videocitofono/cmd)")
                    return
                self._cmd_cb(payload)
        except Exception as e:
            LOG.error("MQTT cb err: %s", e)

    def start(self) -> None:
        try:
            self._client.connect(self.cfg["broker"], self.cfg.get("port", 1883), 30)
            self._client.loop_start()
        except Exception as e:
            LOG.error("MQTT connect failed: %s", e)

    def stop(self) -> None:
        # Offline esplicito su shutdown pulito (il LWT NON viene inviato dal
        # broker quando il disconnect e' regolare): pubblichiamo "offline"
        # retain e lasciamo un attimo al loop per il flush prima di chiudere.
        try:
            self._client.publish(self._status_topic, "offline", qos=1, retain=True)
            import time as _t
            _t.sleep(0.3)
        except Exception:
            pass
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def publish_chiamata(self, payload: str = "chiamata_in_corso", campanello: str | None = None) -> None:
        topic = self.cfg["topic_chiamata"]
        msg = payload if campanello is None else json.dumps({"stato": payload, "campanello": campanello})
        try:
            from modules.log_setup import audit
            audit(LOG, "chiamata", stato=payload, campanello=campanello or "")
        except Exception:
            pass
        # Retain: dopo un restart HA il binary_sensor non resta
        # unavailable fino al prossimo campanello.
        self._publish(topic, msg, retain=True)

    def publish_apertura(self, metodo: str, utente: str = "", scope: str = "porta") -> None:
        topic = self.cfg["topic_apertura"]
        import time as _t
        msg = json.dumps({"metodo": metodo, "utente": utente, "scope": scope,
                          "ts": int(_t.time())})
        self._publish(topic, msg)

    def publish_evento(self, tipo: str, dati: Dict[str, Any] | None = None) -> None:
        topic = self.cfg["topic_evento"]
        msg = json.dumps({"tipo": tipo, "dati": dati or {}})
        self._publish(topic, msg)

    def publish(self, topic: str, msg: str, retain: bool = False, qos: int = 1) -> None:
        """Publish pubblico: usato da HealthReporter, UnknownTracker, ecc."""
        try:
            r = self._client.publish(topic, msg, qos=qos, retain=bool(retain))
            LOG.debug("MQTT pub %s (retain=%s) rc=%s", topic, retain, getattr(r, "rc", "?"))
        except Exception as e:
            LOG.error("MQTT publish error: %s", e)

    def _publish(self, topic: str, msg: str, retain: bool = False) -> None:
        try:
            r = self._client.publish(topic, msg, qos=1, retain=retain)
            LOG.info("MQTT pub %s = %s (retain=%s rc=%s)", topic, msg, retain, r.rc)
        except Exception as e:
            LOG.error("MQTT publish error: %s", e)
