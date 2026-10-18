"""Versione unica dell'app (boot MQTT, health, Admin)."""
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "version.txt"


def get_version() -> str:
    try:
        return _PATH.read_text(encoding="utf-8").strip() or "dev"
    except Exception:
        return "dev"
