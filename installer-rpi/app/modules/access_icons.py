"""Risoluzione icone metodi di accesso (PIN, volto, NFC).

Default allineati a config.example.yaml / videocitofono_defaults.json HA.
I PNG di default sono in app/assets/avatars/ (shippati col deploy).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Tuple

# Filename PNG di default per metodo (non usare icona vettoriale se presente).
DEFAULT_ACCESS_ICONS = {
    "pin": "icons8-keypad-100.png",
    "face": "icons8-face-id-100.png",
    "nfc": "icons8-rfid-500.png",
}

# Varianti obsolete in config/HA: mappa sempre al bundled di default.
_LEGACY_NFC_ICONS = frozenset({
    "icons8-rfid-signal-100.png",
    "icons8-rfid-signal-500.png",
    "icons8-rfid-250.png",
})


def avatars_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "avatars"


def bundled_icon_filenames() -> frozenset[str]:
    """PNG di default shippati col deploy: non vanno mai rimossi dal sync HA."""
    return frozenset(DEFAULT_ACCESS_ICONS.values())


def resolve_access_icon(
    app_ctx: Any,
    icon_key: str,
    vector_type: str = "",
) -> Tuple[str, str]:
    """Ritorna (path_png, icon_type_vettoriale).

    Ordine: icona config/HA se presente, altrimenti PNG bundled di default,
    infine VectorIcon legacy. I bundled evitano flash all'avvio prima del sync.
    """
    cfg = (getattr(app_ctx, "config", None) or {}).get("access_icons", {}) or {}
    raw = (cfg.get(icon_key) or "").strip()
    if icon_key == "nfc" and raw in _LEGACY_NFC_ICONS:
        raw = ""
    if not raw or raw == "default":
        raw = ""

    adir = avatars_dir()
    default_fn = DEFAULT_ACCESS_ICONS.get(icon_key, "")
    candidates: list[Path] = []
    if raw:
        candidates.append(
            Path(raw) if os.path.isabs(raw) else adir / os.path.basename(raw))
    if default_fn:
        dp = adir / default_fn
        if dp not in candidates:
            candidates.append(dp)

    for p in candidates:
        if p.is_file():
            return str(p), ""

    return "", vector_type or icon_key
