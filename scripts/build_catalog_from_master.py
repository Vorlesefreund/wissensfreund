#!/usr/bin/env python3
"""
build_catalog_from_master.py — Erzeugt catalog_full.json + catalog_reserve.json aus dem
Master als Entscheidungsquelle, OHNE catalog_review.xlsx neu zu schreiben.

Ersetzt catalog_merge.main() als reiner Produktionslisten-Bauer. Nutzt exakt dieselben,
getesteten catalog_merge-Schritte:
    load_all → dedup → apply_master_annotations → apply_themengebiete_annotations
    → assign_ranks → export_json
NUR ohne den export_xlsx-Nebeneffekt, der zuvor das (inzwischen archivierte)
catalog_review.xlsx neu anlegte.

load_existing_annotations() liest intern bevorzugt catalog_review_master.xlsx — die
Include/Exclude/erg-Entscheidungen aus dem Master (inkl. Andreas' Hand-Edits) landen also
korrekt in catalog_full.json.

Aufruf: python -X utf8 scripts/build_catalog_from_master.py
"""

import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
import catalog_merge as cm  # noqa: E402


def main() -> None:
    print("1. Lade + dedup …")
    all_items = cm.load_all()
    canonical, duplicates = cm.dedup(all_items)
    print(f"   {len(duplicates)} Dubletten → {len(canonical)} eindeutige Themen")

    print("2. Master-Annotierungen (Entscheidungsquelle) …")
    master_ann = cm.load_existing_annotations(cm.OUT_XLSX)  # bevorzugt intern die Master-Datei
    n_ann = cm.apply_master_annotations(canonical, master_ann)
    n_tg = cm.apply_themengebiete_annotations(canonical)
    print(f"   {n_ann} Master-Overrides | {n_tg} Themengebiete-Listen")

    print("3. Produktions-Reihenfolge …")
    primary, reserve = cm.assign_ranks(canonical)
    n_excl = sum(1 for x in canonical if x.get("eignung") == "exclude")

    print("4. Exportiere JSON (KEIN xlsx) …")
    cm.export_json(primary, reserve)
    print(f"   {len(primary)} primary | {len(reserve)} reserve | {n_excl} exclude (nicht in catalog_full)")
    print("   catalog_review.xlsx NICHT berührt — Master bleibt Wahrheitsquelle.")


if __name__ == "__main__":
    main()
