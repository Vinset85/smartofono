#!/usr/bin/env python3
"""Genera placeholder PNG (avatar default + camera offline) usando Pillow.
Eseguito una volta da install.sh, oppure manualmente."""
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow non installato. Installa con: pip install Pillow")
    raise SystemExit(1)

ASSETS = Path(__file__).resolve().parents[1] / "app" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
(ASSETS / "avatars").mkdir(parents=True, exist_ok=True)


def main() -> None:
    cam = ASSETS / "placeholder_camera.png"
    if not cam.exists():
        img = Image.new("RGB", (640, 480), (10, 12, 18))
        d = ImageDraw.Draw(img)
        d.text((220, 230), "Camera offline", fill=(120, 130, 145))
        img.save(cam)
        print(f"creato {cam}")

    avatar = ASSETS / "avatars" / "default.png"
    if not avatar.exists():
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, 124, 124], fill=(40, 55, 75, 255))
        d.ellipse([46, 30, 82, 66], fill=(160, 170, 185, 255))
        d.ellipse([22, 72, 106, 140], fill=(160, 170, 185, 255))
        img.save(avatar)
        print(f"creato {avatar}")


if __name__ == "__main__":
    main()
