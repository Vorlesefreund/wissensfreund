#!/usr/bin/env python3
r"""watch_review_folders.py — Ordner-Watcher für Review-Docx.

Prüft alle 30 s die zwei Desktop-Ordner
  …\Desktop\wissensfreund_approved\
  …\Desktop\wissensfreund_changes\
auf neue .docx-Dateien. Für jede neue Datei wird
scripts/process_review_docx.py aufgerufen. Erfolgreich verarbeitete Dateien
wandern in den Unterordner processed/.

Aufruf:  python scripts/watch_review_folders.py   (Strg+C zum Beenden)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DESKTOP      = Path(r"C:\Users\Andreas\Desktop")
APPROVED_DIR = DESKTOP / "wissensfreund_approved"
CHANGES_DIR  = DESKTOP / "wissensfreund_changes"
WATCH_DIRS   = [APPROVED_DIR, CHANGES_DIR]
INTERVAL_S   = 30
PROCESSOR    = ROOT / "scripts" / "process_review_docx.py"


def _ensure_dirs() -> None:
    for d in WATCH_DIRS:
        (d / "processed").mkdir(parents=True, exist_ok=True)


def _new_docx(folder: Path) -> list[Path]:
    """Unverarbeitete .docx (ohne Word-Lock ~$, nicht im processed/)."""
    out = []
    for f in sorted(folder.glob("*.docx")):
        if f.name.startswith("~$"):
            continue
        out.append(f)
    return out


def _process(docx: Path) -> bool:
    print(f"  → verarbeite {docx.name} …")
    cmd = [sys.executable, str(PROCESSOR), str(docx)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout:
        print("\n".join("    " + ln for ln in r.stdout.rstrip().splitlines()))
    if r.returncode != 0:
        print(f"  ✗ Fehler (Exit {r.returncode}):")
        if r.stderr:
            print("\n".join("    " + ln for ln in r.stderr.rstrip().splitlines()))
        return False
    return True


def _archive(docx: Path) -> None:
    dest = docx.parent / "processed" / docx.name
    if dest.exists():
        stem, suf = docx.stem, docx.suffix
        n = 2
        while (docx.parent / "processed" / f"{stem}_{n}{suf}").exists():
            n += 1
        dest = docx.parent / "processed" / f"{stem}_{n}{suf}"
    docx.replace(dest)
    print(f"  ✓ verschoben → processed/{dest.name}")


def main() -> int:
    _ensure_dirs()
    print("watch_review_folders aktiv (Strg+C beendet).")
    print(f"  approved: {APPROVED_DIR}")
    print(f"  changes:  {CHANGES_DIR}")
    print(f"  Intervall: {INTERVAL_S}s\n")
    try:
        while True:
            for folder in WATCH_DIRS:
                for docx in _new_docx(folder):
                    print(f"[{folder.name}] neue Datei: {docx.name}")
                    if _process(docx):
                        _archive(docx)
                    else:
                        print(f"  (bleibt liegen für erneuten Versuch: {docx.name})")
            time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        print("\nbeendet.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
