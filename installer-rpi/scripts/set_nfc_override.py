#!/usr/bin/env python3
"""Imposta sezione nfc in config.override.yaml (abilitato, PN532 UART)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

path = Path("/opt/videocitofono/app/config/config.override.yaml")
existing = {}
if path.is_file():
    with path.open(encoding="utf-8") as f:
        existing = yaml.safe_load(f) or {}
nfc = existing.get("nfc") if isinstance(existing.get("nfc"), dict) else {}
nfc.update({
    "enabled": True,
    "device": nfc.get("device") or "tty:USB0:pn532",
    "device_candidates": nfc.get("device_candidates")
    or ["tty:USB0:pn532", "tty:USB1:pn532", "i2c:1:0x24"],
    "cooldown_sec": float(nfc.get("cooldown_sec", 2.0)),
    "library_path": nfc.get("library_path")
    or "/opt/videocitofono/data/nfc_tags.json",
})
existing["nfc"] = nfc
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("w", encoding="utf-8") as f:
    yaml.safe_dump(existing, f, allow_unicode=True, sort_keys=False)
print("nfc override ok")
