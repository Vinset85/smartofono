#!/usr/bin/env python3
"""Esegue le test_* stdlib (niente pytest)."""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "installer-ha/tests/test_ha_templates.py",
    ROOT / "installer-ha/tests/test_livekit_health.py",
    ROOT / "installer-rpi/tests/test_smoke.py",
]


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    failed = 0
    ran = 0
    for path in FILES:
        mod = load(path)
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            ran += 1
            try:
                getattr(mod, name)()
                print("ok", path.stem, name)
            except Exception:
                failed += 1
                print("FAIL", path.stem, name)
                traceback.print_exc()
    print("ran", ran, "failed", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
