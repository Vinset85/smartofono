"""Smoke test moduli videocitofono (senza hardware)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(ROOT))


def test_mqtt_cmd_retain_ignorato():
    from modules.mqtt_client import MqttPublisher

    class _Msg:
        def __init__(self, retain):
            self.topic = "videocitofono/cmd"
            self.payload = b'{"action":"set_config"}'
            self.retain = retain

    p = MqttPublisher(
        {"broker": "127.0.0.1", "port": 1883, "topic_chiamata": "t",
         "topic_cmd": "videocitofono/cmd",
         "topic_status": "videocitofono/status"}
    )
    seen = []
    p.on_cmd(lambda d: seen.append(d))
    p._on_message(p._client, None, _Msg(True))
    assert seen == []
    p._on_message(p._client, None, _Msg(False))
    assert seen and seen[0].get("action") == "set_config"
    n = len(seen)

    class _Empty:
        topic = "videocitofono/cmd"
        payload = b""
        retain = False

    p._on_message(p._client, None, _Empty())
    assert len(seen) == n


def test_mqtt_on_connected_cb():
    from modules.mqtt_client import MqttPublisher

    p = MqttPublisher(
        {"broker": "127.0.0.1", "port": 1883, "topic_chiamata": "t",
         "topic_status": "videocitofono/status"}
    )
    seen = []
    p.on_connected(lambda: seen.append(True))
    p._on_connect(p._client, None, None, 0)
    assert seen == [True]
    p._on_connect(p._client, None, None, 5)
    assert seen == [True]


def test_nfc_usb_recover_max():
    from modules import nfc_reader as nr

    assert nr.USB_RECOVER_MAX == 0
    assert nr.NFC_OPEN_FAILS_BEFORE_USB >= 6
    assert "ensure_pn532_ready" in Path(nr.__file__).read_text(encoding="utf-8")
    assert 5 <= nr.NFC_GIVE_UP_BACKOFF_SEC <= 30
    src = Path(nr.__file__).read_text(encoding="utf-8")
    assert "esce solo su stop() esplicito" in src
    assert "riapertura ascolto" in src
    assert "uart_pn532_reset_and_wake" in src
    assert "reset software" in src
    assert "USB_RECOVER_RETRY_SEC" in src
    assert "_emit_status" in src
    script = Path(nr.__file__).resolve().parents[2] / "scripts" / "nfc-usb-reset.sh"
    sh = script.read_text(encoding="utf-8")
    assert "dwc3_reset_ch340_controller" in sh
    assert "1f00300000.usb" in sh
    assert "skip VBUS" in sh


def test_kiosk_attende_labwc():
    root = Path(__file__).resolve().parents[1]
    unit = (root / "systemd" / "videocitofono.service").read_text(encoding="utf-8")
    assert "wait-kiosk-display.sh" in unit
    assert "display-manager.service" in unit
    wait = (root / "scripts" / "wait-kiosk-display.sh").read_text(encoding="utf-8")
    assert "wayland-0" in wait
    guard = (root / "scripts" / "kiosk-ensure-session.sh").read_text(encoding="utf-8")
    assert "restart lightdm" in guard


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


def test_door_relay_impulso_locale():
    from modules.door_gpio import DoorRelay

    off = DoorRelay({"enabled": False})
    assert off.gpio_for("porta") == 12
    assert off.gpio_for("cancello") == 13
    assert off.pulse("porta") is False

    calls: list[tuple[int, int]] = []
    r = DoorRelay({"enabled": False, "pulse_ms": 20, "porta_gpio": 12})
    r.enabled = True
    r._backend = "mock"
    r._lgpio = None
    r._claim_output = lambda gpio: None
    r._write = lambda gpio, level: calls.append((gpio, int(level)))
    assert r.pulse("porta") is True
    assert calls[0] == (12, 1)
    cfg = (ROOT / "config" / "config.example.yaml").read_text()
    assert "porta_gpio: 12" in cfg
    main = (ROOT / "main.py").read_text()
    assert "def open_access" in main
    assert "DoorRelay" in main


def test_fingerprint_rimosso():
    assert not (ROOT / "modules" / "fingerprint_reader.py").exists()
    cfg = (ROOT / "config" / "config.example.yaml").read_text()
    assert "fingerprint" not in cfg
    main = (ROOT / "main.py").read_text()
    assert "FingerprintReader" not in main
    assert "FingerScreen" not in main
    kv = (ROOT / "videocitofono.kv").read_text()
    assert "FingerScreen" not in kv
    home = (ROOT / "screens" / "home.py").read_text()
    assert "fingerprint" not in home


def test_cmd_auth_senza_secret_accetta():
    from modules.cmd_auth import CmdAuthGuard

    g = CmdAuthGuard({"cmd_secret": ""})
    assert not g.enabled
    assert g.verify({"action": "reboot"})


def test_guest_pin_ciclo():
    import os
    import tempfile

    from modules.guest_pin import GuestPinManager

    path = os.path.join(tempfile.mkdtemp(), "guest_pins.json")
    m = GuestPinManager(path=path, length=6)
    rid, pin = m.create(label="smoke", valid_hours=1, max_uses=1, scope="porta")
    assert len(pin) == 6
    listed = m.list()
    assert listed and listed[0]["id"] == rid
    assert listed[0]["label"] == "smoke"
    hit = m.try_match(pin)
    assert hit is not None and hit["scope"] == "porta"
    assert m.try_match(pin) is None


def test_brightness_off_on(monkeypatch=None):
    from modules.brightness import BrightnessController

    calls = []

    def fake_run(cmd, **_kw):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = "HDMI-A-1 unknown\n"
        return R()

    import modules.brightness as br
    orig = br.subprocess.run
    br.subprocess.run = fake_run
    try:
        c = BrightnessController(prefer_software_dim=True)
        c._backend = "software"
        assert c._has_cmd("wlr-randr")
        c.off()
        assert c.is_off
        c.ensure_on()
        assert not c.is_off
        assert any(cmd[:2] == ["wlr-randr", "--output"] for cmd in calls if isinstance(cmd, list))
    finally:
        br.subprocess.run = orig


def test_version_unica():
    from modules.version import get_version

    v = get_version()
    assert v == (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    assert v == "1.5.3"
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "from modules.version import get_version" in main
    assert '"0.1.0"' not in main
    health = (ROOT / "modules" / "health.py").read_text(encoding="utf-8")
    assert "1.4.0" not in health


def test_reed_disabilitato_di_default():
    from modules.reed import ReedSwitch

    r = ReedSwitch({})
    assert r.enabled is False
    assert r.status() == "off"
    cfg = (ROOT / "config" / "config.example.yaml").read_text(encoding="utf-8")
    assert "tamper:" in cfg
    assert "enabled: false" in cfg
    assert "gpio: 27" in cfg


def test_backup_restore_roundtrip():
    import os
    import tarfile
    import tempfile

    from modules.backup import BackupRunner

    src = tempfile.mkdtemp()
    dest = os.path.join(src, "opt")
    os.makedirs(os.path.join(dest, "data"), exist_ok=True)
    marker = os.path.join(dest, "data", "users.json")
    Path(marker).write_text('{"ok": 1}', encoding="utf-8")
    archive = os.path.join(src, "vc-backup-test.tar.gz")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(marker, arcname="data/users.json")
    out = os.path.join(src, "restored")
    b = BackupRunner({}, root=dest)
    assert b.restore(archive, dest_root=out) is True
    restored = Path(out) / "data" / "users.json"
    assert restored.read_text(encoding="utf-8") == '{"ok": 1}'
    evil = os.path.join(src, "evil.tar.gz")
    with tarfile.open(evil, "w:gz") as tf:
        info = tarfile.TarInfo(name="../escape.txt")
        data = b"nope"
        info.size = len(data)
        tf.addfile(info, fileobj=__import__("io").BytesIO(data))
    assert b.restore(evil, dest_root=out) is True
    assert not (Path(out).parent / "escape.txt").exists()


def test_kivy_fit_mode_e_watchdog_clock():
    kv = (ROOT / "videocitofono.kv").read_text(encoding="utf-8")
    assert "keep_ratio" not in kv
    assert "allow_stretch" not in kv
    assert "fit_mode:" in kv
    assert "<AdminScreen>:" in kv
    wd = (ROOT / "modules" / "watchdog_systemd.py").read_text(encoding="utf-8")
    assert "Clock.schedule_interval" in wd
    assert "threading.Thread" not in wd
    deploy = Path(__file__).resolve().parents[1] / "scripts" / "deploy.sh"
    sh = deploy.read_text(encoding="utf-8")
    assert "UPGRADE_DEPS" in sh
    assert "skip upgrade-deps" in sh
    assert "SKIP_APT=1" in sh
    assert "skip configure-static-ip" in sh
    inst = (Path(__file__).resolve().parents[1] / "scripts" / "install.sh").read_text()
    assert "rpi-connect" in inst
    assert "SKIP_APT" in inst
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "AdminScreen" in main
    assert "ReedSwitch" in main
    lk = (ROOT / "modules" / "livekit_client.py").read_text(encoding="utf-8")
    assert "asyncio.all_tasks" in lk
    health = (ROOT / "modules" / "health.py").read_text(encoding="utf-8")
    assert "usb_overcurrent" in health
    assert "window_sec" in health
    assert '"192.168.1.1"' not in health
    assert "out[\"gw\"]" in health or "out['gw']" in health
    assert "nfc_recovering" in main
    home = (ROOT / "screens" / "home.py").read_text(encoding="utf-8")
    assert "pending_admin" in home
    pin = (ROOT / "screens" / "pin.py").read_text(encoding="utf-8")
    assert 'ruolo != "admin"' in pin or "ruolo != 'admin'" in pin
    assert "_retry_ha_assets" in main
    assert "tengo locale" in main
    timer = Path(__file__).resolve().parents[1] / "systemd" / "videocitofono-kiosk-guard.timer"
    assert timer.is_file()
    inst = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"
    assert "videocitofono-kiosk-guard.timer" in inst.read_text(encoding="utf-8")
    nfcov = (Path(__file__).resolve().parents[1] / "scripts" / "set_nfc_override.py").read_text()
    assert 'if "enabled" not in nfc' in nfcov
    via = (Path(__file__).resolve().parents[1] / "scripts" / "deploy-via-ha.sh").read_text()
    assert "SKIP_APT=1" in via
    assert "SKIP_PIP_UPGRADE=1" in via
    assert "mosquitto_pub" not in via


def test_motion_health_non_ok_se_camera_ko():
    from modules.motion_detector import (
        MotionDetector, MotionPicameraDetector, MotionSnapshotDetector,
    )

    class _Alive:
        def is_alive(self):
            return True

    p = MotionPicameraDetector()
    p._thread = _Alive()
    p._cam = None
    p._fail_streak = 5
    assert p.health_status("screensaver", expected_running=True) == "down"
    p._fail_streak = 0
    p._cam = object()
    assert p.health_status("screensaver", expected_running=True) == "ok"
    s = MotionSnapshotDetector(snapshot_url="http://127.0.0.1/missing")
    s._thread = _Alive()
    s._fail_count = 8
    assert s.health_status("screensaver", expected_running=True) == "down"
    m = MotionDetector(camera=None)
    assert m.health_status("home", expected_running=False) == "idle"
    assert m.health_status("screensaver", expected_running=True) == "down"
