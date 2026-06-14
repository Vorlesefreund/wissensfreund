#!/usr/bin/env python3
"""
catalog_verdicts_parser.py  v1  (2026-06-14)
Liest catalog_review_master.xlsx und erzeugt:
  eignung_verdicts.json   — Laufzeit-Lookup für die Artikel-Pipeline
  categories_backlog.json — "auch Gebiet"-Notizen für späteres categories-Array

Verdicts-Logik:
  eignung=exclude         → exclude: true  (+ merge_into aus Kommentar-Spalte)
  age_floor > 1           → age_floor gesetzt
  framing_note nicht leer → framing_note gesetzt
  FREIGABE nicht leer     → reviewed: true
  Alles Default           → kein Eintrag (Pipeline-Default = include/age_floor=1)
"""
import json, pathlib, re
import openpyxl

REPO_ROOT      = pathlib.Path(__file__).parent
MASTER_XLSX    = REPO_ROOT / "catalog_review_master.xlsx"
OUT_VERDICTS   = REPO_ROOT / "eignung_verdicts.json"
OUT_CATEGORIES = REPO_ROOT / "categories_backlog.json"

AGE_FLOOR_MAP = {"S1": 1, "1": 1, "S2": 2, "2": 2, "S3": 3, "3": 3}

def parse_age_floor(val: str) -> int:
    return AGE_FLOOR_MAP.get(str(val).strip().upper(), 1)

def main():
    if not MASTER_XLSX.exists():
        raise FileNotFoundError(f"Nicht gefunden: {MASTER_XLSX}")

    wb = openpyxl.load_workbook(MASTER_XLSX, data_only=True, read_only=True)
    ws = wb["Review"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    headers = [str(h).strip() if h else "" for h in rows[0]]
    col = {h: i for i, h in enumerate(headers) if h}

    verdicts: dict[str, dict] = {}
    categories_backlog: dict[str, list[str]] = {}
    stats = {"total": 0, "exclude": 0, "age_floor": 0,
             "framing": 0, "reviewed": 0, "backlog": 0}

    for row in rows[1:]:
        def v(field: str) -> str:
            idx = col.get(field)
            return str(row[idx]).strip() if idx is not None and row[idx] is not None else ""

        thema = v("thema")
        if not thema or thema == "nan":
            continue
        stats["total"] += 1

        eignung    = v("eignung")
        age_floor  = parse_age_floor(v("age_floor"))
        framing    = v("framing_note")
        freigabe   = v("FREIGABE")
        notiz      = v("notiz")
        kommentar  = v("Kommentar") if "Kommentar" in col else ""

        entry: dict = {}

        if eignung == "exclude":
            entry["exclude"] = True
            if kommentar:
                entry["merge_into"] = kommentar
            stats["exclude"] += 1

        if age_floor > 1:
            entry["age_floor"] = age_floor
            stats["age_floor"] += 1

        if framing:
            entry["framing_note"] = framing
            stats["framing"] += 1

        if freigabe:
            entry["reviewed"] = True
            stats["reviewed"] += 1

        if entry:
            verdicts[thema] = entry

        # "auch Gebiet"-Notizen → categories_backlog
        auch_gebiete = re.findall(r"auch Gebiet\s+([^;,\n]+)", notiz, re.IGNORECASE)
        if auch_gebiete:
            categories_backlog[thema] = [g.strip() for g in auch_gebiete]
            stats["backlog"] += 1

    OUT_VERDICTS.write_text(
        json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUT_CATEGORIES.write_text(
        json.dumps(categories_backlog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"eignung_verdicts.json:   {len(verdicts)} Einträge")
    print(f"  davon exclude:         {stats['exclude']}")
    print(f"  davon age_floor>1:     {stats['age_floor']}")
    print(f"  davon framing_note:    {stats['framing']}")
    print(f"  davon reviewed:        {stats['reviewed']}")
    print(f"categories_backlog.json: {stats['backlog']} Themen mit auch-Gebiet-Notizen")

if __name__ == "__main__":
    main()
