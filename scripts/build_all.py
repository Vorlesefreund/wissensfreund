#!/usr/bin/env python3
"""
build_all.py — Ein-Befehl-Kette: Master rein → alle abgeleiteten Listen raus.

Reihenfolge (jeder Schritt liest den Master bzw. dessen Quellen):
  1. build_master.py               → catalog_review_master.xlsx (frisch; Hand-Edits via
                                     apply_master_annotations zurückgelesen)
  2. build_catalog_from_master.py  → catalog_full.json + catalog_reserve.json
                                     (OHNE catalog_review.xlsx-Nebeneffekt)
  3. build_eignung_exclude.py      → eignung_exclude.json
  4. build_ergiebigkeit_scores.py  → ergiebigkeit_scores.json
  5. build_production_status.py    → Sheet "Produktion" im Master

Der Master ist Wahrheitsquelle; alles andere ist Ableitung. Master darf nicht in Excel
offen sein.

Aufruf: python -X utf8 scripts/build_all.py
"""

import pathlib
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO    = pathlib.Path(__file__).parent.parent
SCRIPTS = REPO / "scripts"
MASTER  = REPO / "catalog_review_master.xlsx"

# (Beschreibung, Skriptpfad) — Reihenfolge ist bindend
STEPS = [
    ("Master bauen",             SCRIPTS / "build_master.py"),
    ("catalog_full/reserve",     SCRIPTS / "build_catalog_from_master.py"),
    ("eignung_exclude",          REPO / "build_eignung_exclude.py"),
    ("ergiebigkeit_scores",      REPO / "build_ergiebigkeit_scores.py"),
    ("Produktions-Status",       SCRIPTS / "build_production_status.py"),
]


def main() -> None:
    lock = MASTER.parent / f"~${MASTER.name}"
    if lock.exists():
        sys.exit(f"Master ist in Excel geoeffnet ({lock.name}) — bitte schliessen und erneut ausfuehren.")

    for i, (desc, script) in enumerate(STEPS, 1):
        if not script.exists():
            sys.exit(f"FEHLT: {script}")
        print(f"\n{'='*70}\n[{i}/{len(STEPS)}] {desc}  ({script.name})\n{'='*70}")
        r = subprocess.run([sys.executable, "-X", "utf8", str(script)], cwd=str(REPO))
        if r.returncode != 0:
            sys.exit(f"\n✗ ABBRUCH bei Schritt {i} ({desc}) — Exit {r.returncode}.")

    print(f"\n{'='*70}\n✓ build_all fertig — Master + alle abgeleiteten Listen aktuell.\n{'='*70}")


if __name__ == "__main__":
    main()
