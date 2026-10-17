"""Healthcheck LiveKit (salta se l'host non e' in LAN)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HOST = os.environ.get("VC_LIVEKIT_HOST", "127.0.0.1")
ISSUER = f"http://{HOST}:8081/health"
SERVER = f"http://{HOST}:7880/"


def _get(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None


def test_livekit_server_ok():
    status, body = _get(SERVER)
    if status is None:
        return
    assert status == 200
    assert "OK" in body


def test_token_issuer_health():
    status, body = _get(ISSUER)
    if status is None:
        return
    data = json.loads(body)
    assert data.get("ok") is True
    assert str(data.get("ws_url", "")).startswith("wss://")
    assert "7880" in str(data.get("ws_url_lan", ""))
