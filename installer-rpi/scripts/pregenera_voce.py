#!/usr/bin/env python3
"""Pre-genera in cache i saluti vocali degli utenti registrati.

Da lanciare sul Pi dopo un cambio di voce o quando si aggiunge una persona:

    sudo -u vinset /opt/videocitofono/venv/bin/python3 \
        /opt/videocitofono/scripts/pregenera_voce.py

Perche' serve: la voce neurale ha bisogno di internet per sintetizzare, non
per parlare. Preparando le frasi in anticipo, all'apertura della porta il
saluto parte subito e continua a funzionare anche con la rete giu'.

Genera tutte le varianti di `greetings` per ogni nome e fascia oraria, cioe'
esattamente le frasi che il citofono puo' pronunciare.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP = Path("/opt/videocitofono/app")
sys.path.insert(0, str(APP))

from modules.greetings import _TEMPLATES  # noqa: E402
from modules.tts import Tts  # noqa: E402


def persone() -> list[tuple[str, str]]:
    """(nome, genere) dai volti registrati; genere ignoto -> entrambe le forme."""
    out: list[tuple[str, str]] = []
    faces = Path("/opt/videocitofono/data/faces")
    for d in sorted(p for p in faces.glob("*") if p.is_dir()
                    and not p.name.startswith(".")):
        genere = ""
        meta = d / "meta.json"
        if meta.is_file():
            try:
                genere = (json.loads(meta.read_text()).get("genere") or "").upper()
            except Exception:
                genere = ""
        nome = d.name.replace("_", " ")
        if genere in ("M", "F"):
            out.append((nome, genere))
        else:
            out.extend([(nome, "M"), (nome, "F")])
    return out


def config_tts() -> dict:
    for p in (APP / "config/config.override.yaml", APP / "config/config.yaml"):
        if not p.is_file():
            continue
        try:
            import yaml
            d = yaml.safe_load(p.read_text()) or {}
        except Exception:
            continue
        t = d.get("tts")
        if isinstance(t, dict) and t.get("engine") == "edge":
            return t
    return {}


def main() -> int:
    cfg = config_tts()
    tts = Tts(
        enabled=True,
        engine="edge",
        volume=float(cfg.get("volume", 1.0)),
        edge_voice=str(cfg.get("edge_voice", "")),
        edge_rate=str(cfg.get("edge_rate", "+0%")),
        cache_dir=str(cfg.get("cache_dir", "")),
    )
    if tts.engine != "edge":
        print("ERRORE: la voce neurale non e' disponibile (edge-tts o ffmpeg "
              "mancanti)", file=sys.stderr)
        return 1

    frasi: set[str] = set()
    for nome, genere in persone():
        for (slot, g), templates in _TEMPLATES.items():
            if g and g != genere:
                continue
            for tpl in templates:
                frasi.add(" ".join(tpl.format(nome=nome).split()))

    print(f"voce: {tts.edge_voice}  cache: {tts.cache_dir}")
    print(f"frasi da preparare: {len(frasi)}")
    fatte = gia_pronte = errori = 0
    for f in sorted(frasi):
        if os.path.isfile(tts.percorso_cache(f)):
            gia_pronte += 1
            continue
        if tts.prepara(f):
            fatte += 1
        else:
            errori += 1
            print(f"  non riuscita: {f}", file=sys.stderr)
    print(f"nuove: {fatte}  gia' pronte: {gia_pronte}  non riuscite: {errori}")
    return 1 if errori and not fatte else 0


if __name__ == "__main__":
    raise SystemExit(main())
