#!/usr/bin/env python3
"""
catalog_rater_anker.py  v1  (2026-06-16)
──────────────────────────────────────────────────────────────────────────────
Finale Anker-Nachträge: 27 fehlende Grundstock-Themen bewerten.
Ergiebigkeit kommt aus wortziele_ergiebigkeit_134_v2.xlsx (kalibriert, gesperrt).
Rater bewertet NUR: eignung / age_floor / kategorie_nr / framing_note /
sensibel / begruendung_eignung / leuchtturm / notiz / themengebiet.

Output: catalog_raw_anker/<gebiet>.json  (ein File pro Themengebiet)
Resume-fähig: vorhandene .json werden übersprungen.

Nutzung:
  python catalog_rater_anker.py            # alle 27 Themen (1 Opus-Call)
  python catalog_rater_anker.py --dry-run  # kein API-Call
  python catalog_rater_anker.py --list     # Themen + erg-Werte anzeigen
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
ERG_JSON      = REPO_ROOT / "anker_ergiebigkeit.json"
OUT_DIR       = REPO_ROOT / "catalog_raw_anker"

MODEL         = "claude-opus-4-8"
MAX_TOKENS    = 24000
RETRY_DELAYS  = [15, 45, 120]

REQUIRED_FIELDS = {
    "thema", "themengebiet", "leuchtturm",
    "erg_s1", "erg_s2", "erg_s3",
    "eignung", "age_floor", "kategorie_nr",
    "framing_note", "sensibel", "begruendung_eignung",
    "dublette_von", "notiz",
}

# ── NACHTRAG-Liste (original → WP-Lemma, Themengebiet) ───────────────────────
# Format: (original_name_in_xlsx, wp_lemma_fuer_thema_feld, themengebiet_vorschlag)
NACHTRAG: list[tuple[str, str, str]] = [
    # Klare Anker-Lücken
    ("Mozart",                 "Wolfgang Amadeus Mozart",  "Kunst, Musik & Literatur"),
    ("Fossilien",              "Fossilien",                 "Naturwissenschaft & Biologie-Konzepte"),
    ("Waldbrand",              "Waldbrand",                 "Erde, Wetter & Naturphänomene"),
    ("Trojanischer Krieg",     "Trojanischer Krieg",        "Geschichte & Epochen"),
    ("Tell",                   "Wilhelm Tell",              "Geschichte & Epochen"),
    ("Humboldt",               "Alexander von Humboldt",    "Berühmte Personen"),
    ("Seefahrer",              "Seefahrer",                 "Geschichte & Epochen"),
    ("Pfeil und Bogen",        "Pfeil und Bogen",           "Geschichte & Epochen"),
    ("Tinte",                  "Tinte",                     "Grundbegriffe"),
    ("Wachs",                  "Wachs",                     "Grundbegriffe"),
    ("Vene",                   "Vene",                      "Menschlicher Körper & Gesundheit"),
    ("Wendekreis",             "Wendekreis",                "Erde, Wetter & Naturphänomene"),
    ("Persischer Golf",        "Persischer Golf",           "Naturräume & Landschaften"),
    ("Graz",                   "Graz",                      "Weltstädte & Wahrzeichen"),
    ("Graubünden",             "Graubünden",                "Länder & Kontinente"),
    ("Dänische Sprache",       "Dänische Sprache",          "Grundbegriffe"),
    ("Bundesrepublik Deutschland", "Bundesrepublik Deutschland", "Geschichte & Epochen"),
    ("Verbannung",             "Verbannung",                "Geschichte & Epochen"),
    # Vom Anfang verschollen
    ("Elefant",                "Elefant",                   "Tiere"),
    ("Indianer",               "Indianer",                  "Geschichte & Epochen"),
    # Grenzfälle (Andreas: JA)
    ("Zentripetalkraft",       "Zentripetalkraft",          "Naturwissenschaft & Biologie-Konzepte"),
    ("Lego",                   "Lego",                      "Kunst, Musik & Literatur"),
    ("VW",                     "Volkswagen",                "Technik, Maschinen & Fahrzeuge"),
    ("Looney Tunes",           "Looney Tunes",              "Kunst, Musik & Literatur"),
    ("Science Center",         "Science Center",            "Naturwissenschaft & Biologie-Konzepte"),
    ("Bunker",                 "Bunker",                    "Geschichte & Epochen"),
    ("Chaplin",                "Charlie Chaplin",           "Berühmte Personen"),
]


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def area_slug(gebiet: str) -> str:
    s = gebiet.lower()
    for src, dst in [("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT.exists():
        sys.exit(f"FEHLER: System-Prompt nicht gefunden: {SYSTEM_PROMPT}")
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
    count = 0
    for row in rows[1:]:
        t = row[idx["thema"]]
        if not t: continue
        def fmt(v): return str(int(v)) if isinstance(v,(int,float)) else (str(v) if v else "—")
        lines.append(f"{str(t):<32} {fmt(row[idx['s1']]):>3} {fmt(row[idx['s2']]):>3} {fmt(row[idx['s3']]):>3}")
        count += 1
    print(f"  {count} Anker geladen.")
    return "\n".join(lines)


def load_erg() -> dict:
    if not ERG_JSON.exists():
        sys.exit(f"FEHLER: {ERG_JSON} nicht gefunden. Zuerst Aufgabe 2 ausführen.")
    return json.loads(ERG_JSON.read_text(encoding="utf-8"))


def extract_json(raw: str) -> list[dict] | None:
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    # Fix gemischte typografische Anführungszeichen in Strings
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


def validate_items(data: list[dict], expected_n: int) -> list[str]:
    issues = []
    if len(data) != expected_n:
        issues.append(f"  Anzahl: erwartet {expected_n}, erhalten {len(data)}")
    for i, item in enumerate(data):
        name = item.get("thema", f"#{i}")
        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            issues.append(f"  [{name}] fehlende Felder: {sorted(missing)}")
    return issues


def call_api(client: anthropic.Anthropic, system: str, user: str, max_tokens: int) -> str:
    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    Retry {attempt}/{len(RETRY_DELAYS)} — warte {delay}s …", flush=True)
            time.sleep(delay)
        try:
            chunks: list[str] = []
            with client.messages.stream(
                model=MODEL, max_tokens=max_tokens,
                system=system, messages=[{"role":"user","content":user}],
            ) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
            return "".join(chunks)
        except anthropic.RateLimitError as e:
            print(f"    Rate-Limit: {e}"); last_exc = e
        except anthropic.APIStatusError as e:
            print(f"    API-Fehler {e.status_code}: {e.message}"); last_exc = e
            if e.status_code < 500: raise
    raise RuntimeError(f"Alle Retries erschöpft: {last_exc}")


# ── Haupt-Logik ───────────────────────────────────────────────────────────────

def build_user_message(items: list[dict], anchor_table: str) -> str:
    """
    items = Liste von {thema, themengebiet_vorschlag, erg_s1, erg_s2, erg_s3}
    """
    n = len(items)

    # Tabelle der Themen mit gesperrten erg-Werten
    zeilen = []
    for x in items:
        e1 = str(x['erg_s1']) if x['erg_s1'] is not None else "—"
        e2 = str(x['erg_s2']) if x['erg_s2'] is not None else "—"
        e3 = str(x['erg_s3']) if x['erg_s3'] is not None else "—"
        zeilen.append(f"  {x['thema']:<35} S1={e1} S2={e2} S3={e3}  [Gebiet-Vorschlag: {x['themengebiet_vorschlag']}]")
    themen_block = "\n".join(zeilen)

    return (
        f"Folgende {n} Themen sind finale Nachträge für den Wissensfreund-Katalog.\n"
        f"Die Ergiebigkeitswerte (erg_s1/s2/s3) sind bereits kalibriert und GESPERRT —\n"
        f"sie MÜSSEN exakt so ins JSON übernommen werden wie angegeben.\n\n"
        f"Themen mit gesperrten Ergiebigkeitswerten:\n"
        f"{themen_block}\n\n"
        f"Deine Aufgabe:\n"
        f"1. Übernimm erg_s1/s2/s3 EXAKT wie angegeben (nicht verändern!).\n"
        f"2. Weise das korrekte themengebiet zu (Vorschlag prüfen, ggf. korrigieren).\n"
        f"3. Bewerte: eignung, age_floor, kategorie_nr, framing_note, sensibel,\n"
        f"   begruendung_eignung, leuchtturm, notiz.\n"
        f"4. Leuchtturm=true nur für die offensichtlichsten Top-Themen (max. 2–3).\n"
        f"5. Schlage KEINE neuen Themen vor — nur diese {n} bewerten.\n"
        f"6. Alle {n} Themen müssen im JSON-Array erscheinen.\n\n"
        f"HINWEISE ZU EINZELNEN THEMEN:\n"
        f"- Indianer: historischer Begriff für indigene Völker Amerikas. Framing-Note nötig.\n"
        f"- Lego/Looney Tunes: Markennamen; Klexikon hat Artikel dazu → include.\n"
        f"- Science Center: Bildungsinstitution (Experimentierhäuser für Kinder).\n"
        f"- Bundesrepublik Deutschland: politische Staatsform — sachlich, Grundwissen.\n"
        f"- Verbannung: historisches/rechtliches Konzept (Exil, Verbannung als Strafe).\n\n"
        f"Anker-Tabelle (verbindliche Ergiebigkeits-Referenz — nur zur Einordnung):\n"
        f"{anchor_table}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Anker-Nachträge: 27 Themen mit gesperrter Ergiebigkeit bewerten",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "alle_nachtraege.json"
    out_raw  = OUT_DIR / "alle_nachtraege_raw.txt"

    # erg-Werte laden
    erg_map = load_erg()

    # Items zusammenstellen (mit Lemma-Korrektur + Anker-erg)
    items: list[dict] = []
    for orig, lemma, gebiet_vorschlag in NACHTRAG:
        e = erg_map.get(orig, {})
        items.append({
            "thema":               lemma,
            "thema_orig_in_xlsx":  orig,
            "themengebiet_vorschlag": gebiet_vorschlag,
            "erg_s1": e.get("erg_s1"),
            "erg_s2": e.get("erg_s2"),
            "erg_s3": e.get("erg_s3"),
            "hat_anker_erg": bool(e),
        })

    if args.list:
        print(f"{'Thema (Lemma)':<38} {'Orig':<28} {'S1':>3} {'S2':>3} {'S3':>3}")
        print("─"*78)
        for x in items:
            e1 = str(x['erg_s1']) if x['erg_s1'] is not None else "—"
            e2 = str(x['erg_s2']) if x['erg_s2'] is not None else "—"
            e3 = str(x['erg_s3']) if x['erg_s3'] is not None else "—"
            print(f"  {x['thema']:<36} {x['thema_orig_in_xlsx']:<28} {e1:>3} {e2:>3} {e3:>3}")
        print(f"\nGesamt: {len(items)} | Mit Anker-erg: {sum(1 for x in items if x['hat_anker_erg'])}")
        return

    # Resume
    if out_json.exists() and not args.dry_run:
        existing = json.loads(out_json.read_text(encoding="utf-8"))
        print(f"✓ Übersprungen — {len(existing)} Themen bereits vorhanden: {out_json.name}")
        return

    print(f"System-Prompt : {SYSTEM_PROMPT}")
    print(f"Anker-xlsx    : {ANCHOR_XLSX}")
    print(f"Ausgabe-Dir   : {OUT_DIR}")
    print(f"Modell        : {MODEL}  max_tokens={MAX_TOKENS}")
    print(f"Themen        : {len(items)} (alle mit Anker-erg)")

    print("\nLade System-Prompt …")
    system = load_system_prompt()
    print(f"  {len(system):,} Zeichen.")

    print("Lade Anker-Tabelle …")
    anchor_table = load_anchor_table()

    user_msg = build_user_message(items, anchor_table)

    if args.dry_run:
        print(f"\n[DRY-RUN] User-Message (erste 800 Zeichen):")
        print(user_msg[:800])
        print("…\n")
        return

    print(f"\n→ {MODEL} ({len(items)} Themen) …", flush=True)
    client = anthropic.Anthropic()
    t0 = time.time()
    try:
        raw = call_api(client, system, user_msg, MAX_TOKENS)
    except Exception as e:
        print(f"✗ API-Fehler: {e}")
        sys.exit(1)
    elapsed = time.time() - t0
    print(f"  {elapsed:.1f}s | {len(raw):,} Zeichen")

    out_raw.write_text(raw, encoding="utf-8")

    data = extract_json(raw)
    if data is None:
        print(f"✗ JSON-Parse fehlgeschlagen → {out_raw.name}")
        sys.exit(1)

    issues = validate_items(data, len(items))
    if issues:
        print(f"⚠ {len(issues)} Validierungs-Hinweis(e):")
        for iss in issues[:8]: print(iss)

    # Gesperrte erg-Werte aus Anker überschreiben (Rater darf sie nicht ändern)
    erg_by_lemma = {x["thema"]: x for x in items}
    korrekturen = 0
    for item in data:
        lemma = item.get("thema","")
        anker = erg_by_lemma.get(lemma)
        if anker and anker["hat_anker_erg"]:
            orig_e = (item.get("erg_s1"), item.get("erg_s2"), item.get("erg_s3"))
            item["erg_s1"] = anker["erg_s1"]
            item["erg_s2"] = anker["erg_s2"]
            item["erg_s3"] = anker["erg_s3"]
            new_e = (item["erg_s1"], item["erg_s2"], item["erg_s3"])
            if orig_e != new_e:
                korrekturen += 1
        item.setdefault("tier", "primary")
        item.setdefault("eignung", "include")
        item.setdefault("dublette_von", None)

    if korrekturen:
        print(f"  erg-Korrekturen (Anker überschrieben Rater): {korrekturen}")

    # Einzelne Dateien pro Gebiet anlegen (für Kompatibilität mit Merge-Skript)
    from collections import defaultdict
    by_gebiet: dict[str, list[dict]] = defaultdict(list)
    for item in data:
        by_gebiet[item.get("themengebiet", "Unbekannt")].append(item)

    for gebiet, gruppe in by_gebiet.items():
        slug = area_slug(gebiet)
        out_g = OUT_DIR / f"{slug}.json"
        out_g.write_text(json.dumps(gruppe, ensure_ascii=False, indent=2), encoding="utf-8")

    # Alle zusammen
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    n_l = sum(1 for x in data if x.get("leuchtturm"))
    n_s = sum(1 for x in data if x.get("sensibel"))
    print(f"\n✓ {len(data)} Themen gespeichert | {n_l} Leuchtturm | {n_s} sensibel")
    print(f"  Gebiet-Dateien: {list(by_gebiet.keys())}")
    print(f"  → {out_json.name}")

    print("\n── Stichproben ──")
    for probe in ["Wolfgang Amadeus Mozart", "Elefant", "Lego", "Indianer", "Wilhelm Tell"]:
        hit = next((x for x in data if x.get("thema") == probe), None)
        if hit:
            print(f"  {hit['thema']}: S1={hit['erg_s1']} S2={hit['erg_s2']} S3={hit['erg_s3']}"
                  f" | eignung={hit['eignung']} | age_floor={hit['age_floor']}"
                  f" | sensibel={hit.get('sensibel')} | leuchtturm={hit.get('leuchtturm')}"
                  f" | gebiet={hit.get('themengebiet','?')}")
            if hit.get('framing_note'):
                print(f"    framing: {hit['framing_note'][:80]}")


if __name__ == "__main__":
    main()
