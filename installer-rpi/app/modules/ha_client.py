"""Client REST verso Home Assistant per chiamare service script (apri porta/cancello)."""
from __future__ import annotations

import logging
from typing import Any, Dict

import requests

LOG = logging.getLogger(__name__)


class HaClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.base = cfg["base_url"].rstrip("/")
        self.token = cfg.get("token", "")
        self._session = requests.Session()
        if self.token:
            self._session.headers.update({"Authorization": f"Bearer {self.token}"})
        self._session.headers.update({"Content-Type": "application/json"})

    def _domain_service(self, entity_id: str) -> tuple[str, str]:
        # script.cancello_ingresso -> (script, turn_on) con entity_id
        # In HA, script si attiva via script.<id>/turn_on (oppure direttamente script.<id>)
        return entity_id.split(".", 1)

    def call_service(self, entity_id: str) -> bool:
        if not self.token:
            LOG.warning("HA token mancante, salto chiamata service %s", entity_id)
            return False
        domain, name = self._domain_service(entity_id)
        url = f"{self.base}/api/services/{domain}/turn_on"
        try:
            r = self._session.post(url, json={"entity_id": entity_id}, timeout=3)
            ok = r.status_code in (200, 201)
            LOG.info("HA service %s -> %s", entity_id, r.status_code)
            return ok
        except Exception as e:
            LOG.error("HA service error: %s", e)
            return False

    def apri_porta(self) -> bool:
        return self.call_service(self.cfg["script_apri_porta"])

    def apri_cancello(self) -> bool:
        return self.call_service(self.cfg["script_apri_cancello"])
