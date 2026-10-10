#!/usr/bin/env python3
"""Se config.yaml non ha la chiave 'nfc', appende il blocco estratto da config.example.yaml.
   Non tocca il file se 'nfc' esiste già."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def extract_nfc_block(example_text: str) -> str | None:
    lines = example_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith("nfc:"):
            start = i
            break
    if start is None:
        return None
    chunk: list[str] = [lines[start]]
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            chunk.append(line)
            continue
        if not line[:1].isspace() and ":" in line:
            break
        chunk.append(line)
    return "".join(chunk).rstrip() + "\n"


def main() -> int:
    root = Path("/opt/videocitofono/app/config")
    cfg = root / "config.yaml"
    example = root / "config.example.yaml"
    if not cfg.is_file() or not example.is_file():
        return 0
    text = cfg.read_text(encoding="utf-8")
    if re.search(r"^nfc:\s*$", text, re.MULTILINE):
        return 0
    block = extract_nfc_block(example.read_text(encoding="utf-8"))
    if not block:
        print("merge_nfc: blocco nfc non trovato in config.example.yaml", file=sys.stderr)
        return 1
    cfg.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    print("merge_nfc: aggiunta sezione nfc da config.example.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
