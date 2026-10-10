#!/usr/bin/env python3
"""Integra chiavi mancanti in config.yaml da config.example.yaml.

Eseguito da systemd ExecStartPre prima di ogni avvio app: aggiunge solo
le chiavi presenti nell'esempio versionato ma assenti in config.yaml,
senza sovrascrivere valori già impostati localmente.

Poi applica config.override.yaml con deep merge (override vince).

Preserva da config.yaml esistente:
  home_assistant.token
  mqtt.cmd_secret

Non elimina config.override.yaml dopo l'esecuzione.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("restore_config_defaults: PyYAML mancante", file=sys.stderr)
    sys.exit(1)

APP_CONFIG = Path("/opt/videocitofono/app/config")
EXAMPLE = APP_CONFIG / "config.example.yaml"
TARGET = APP_CONFIG / "config.yaml"
OVERRIDE = APP_CONFIG / "config.override.yaml"


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _merge_missing_keys(base: dict, template: dict) -> dict:
    """Aggiunge a base solo le chiavi mancanti da template (ricorsivo)."""
    out = dict(base)
    for k, v in (template or {}).items():
        if k not in out:
            out[k] = v
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_missing_keys(out[k], v)
    return out


def main() -> int:
    if not EXAMPLE.is_file():
        print(f"restore_config_defaults: manca {EXAMPLE}", file=sys.stderr)
        return 1

    existing = _load(TARGET)
    defaults = _load(EXAMPLE)
    if not existing:
        existing = dict(defaults)

    merged = _merge_missing_keys(existing, defaults)
    override = _load(OVERRIDE) if OVERRIDE.exists() else {}
    result = _deep_merge(merged, override)

    token = (existing.get("home_assistant") or {}).get("token")
    if token:
        ha = dict(result.get("home_assistant") or {})
        ha["token"] = token
        result["home_assistant"] = ha

    cmd_secret = (existing.get("mqtt") or {}).get("cmd_secret")
    if cmd_secret:
        mqtt = dict(result.get("mqtt") or {})
        mqtt["cmd_secret"] = cmd_secret
        result["mqtt"] = mqtt

    APP_CONFIG.mkdir(parents=True, exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as f:
        yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False)

    added = sorted(set(defaults.keys()) - set(existing.keys()))
    print(
        f"restore_config_defaults: {TARGET} merge-only "
        f"({len(added)} sezioni top-level aggiunte: {', '.join(added) or '—'}), "
        f"override={'sì' if override else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
