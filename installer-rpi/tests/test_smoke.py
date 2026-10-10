"""Smoke test moduli videocitofono (senza hardware)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(ROOT))


def test_cmd_auth():
    from modules.cmd_auth import CmdAuthGuard

    g = CmdAuthGuard({"cmd_secret": "abc", "cmd_rate_limit_sec": 60})
    assert g.verify({"action": "wake", "token": "abc"})
    assert not g.verify({"action": "wake", "token": "bad"})
    assert g.allow_dangerous("restart_app")
    assert not g.allow_dangerous("restart_app")


def test_face_match():
    from modules.face_match import decide_match, user_min_distances

    ud = user_min_distances([0.32, 0.50, 0.33], ["mario", "luigi", "mario"])
    assert ud["mario"] == 0.32
    ok = decide_match(ud, threshold=0.40, margin=0.05)
    assert ok and ok["match"] is True
    tight = decide_match({"a": 0.30, "b": 0.32}, threshold=0.40, margin=0.05)
    assert tight and tight["match"] is False


def test_anomaly():
    from modules.anomaly import AnomalyDetector

    class _DB:
        def _cursor(self):
            raise RuntimeError("no db in test")

    d = AnomalyDetector(_DB(), min_samples=999)
    r = d.evaluate("test", hour=12)
    assert r["is_anomaly"] is False


def test_touch_controller():
    from modules.touch_controller import TouchController

    tc = TouchController()
    assert tc.try_action("test", sec=0.1)
    assert not tc.try_action("test", sec=0.1)


def test_backup_targets():
    from modules.backup import BackupRunner

    b = BackupRunner({}, root="/tmp/vc-test")
    names = [Path(p).name for p in b.targets]
    assert "users.json" in names
    assert "guest_pins.json" in names
    assert "nfc_tags.json" in names


def test_fingerprint_stub():
    from modules.fingerprint_reader import FingerprintReader

    fp = FingerprintReader({"enabled": True})
    assert not fp.is_available()
    assert fp.enroll_next() is None
