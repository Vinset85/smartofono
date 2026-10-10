"""Monitor connettività MQTT + Home Assistant.

service_mode:
  online  — MQTT connesso e HA raggiungibile
  limited — MQTT down e/o HA non raggiungibile
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import requests

try:
    import urllib3
    # Il probe di raggiungibilita' verso HA punta a un IP LAN (es.
    # https://192.168.1.160:8123) ma il certificato e' emesso per il
    # duckdns: la verifica del nome host fallirebbe a ogni ciclo (ogni 15s)
    # spammando "Certificate did not match" + InsecureRequestWarning nei log,
    # mascherando errori reali. Per un semplice probe di reachability LAN la
    # verifica TLS non serve: silenziamo il warning una volta sola.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:  # pragma: no cover - urllib3 sempre presente con requests
    pass

LOG = logging.getLogger(__name__)


class ConnectivityMonitor:
    def __init__(
        self,
        mqtt_client: Any,
        ha_cfg: Dict[str, Any],
        interval_sec: float = 15.0,
        on_mode_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._mqtt = mqtt_client
        self._ha_cfg = ha_cfg or {}
        self._interval = max(5.0, float(interval_sec))
        self._on_mode_change = on_mode_change
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self._mode = "online"
        self._ha_reachable = True
        self._pending_calls: list[tuple[str, str]] = []

    @property
    def service_mode(self) -> str:
        return self._mode

    @property
    def ha_reachable(self) -> bool:
        return self._ha_reachable

    @property
    def pending_calls_count(self) -> int:
        return len(self._pending_calls)

    def is_online(self) -> bool:
        return self._mode == "online"

    def queue_call(self, camp_id: str, nominativo: str) -> None:
        self._pending_calls.append((camp_id, nominativo))
        LOG.info("chiamata accodata (offline): %s (%s)", camp_id, nominativo)

    def pop_pending_calls(self) -> list[tuple[str, str]]:
        out = list(self._pending_calls)
        self._pending_calls.clear()
        return out

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._loop, name="connectivity", daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop.set()

    def _check_ha(self) -> bool:
        base = str(self._ha_cfg.get("base_url", "")).rstrip("/")
        if not base:
            return True
        # Probe di sola reachability: niente verifica TLS (vedi nota in cima
        # al modulo). verify_identity puo' forzare la verifica se in futuro
        # si usera' un hostname valido invece dell'IP LAN.
        verify = bool(self._ha_cfg.get("verify_identity", False))
        try:
            # /manifest.json e' servito SENZA autenticazione: usarlo come
            # probe evita di colpire /api/ (endpoint autenticato) che ad
            # ogni ciclo (15s) faceva registrare a HA un "Login attempt
            # failed" da questo IP, spammando notifiche. Qualsiasi risposta
            # HTTP < 500 = HA raggiungibile.
            r = requests.get(f"{base}/manifest.json", timeout=3, verify=verify)
            return r.status_code < 500
        except Exception:
            return False

    def _evaluate(self) -> str:
        mqtt_ok = bool(getattr(self._mqtt, "is_connected", lambda: False)())
        ha_ok = self._check_ha()
        self._ha_reachable = ha_ok
        if mqtt_ok and ha_ok:
            return "online"
        return "limited"

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                new_mode = self._evaluate()
                if new_mode != self._mode:
                    prev = self._mode
                    self._mode = new_mode
                    LOG.info("connectivity: %s -> %s", prev, new_mode)
                    if self._on_mode_change:
                        try:
                            self._on_mode_change(new_mode)
                        except Exception as e:
                            LOG.debug("on_mode_change err: %s", e)
            except Exception as e:
                LOG.debug("connectivity loop err: %s", e)
            self._stop.wait(self._interval)
