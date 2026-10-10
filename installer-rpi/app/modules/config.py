"""Caricamento config YAML (con fallback su example)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ricorsivo non distruttivo (override vince su base)."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> Dict[str, Any]:
    """Carica config.yaml + sovrascrive con config.override.yaml (se presente).
    Se config.yaml manca, usa config.example.yaml. Path relativi a app/."""
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(ROOT / "config" / "config.yaml")
    candidates.append(ROOT / "config" / "config.example.yaml")
    base = None
    for p in candidates:
        if p.exists():
            LOG.info("Carico config: %s", p)
            with open(p, encoding="utf-8") as f:
                base = yaml.safe_load(f) or {}
            break
    if base is None:
        raise FileNotFoundError("Nessun config trovato in: %s" % candidates)
    override_path = ROOT / "config" / "config.override.yaml"
    if override_path.exists():
        try:
            with open(override_path, encoding="utf-8") as f:
                ov = yaml.safe_load(f) or {}
            merged = _deep_merge(base, ov)
            LOG.info("Override applicato: %s", override_path)
            return merged
        except Exception as e:
            LOG.warning("Impossibile leggere override (%s): %s", override_path, e)
    return base


def data_path(rel: str) -> Path:
    """Path assoluto sotto app/data/ (creato se manca)."""
    p = ROOT / "data" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
