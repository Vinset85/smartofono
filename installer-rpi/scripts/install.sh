#!/usr/bin/env bash
# Installer applicazione Videocitofono su Raspberry Pi 5 (Bookworm).
# Da eseguire come utente vinset (non root). Userà sudo dove serve.
set -euo pipefail

APP_USER="${APP_USER:-vinset}"
APP_ROOT="${APP_ROOT:-/opt/videocitofono}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installazione Videocitofono in $APP_ROOT (utente $APP_USER)"

echo "--> Pacchetti di sistema"
if [[ "${SKIP_APT:-0}" == "1" ]]; then
    echo "    skip apt-get (SKIP_APT=1)"
else
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip python3-dev \
        build-essential pkg-config \
        libmtdev-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
        libgl1 libgles2 libgstreamer1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
        fonts-dejavu fonts-noto-color-emoji fonts-symbola \
        python3-picamera2 python3-opencv python3-numpy python3-lgpio \
        libusb-1.0-0 \
        xwayland grim wlr-randr \
        git rsync
fi

echo "--> Creazione cartelle"
sudo mkdir -p "$APP_ROOT"
sudo chown -R "$APP_USER:$APP_USER" "$APP_ROOT"

echo "--> Copia applicazione"
# Non sovrascrivere config.yaml gia' personalizzato sul Pi
rsync -a --delete --exclude='__pycache__' --exclude='data/' \
    --exclude='config/config.yaml' \
    --exclude='config/config.override.yaml' \
    "$REPO_ROOT/app/" "$APP_ROOT/app/"

echo "--> Asset bundled (icone accesso, placeholder)"
mkdir -p "$APP_ROOT/app/assets/avatars"
rsync -a "$REPO_ROOT/app/assets/" "$APP_ROOT/app/assets/"

echo "--> Virtualenv (con accesso ai pacchetti di sistema per picamera2)"
if [ ! -d "$APP_ROOT/venv" ]; then
    python3 -m venv --system-site-packages "$APP_ROOT/venv"
fi
if [[ "${SKIP_PIP_UPGRADE:-0}" != "1" ]]; then
    "$APP_ROOT/venv/bin/pip" install --upgrade pip wheel setuptools
fi
"$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/app/requirements.txt"

echo "--> Generazione asset placeholder"
"$APP_ROOT/venv/bin/python3" "$REPO_ROOT/scripts/genera_assets.py" || true
rsync -a "$REPO_ROOT/app/assets/" "$APP_ROOT/app/assets/"

echo "--> Config (se manca, copia example)"
if [ ! -f "$APP_ROOT/app/config/config.yaml" ]; then
    cp "$APP_ROOT/app/config/config.example.yaml" "$APP_ROOT/app/config/config.yaml"
    echo "    Modificare $APP_ROOT/app/config/config.yaml prima dell'avvio."
fi
rm -f "$APP_ROOT/app/assets/avatars/icons8-fingerprint-100.png"
"$APP_ROOT/venv/bin/python3" - <<'PY' || true
import yaml
from pathlib import Path
root = Path("/opt/videocitofono/app/config")
for name in ("config.yaml", "config.override.yaml"):
    p = root / name
    if not p.is_file():
        continue
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    changed = False
    if "fingerprint" in data:
        data.pop("fingerprint", None)
        changed = True
    icons = data.get("access_icons")
    if isinstance(icons, dict) and "fingerprint" in icons:
        icons.pop("fingerprint", None)
        changed = True
    if changed:
        p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("removed fingerprint from", p)
PY

echo "--> udev rule per controllo backlight da utente non root"
sudo tee /etc/udev/rules.d/99-backlight.rules >/dev/null <<'EOF'
SUBSYSTEM=="backlight", ACTION=="add", \
    RUN+="/bin/sh -c 'chgrp video /sys/class/backlight/%k/brightness && chmod g+w /sys/class/backlight/%k/brightness'"
EOF
sudo udevadm control --reload-rules || true
sudo udevadm trigger --action=add --subsystem-match=backlight || true
sudo usermod -aG video "$APP_USER" || true
# GPIO relè apertura (gpiochip / pinctrl) e seriale USB NFC
sudo usermod -aG gpio "$APP_USER" || true
sudo usermod -aG dialout "$APP_USER" || true
if [ -f "$REPO_ROOT/scripts/udev-nfc-ch340.rules" ]; then
    sudo cp "$REPO_ROOT/scripts/udev-nfc-ch340.rules" \
        /etc/udev/rules.d/99-videocitofono-nfc-ch340.rules
    sudo udevadm control --reload-rules || true
    sudo udevadm trigger --subsystem-match=tty || true
fi

echo "--> Modalità kiosk: rimuovi desktop pcmanfm/wf-panel-pi dal labwc autostart (sistema)"
# IMPORTANTE: labwc legge autostart sia da /etc/xdg/labwc/autostart sia da
# ~/.config/labwc/autostart. Su RPi OS Bookworm il primo lancia pcmanfm (desktop)
# e wf-panel-pi (taskbar), che sovrappongono l'app Kivy.
# Patchamo il file di sistema (con backup) per ottenere kiosk-only.
KIOSK_AUTOSTART="/etc/xdg/labwc/autostart"
if [ -f "$KIOSK_AUTOSTART" ] && ! grep -q 'Videocitofono kiosk' "$KIOSK_AUTOSTART"; then
    sudo cp "$KIOSK_AUTOSTART" "$KIOSK_AUTOSTART.orig.bak"
    echo "    Backup -> $KIOSK_AUTOSTART.orig.bak"
fi
sudo tee "$KIOSK_AUTOSTART" >/dev/null <<'EOF'
# Videocitofono kiosk: niente desktop manager, niente panel.
# L'app videocitofono parte come servizio systemd su DISPLAY=:0 (XWayland).
/usr/bin/kanshi &
/usr/bin/lxsession-xdg-autostart
EOF
echo "    Patched $KIOSK_AUTOSTART"

# Anche autostart utente (kiosk minimal, niente desktop)
mkdir -p /home/"$APP_USER"/.config/labwc
cat > /home/"$APP_USER"/.config/labwc/autostart <<'EOF'
# Kiosk videocitofono - nessun desktop, no panel
/usr/bin/kanshi &
EOF
chown "$APP_USER:$APP_USER" /home/"$APP_USER"/.config/labwc/autostart

echo "--> Termina eventuali pcmanfm/wf-panel-pi residui (no-op se assenti)"
sudo pkill -9 -f 'lwrespawn.*pcmanfm' 2>/dev/null || true
sudo pkill -9 -f 'lwrespawn.*wf-panel' 2>/dev/null || true
sudo pkill -9 pcmanfm 2>/dev/null || true
sudo pkill -9 wf-panel-pi 2>/dev/null || true

echo "--> Disabilita screen blanking / DPMS automatico"
mkdir -p /home/"$APP_USER"/.config/labwc
if [ ! -f /home/"$APP_USER"/.config/labwc/environment ] || \
   ! grep -q 'WLR_NO_HARDWARE_CURSORS' /home/"$APP_USER"/.config/labwc/environment; then
    cat >> /home/"$APP_USER"/.config/labwc/environment <<'EOF'

# Videocitofono: no DPMS auto (gestiamo lo screen-saver lato app)
WLR_NO_HARDWARE_CURSORS=1
EOF
    chown "$APP_USER:$APP_USER" /home/"$APP_USER"/.config/labwc/environment
fi

echo "--> Script reset USB lettore NFC (CH340) e attesa display kiosk"
sudo mkdir -p "$APP_ROOT/scripts"
sudo install -m 0755 "$REPO_ROOT/scripts/nfc-usb-reset.sh" \
    "$APP_ROOT/scripts/nfc-usb-reset.sh"
sudo install -m 0755 "$REPO_ROOT/scripts/wait-kiosk-display.sh" \
    "$APP_ROOT/scripts/wait-kiosk-display.sh"
sudo install -m 0755 "$REPO_ROOT/scripts/kiosk-ensure-session.sh" \
    "$APP_ROOT/scripts/kiosk-ensure-session.sh"

echo "--> LightDM: autologin immediato (niente timeout greeter)"
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo tee /etc/lightdm/lightdm.conf.d/99-videocitofono-kiosk.conf >/dev/null <<EOF
[Seat:*]
autologin-user=$APP_USER
autologin-user-timeout=0
EOF

echo "--> Sudoers: consenti all'app di restartare se stessa e rebootare l'RPi via MQTT"
sudo tee /etc/sudoers.d/videocitofono >/dev/null <<EOF
# Consenti a $APP_USER di riavviare il service e l'RPi senza password (cmd via MQTT)
$APP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart videocitofono.service
$APP_USER ALL=(ALL) NOPASSWD: /bin/systemctl stop go2rtc.service
$APP_USER ALL=(ALL) NOPASSWD: /bin/systemctl start go2rtc.service
$APP_USER ALL=(ALL) NOPASSWD: /sbin/reboot
$APP_USER ALL=(ALL) NOPASSWD: $APP_ROOT/scripts/nfc-usb-reset.sh
EOF
sudo chmod 0440 /etc/sudoers.d/videocitofono

echo "--> Script utilità (restore defaults config)"
sudo mkdir -p "$APP_ROOT/scripts"
sudo install -m 0755 "$REPO_ROOT/scripts/restore_config_defaults.py" \
    "$APP_ROOT/scripts/restore_config_defaults.py"
sudo chown "$APP_USER:$APP_USER" "$APP_ROOT/scripts/restore_config_defaults.py"

echo "--> Ripristino config di default da config.example.yaml"
"$APP_ROOT/venv/bin/python3" "$APP_ROOT/scripts/restore_config_defaults.py" || true

echo "--> Tune termico (servizi non necessari, go2rtc on-demand)"
sudo install -m 0755 "$REPO_ROOT/scripts/tune-system-thermal.sh" \
    "$APP_ROOT/scripts/tune-system-thermal.sh"
sudo "$APP_ROOT/scripts/tune-system-thermal.sh" || true

echo "--> Face recognition deps (ArcFace + liveness)"
sudo install -m 0755 "$REPO_ROOT/scripts/install-face-deps.sh" \
    "$APP_ROOT/scripts/install-face-deps.sh"
sudo env SKIP_APT="${SKIP_APT:-0}" FACE_UPGRADE="${FACE_UPGRADE:-0}" \
    "$APP_ROOT/scripts/install-face-deps.sh" || echo "    WARN: face deps parziali"

echo "--> Config Mosquitto e go2rtc (per setup-mqtt-auth e motion snapshot)"
sudo mkdir -p "$APP_ROOT/config"
sudo install -m 0644 "$REPO_ROOT/config/mosquitto-videocitofono.conf" \
    "$APP_ROOT/config/mosquitto-videocitofono.conf"
sudo install -m 0644 "$REPO_ROOT/config/go2rtc.yaml" \
    "$APP_ROOT/config/go2rtc.yaml"
sudo chown -R "$APP_USER:$APP_USER" "$APP_ROOT/config"

echo "--> MQTT auth (opzionale: sudo setup-mqtt-auth.sh)"
if [[ -f "$REPO_ROOT/scripts/setup-mqtt-auth.sh" ]]; then
  sudo install -m 0755 "$REPO_ROOT/scripts/setup-mqtt-auth.sh" \
      "$APP_ROOT/scripts/setup-mqtt-auth.sh"
fi

echo "--> Installazione service systemd"
sudo install -m 0644 "$REPO_ROOT/systemd/videocitofono.service" \
    /etc/systemd/system/videocitofono.service
sudo install -m 0644 "$REPO_ROOT/systemd/videocitofono-nfc-prep.service" \
    /etc/systemd/system/videocitofono-nfc-prep.service
sudo install -m 0644 "$REPO_ROOT/systemd/videocitofono-kiosk-guard.service" \
    /etc/systemd/system/videocitofono-kiosk-guard.service
sudo systemctl daemon-reload
# Prep NFC non abilitato di default (evita conflitti con touch USB interno).
sudo systemctl disable videocitofono-nfc-prep.service 2>/dev/null || true
sudo systemctl enable videocitofono.service
sudo systemctl enable videocitofono-kiosk-guard.service
# Raspberry Pi Connect/WayVNC non serve in kiosk e al boot fallisce.
sudo systemctl disable --now rpi-connect.service rpi-connect-wayvnc.service \
    rpi-connect-signin.service 2>/dev/null || true

cat <<EOF

============================================================
 Installazione completata.

 Prossimi passi:
   1. Modifica config:   $APP_ROOT/app/config/config.yaml
   2. Test manuale:      $APP_ROOT/venv/bin/python3 $APP_ROOT/app/main.py
   3. Avvia service:     sudo systemctl start videocitofono.service
   4. Log:               journalctl -u videocitofono -f

 Variabili LiveKit (editabili in /etc/systemd/system/videocitofono.service):
   VC_LK_TOKEN_URL  -> token issuer (default http://192.168.1.160:8081/token)
   VC_LK_WS_URL     -> signaling   (default ws://192.168.1.160:7880)
   VC_LK_PUBLISH    -> 1 abilita publish camera+mic LiveKit dal Pi
                       (default 0 finche' go2rtc-pi tiene il sensore)

 Pacchetto Python required (gia' in app/requirements.txt):
   livekit-rtc>=1.1.0
============================================================
EOF
