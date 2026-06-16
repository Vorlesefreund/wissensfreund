#!/usr/bin/env python3
"""
catalog_rater_anker2.py  v1  (2026-06-16)
──────────────────────────────────────────────────────────────────────────────
Mini-Rater für 6 Themen mit erg-Lücken.
Der Rater füllt fehlende erg-Werte und prüft age_floor für sensible Themen.

Output: catalog_raw_anker2/<gebiet>.json
"""

import anthropic, json, pathlib, re, sys, time, argparse

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT     = pathlib.Path(__file__).parent
SYSTEM_PROMPT = REPO_ROOT / "wissensfreund_rater_kuratierung_v2.md"
ANCHOR_XLSX   = REPO_ROOT / "wortziele_ergiebigkeit_134_v2.xlsx"
OUT_DIR       = REPO_ROOT / "catalog_raw_anker2"

MODEL       = "claude-opus-4-8"
MAX_TOKENS  = 8000
RETRY_DELAYS = [15, 45, 120]

REQUIRED_FIELDS = {
    "thema", "themengebiet", "leuchtturm",
    "erg_s1", "erg_s2", "erg_s3",
    "eignung", "age_floor", "kategorie_nr",
    "framing_note", "sensibel", "begruendung_eignung",
    "dublette_von", "notiz",
}

# 6 Themen mit bekannten Lücken
# (thema, themengebiet, bekannte_erg, age_floor_hint, anmerkung_fuer_rater)
THEMEN = [
    ("Märtyrer",          "Religion, Feste & Bräuche",
     "erg_s1=?, erg_s2=4, erg_s3=6",
     "age_floor=1 (prüfen)", "Religiöses Thema, aber bildungsrelevant."),
    ("Beschneidung",      "Religion, Feste & Bräuche",
     "erg_s1=?, erg_s2=?, erg_s3=5",
     "age_floor=S2 oder S3 prüfen", "Körperliches Ritual. Prüfe ob age_floor=S3 (Kat 2/6)."),
    ("Orientierungslauf", "Sport & Spiele",
     "erg_s1=?, erg_s2=5, erg_s3=6",
     "age_floor=1", "Sportart, unproblematisch."),
    ("Inflation",         "Gesellschaft, Berufe & Zusammenleben",
     "erg_s1=?, erg_s2=4, erg_s3=7",
     "age_floor=1 oder S2", "Wirtschaftskonzept. Prüfe Alterseignung für S1."),
    ("Holocaust-Mahnmal", "Weltstädte & Wahrzeichen",
     "erg_s1=?, erg_s2=?, erg_s3=7",
     "age_floor=S3 (Kat 4 NS)", "NS-Kontext → Kat 4, age_floor=S3 sehr wahrscheinlich korrekt."),
    ("Bonnie und Clyde",  "Berühmte Personen",
     "erg_s1=?, erg_s2=?, erg_s3=7",
     "age_floor=S2 oder S3", "Kriminelle, Gewalt → Kat 8. Prüfe ob S2 oder S3."),
]


def area_slug(gebiet: str) -> str:
    s = gebiet.lower()
    for src, dst in [("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def load_system_prompt() -> str:
    return SYSTEM_PROMPT.read_text(encoding="utf-8")


def load_anchor_table() -> str:
    import openpyxl
    wb = openpyxl.load_workbook(ANCHOR_XLSX, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    raw_hdr = [str(v).strip().lower() if v else "" for v in rows[0]]
    def find(must, must_not=None):
        for i, h in enumerate(raw_hdr):
            if all(k in h for k in must):
                if must_not and any(k in h for k in must_not): continue
                return i
        return -1
    idx = {
        "thema": find(["thema"]),
        "s1":    find(["s1"]),
        "s2":    find(["s2"]),
        "s3":    find(["s3"]),
    }
    if idx["s1"] < 0: idx["s1"] = find(["ergiebigkeit"], ["s2","s3","2","3"])
    if idx["s2"] < 0: idx["s2"] = find(["ergiebigkeit","2"], ["s1","s3","1","3"])
    if idx["s3"] < 0: idx["s3"] = find(["ergiebigkeit","3"], ["s1","s2","1","2"])
    lines = [f"{'Thema':<32} {'S1':>3} {'S2':>3} {'S3':>3}", "─"*44]
    for row in rows[1:]:
        t = row[idx["thema"]]
        if not t: continue
        def fmt(v): return str(int(v)) if isinstance(v,(int,float)) else (str(v) if v else "—")
        lines.append(f"{str(t):<32} {fmt(row[idx['s1']]):>3} {fmt(row[idx['s2']]):>3} {fmt(row[idx['s3']]):>3}")
    return "\n".join(lines)


def extract_json(raw: str) -> list[dict] | None:
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r'„([^"]*?)"', r"'\1'", text)
    text = text.strip()
    try:
        d = json.loads(text)
        return d if isinstance(d, list) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return d if isinstance(d, list) else None
        except json.JSONDecodeError:
            pass
    return None


def call_api(client, system: str, user: str) -> str:
    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    Retry {attempt} — warte {delay}s …", flush=True)
            time.sleep(delay)
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if resp.stop_reason == "end_turn":
                return resp.content[0].text
            if hasattr(resp, "type") and resp.type == "overloaded_error":
                raise RuntimeError("overloaded_error")
            return resp.content[0].text
        except Exception as e:
            last_exc = e
            print(f"    API-Fehler: {e}", flush=True)
    raise RuntimeError(f"API nach {len(RETRY_DELAYS)+1} Versuchen: {last_exc}")


def build_user_msg(anchor_table: str) -> str:
    lines = [
        "## Aufgabe: Ergiebigkeits-Lücken schließen",
        "",
        "Bewerte NUR diese 6 Themen. Fülle fehlende erg-Werte und prüfe eignung/age_floor.",
        "Besondere Hinweise:",
        "- Beschneidung: prüfe ob age_floor=S3 (Kat 2 Körper/Ritual oder Kat 6 Religion).",
        "  Falls S3 → erg_s1=null, erg_s2=null.",
        "- Holocaust-Mahnmal: Kat 4 (NS-Kontext), age_floor=S3 sehr wahrscheinlich korrekt.",
        "  Falls S3 → erg_s1=null, erg_s2=null.",
        "- Bonnie und Clyde: Kat 8 (Gewalt/Kriminalität). Prüfe ob S2 oder S3 angemessen.",
        "- Inflation: prüfe ob S1-Kinder das Konzept verstehen können (Ergiebigkeit für S1?).",
        "- Märtyrer: religiöses Thema, af=1 ok wenn sachlich — fülle erg_s1.",
        "- Orientierungslauf: Sportart, af=1, fülle erg_s1.",
        "",
        "Ausgabe: JSON-Array mit genau 6 Objekten (vollständiges Schema, alle Felder).",
        "Stufen unter age_floor → erg_s* = null.",
        "",
        "## Themen:",
    ]
    for thema, gebiet, bekannte_erg, af_hint, anm in THEMEN:
        lines.append(f"- **{thema}** (Gebiet: {gebiet})")
        lines.append(f"  Bekannte erg: {bekannte_erg} | age_floor-Hinweis: {af_hint}")
        lines.append(f"  Anmerkung: {anm}")
    lines += [
        "",
        "## Kalibrierungs-Anker (134 Themen):",
        anchor_table,
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    print("Lade System-Prompt + Anker …")
    system = load_system_prompt()
    anchor_table = load_anchor_table()
    user_msg = build_user_msg(anchor_table)

    if args.dry_run:
        print("DRY-RUN: User-Message:")
        print(user_msg[:800], "…")
        return

    client = anthropic.Anthropic()
    print(f"Rufe {MODEL} für 6 Themen …", flush=True)
    raw = call_api(client, system, user_msg)

    data = extract_json(raw)
    if not data:
        raw_path = OUT_DIR / "_raw_anker2.txt"
        raw_path.write_text(raw, encoding="utf-8")
        print(f"FEHLER: JSON-Parse fehlgeschlagen. Raw gespeichert: {raw_path}")
        return

    print(f"  {len(data)} Themen erhalten.")

    # Defaults setzen
    for item in data:
        item.setdefault("tier", "primary")
        item.setdefault("eignung", "include")
        item.setdefault("leuchtturm", False)
        item.setdefault("dublette_von", None)
        item.setdefault("notiz", "")

    # Validierung
    expected = {t for t, *_ in THEMEN}
    rated = {item.get("thema", "") for item in data}
    missing = expected - rated
    if missing:
        print(f"  WARNUNG: Fehlende Themen im Output: {missing}")

    for item in data:
        issues = REQUIRED_FIELDS - set(item.keys())
        if issues:
            print(f"  WARNUNG [{item.get('thema')}]: fehlende Felder: {sorted(issues)}")

    # Ausgabe anzeigen
    print()
    print(f"{'Thema':<28} {'af':>3} {'s1':>4} {'s2':>4} {'s3':>4}  eignung    sensibel")
    print("─" * 75)
    for item in data:
        print(
            f"  {item.get('thema',''):<26} {str(item.get('age_floor') or 1):>3}"
            f" {str(item.get('erg_s1') or '—'):>4} {str(item.get('erg_s2') or '—'):>4}"
            f" {str(item.get('erg_s3') or '—'):>4}  {item.get('eignung',''):10}"
            f"  {item.get('sensibel','')}"
        )

    # Nach Themengebiet speichern
    by_gebiet: dict[str, list] = {}
    for item in data:
        g = item.get("themengebiet", "unbekannt")
        by_gebiet.setdefault(g, []).append(item)

    saved = []
    for gebiet, items in by_gebiet.items():
        slug = area_slug(gebiet)
        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        saved.append(f"{out_path.name} ({len(items)} Themen)")

    # Auch als Gesamtdatei
    all_path = OUT_DIR / "alle_anker2.json"
    all_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nGespeichert: {', '.join(saved)}")
    print(f"Gesamt: {all_path.name}")


if __name__ == "__main__":
    main()
