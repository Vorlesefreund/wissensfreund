#!/usr/bin/env python3
"""
catalog_rater_harness.py  v1  (2026-06-13)
──────────────────────────────────────────
Wissensfreund — Katalog-Kuratierungs-Harness

Ruft claude-opus-4-8 je Themengebiet/Unter-Thema auf (System-Prompt =
wissensfreund_rater_kuratierung_v2.md) und speichert JSON in catalog_raw/.
Bestehende .json-Dateien werden übersprungen (Resume-fähig).

Voraussetzungen:
  pip install anthropic openpyxl
  export ANTHROPIC_API_KEY=...

Nutzung:
  python catalog_rater_harness.py                         # alle ~24 Calls
  python catalog_rater_harness.py --list                  # Slugs + Budgets
  python catalog_rater_harness.py --area Tiere            # alle Tiere-Sub-Calls
  python catalog_rater_harness.py --area tiere_a          # ein Slug (Präfix-Match)
  python catalog_rater_harness.py --dry-run               # kein API-Call
  python catalog_rater_harness.py --max-tokens 20000      # für große Gebiete (>200)
"""

import anthropic
import json
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import openpyxl
import pathlib
import re
import sys
import time
import argparse

# Windows: Terminal-Encoding auf UTF-8 erzwingen (Box-Zeichen)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Pfade (relativ zum Script) ────────────────────────────────────────────

REPO_ROOT       = pathlib.Path(__file__).parent
SYSTEM_PROMPT   = REPO_ROOT / "wissensfreund_rater_kuratierung_v2.md"
ANCHOR_XLSX     = REPO_ROOT / "wortziele_ergiebigkeit_134_v2.xlsx"
CATALOG_RAW_DIR = REPO_ROOT / "catalog_raw"

# ── Modell-Konfiguration ──────────────────────────────────────────────────

MODEL        = "claude-opus-4-8"
MAX_TOKENS   = 32000           # Streaming erforderlich ab ~20k; budget>200 braucht ~25k+
RETRY_DELAYS = [15, 45, 120]   # Sekunden zwischen Retries (Rate-Limit / 5xx)
INTER_CALL_PAUSE = 5           # Sekunden Pause zwischen erfolgreichen Calls

# ── Gebiets-Definitionen ──────────────────────────────────────────────────
# Tupel: (thema, unter_thema_oder_None, budget)
# Reihenfolge = Ausführungsreihenfolge

AREAS = [
    # Tiere → 3 Sub-Calls (gesamt 500)
    ("Tiere", "A — Haustiere & Nutztiere",                                          120),
    ("Tiere", "B — Wildtiere (Säugetiere, Vögel, Reptilien, Amphibien)",            170),
    ("Tiere", "C — Meerestiere, Fische, Insekten, Spinnentiere, Dinosaurier",       210),

    # Einzelne Gebiete
    ("Pflanzen & Pilze",                              None, 200),
    ("Menschlicher Körper & Gesundheit",              None, 200),
    ("Erde, Wetter & Naturphänomene",                 None, 150),
    ("Naturräume & Landschaften",                     None, 130),
    ("Weltall & Astronomie",                          None, 160),

    # Naturwissenschaft → 2 Sub-Calls (gesamt 300)
    ("Naturwissenschaft & Biologie-Konzepte",
        "A — Physik, Chemie, Wie funktioniert …",                                   150),
    ("Naturwissenschaft & Biologie-Konzepte",
        "B — Biologie-Konzepte (Zelle, Evolution, Ökosystem …)",                    150),

    # Einzelne Gebiete
    ("Technik, Maschinen & Fahrzeuge",                None, 250),
    ("Länder & Kontinente",                           None, 240),
    ("Deutsche Städte",                               None, 110),
    ("Weltstädte & Wahrzeichen",                      None, 110),
    ("Geschichte & Epochen",                          None, 250),

    # Berühmte Personen → 2 Sub-Calls (gesamt 280)
    ("Berühmte Personen", "A — Historisch (bis ~1900)",         140),
    ("Berühmte Personen", "B — Zeitgenössisch (ab ~1900)",      140),

    # Einzelne Gebiete
    ("Kunst, Musik & Literatur",                      None, 180),
    ("Sport & Spiele",                                None, 150),
    ("Essen & Alltag",                                None, 190),
    ("Religion, Feste & Bräuche",                     None, 100),
    ("Gesellschaft, Berufe & Zusammenleben",          None, 180),
    ("Grundbegriffe (Zahlen, Formen, Farben, Zeit, Sprache)", None, 190),
    ("Märchen, Mythologie & Fabelwesen",              None, 110),
]

# Pflichtfelder je Themen-Objekt (für Validierung)
REQUIRED_FIELDS = {
    "thema", "themengebiet", "leuchtturm",
    "erg_s1", "erg_s2", "erg_s3",
    "eignung", "age_floor", "kategorie_nr",
    "framing_note", "sensibel", "begruendung_eignung",
    "dublette_von", "notiz",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────

def area_slug(thema: str, unter: str | None) -> str:
    """Dateiname-sicherer, eindeutiger Schlüssel (Umlaute transliteriert)."""
    raw = thema if not unter else f"{thema} {unter}"
    s = raw.lower()
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT.exists():
        sys.exit(f"FEHLER: System-Prompt nicht gefunden:\n  {SYSTEM_PROMPT}")
    return SYSTEM_PROMPT.read_text(encoding="utf-8")


def load_anchor_table() -> str:
    """
    Liest alle Anker aus wortziele_ergiebigkeit_134_v2.xlsx.
    Erwartet Header-Spalten mit 'thema', 's1', 's2', 's3' (case-insensitiv).
    Gibt kompakte Text-Tabelle zurück (für den User-Prompt).
    """
    if not ANCHOR_XLSX.exists():
        sys.exit(f"FEHLER: Anker-xlsx nicht gefunden:\n  {ANCHOR_XLSX}")

    wb = openpyxl.load_workbook(ANCHOR_XLSX, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        sys.exit("FEHLER: Anker-xlsx ist leer.")

    # Header-Zeile → Index-Map
    raw_headers = [str(v).strip().lower() if v is not None else "" for v in rows[0]]

    def find(must_contain: list[str], must_not: list[str] | None = None) -> int:
        for i, h in enumerate(raw_headers):
            if all(k in h for k in must_contain):
                if must_not and any(k in h for k in must_not):
                    continue
                return i
        return -1

    idx = {
        "thema": find(["thema"]),
        "s1":    find(["s1"]),
        "s2":    find(["s2"]),
        "s3":    find(["s3"]),
    }
    # Fallback: reine Ziffern-Suche (falls Header "Ergiebigkeit 1" o.ä.)
    if idx["s1"] < 0:
        idx["s1"] = find(["ergiebigkeit"], ["s2", "s3", "2", "3"])
    if idx["s2"] < 0:
        idx["s2"] = find(["ergiebigkeit", "2"], ["s1", "s3", "1", "3"])
    if idx["s3"] < 0:
        idx["s3"] = find(["ergiebigkeit", "3"], ["s1", "s2", "1", "2"])

    missing = [k for k, v in idx.items() if v < 0]
    if missing:
        sys.exit(
            f"FEHLER: Spalten nicht erkannt: {missing}\n"
            f"Gefundene Header: {raw_headers}\n"
            f"Bitte idx-Mapping in load_anchor_table() anpassen."
        )

    lines = [f"{'Thema':<32} {'S1':>3} {'S2':>3} {'S3':>3}", "─" * 44]
    count = 0
    for row in rows[1:]:
        thema = row[idx["thema"]]
        if not thema:
            continue
        def fmt(v): return str(int(v)) if isinstance(v, (int, float)) else (str(v) if v else "—")
        lines.append(
            f"{str(thema):<32} {fmt(row[idx['s1']]):>3} {fmt(row[idx['s2']]):>3} {fmt(row[idx['s3']]):>3}"
        )
        count += 1

    if count == 0:
        sys.exit("FEHLER: Keine Daten-Zeilen in Anker-xlsx gefunden.")

    print(f"  {count} Anker geladen.")
    return "\n".join(lines)


def build_user_message(thema: str, unter: str | None, budget: int, anchor_table: str) -> str:
    leuchtturm_max = max(3, int(budget * 0.05 + 0.5))
    parts = [f"Themengebiet: {thema}"]
    if unter:
        parts.append(f"Unter-Thema: {unter}")
    parts.append(
        f"Themengebiet-Größe: ~{budget} Themen (Orientierung). "
        f"Vollständigkeit vor Kürze — lieber zu viel als gute Themen weglassen."
    )
    parts.append(f"Leuchtturm-Quote: maximal {leuchtturm_max} Themen (Top ~5 % deines Gebiets).")
    parts.append("")
    parts.append("Anker-Tabelle — Ergiebigkeits-Referenz (verbindliche Skala, alle 134 Themen):")
    parts.append(anchor_table)
    return "\n".join(parts)


def extract_json(raw: str) -> list[dict] | None:
    """Extrahiert JSON-Array — toleriert Markdown-Fences und führenden Text."""
    text = raw.strip()
    # Markdown-Fences entfernen
    text = re.sub(r"^```[a-z]*\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Direkter Parse-Versuch
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        pass

    # Fallback: Array via Regex isolieren (bei führendem Text)
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            return data if isinstance(data, list) else None
        except json.JSONDecodeError:
            pass

    return None


def validate_items(data: list[dict]) -> list[str]:
    """Gibt Liste von Validierungs-Hinweisen zurück (leer = ok)."""
    issues = []
    for i, item in enumerate(data):
        name = item.get("thema", f"#{i}")
        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            issues.append(f"  [{name}] fehlende Felder: {sorted(missing)}")
        if item.get("eignung") not in ("include", "exclude", None):
            issues.append(f"  [{name}] ungültiges eignung='{item.get('eignung')}'")
        if item.get("sensibel") and not item.get("begruendung_eignung"):
            issues.append(f"  [{name}] sensibel=true aber begruendung_eignung leer")
    return issues


def split_primary_reserve(data: list[dict], budget: int) -> list[dict]:
    """
    Sortiert nach Leuchtturm + S2-Ergiebigkeit (desc), markiert top `budget`
    Themen als tier='primary', den Rest als tier='reserve'. In-place-Mutation.
    Leuchtturm-Items werden immer primary.
    """
    data.sort(
        key=lambda x: (
            1 if x.get("leuchtturm") else 0,
            x.get("erg_s2") or 0,
            x.get("erg_s1") or 0,
        ),
        reverse=True,
    )
    for i, item in enumerate(data):
        item["tier"] = "primary" if i < budget else "reserve"
    return data


def call_api(client: anthropic.Anthropic, system: str, user: str, max_tokens: int) -> str:
    """Ruft Opus auf mit Streaming + exponentiellem Retry bei Rate-Limit / 5xx."""
    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    Retry {attempt}/{len(RETRY_DELAYS)} — warte {delay}s …", flush=True)
            time.sleep(delay)
        try:
            chunks: list[str] = []
            with client.messages.stream(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
            return "".join(chunks)
        except anthropic.RateLimitError as e:
            print(f"    Rate-Limit: {e}")
            last_exc = e
        except anthropic.APIStatusError as e:
            print(f"    API-Fehler {e.status_code}: {e.message}")
            last_exc = e
            if e.status_code < 500:
                raise  # 4xx → kein Retry
    raise RuntimeError(f"Alle Retries erschöpft. Letzter Fehler: {last_exc}")


# ── Haupt-Verarbeitungs-Funktion ──────────────────────────────────────────

def run_area(
    client: anthropic.Anthropic | None,
    system: str,
    anchor_table: str,
    thema: str,
    unter: str | None,
    budget: int,
    out_dir: pathlib.Path,
    max_tokens: int,
    dry_run: bool,
) -> bool:
    slug  = area_slug(thema, unter)
    label = thema + (f" / {unter}" if unter else "")
    out_json = out_dir / f"{slug}.json"
    out_raw  = out_dir / f"{slug}_raw.txt"

    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"  budget={budget}  slug={slug}")

    # Resume: überspringen wenn fertig
    if out_json.exists() and not dry_run:
        existing = json.loads(out_json.read_text(encoding="utf-8"))
        print(f"  ✓ Übersprungen — {len(existing)} Themen bereits vorhanden.")
        return True

    user_msg = build_user_message(thema, unter, budget, anchor_table)

    if dry_run:
        print("\n[DRY-RUN] User-Message (erste 800 Zeichen):")
        print(user_msg[:800])
        print("…\n")
        return True

    print(f"  → {MODEL} …", flush=True)
    t0 = time.time()
    try:
        raw = call_api(client, system, user_msg, max_tokens)
    except Exception as e:
        print(f"  ✗ API-Fehler: {e}")
        return False
    elapsed = time.time() - t0
    print(f"    {elapsed:.1f}s | {len(raw):,} Zeichen")

    # Raw-Text immer sichern (auch bei JSON-Fehler)
    out_raw.write_text(raw, encoding="utf-8")

    # JSON extrahieren
    data = extract_json(raw)
    if data is None:
        print(f"  ✗ JSON-Parse fehlgeschlagen → {out_raw.name} für manuelle Rettung.")
        return False

    # Validierung
    issues = validate_items(data)
    if issues:
        print(f"  ⚠ {len(issues)} Validierungs-Hinweis(e):")
        for iss in issues[:5]:
            print(iss)
        if len(issues) > 5:
            print(f"    … und {len(issues)-5} weitere (siehe {out_raw.name}).")

    # Primary/Reserve-Split
    data = split_primary_reserve(data, budget)

    # Speichern
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n_primary    = sum(1 for x in data if x.get("tier") == "primary")
    n_reserve    = sum(1 for x in data if x.get("tier") == "reserve")
    n_sensibel   = sum(1 for x in data if x.get("sensibel"))
    n_leuchtturm = sum(1 for x in data if x.get("leuchtturm"))
    print(
        f"  ✓ {len(data)} Themen → {n_primary} primary / {n_reserve} reserve"
        f"  ({n_sensibel} sensibel, {n_leuchtturm} Leuchtturm) → {out_json.name}"
    )

    time.sleep(INTER_CALL_PAUSE)
    return True


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wissensfreund Katalog-Rater Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--area",
        help="Nur Gebiete, deren Thema/Unter-Thema/Slug diesen String enthält.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Kein API-Call — zeigt User-Message (erste 800 Zeichen).",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Zeigt alle Slugs, Budgets, Gesamt-Summe.",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=MAX_TOKENS,
        help=f"max_tokens pro Call (default {MAX_TOKENS}; bei budget>200 ggf. 20000).",
    )
    parser.add_argument(
        "--output-dir", default=str(CATALOG_RAW_DIR),
        help=f"Ausgabe-Verzeichnis (default: {CATALOG_RAW_DIR}).",
    )
    args = parser.parse_args()

    # ── --list ────────────────────────────────────────────────────────────
    if args.list:
        print(f"{'#':>3}  {'Slug':<52} {'Budget':>7}")
        print("─" * 66)
        total = 0
        for i, (t, u, b) in enumerate(AREAS, 1):
            print(f"{i:>3}  {area_slug(t, u):<52} {b:>7}")
            total += b
        print("─" * 66)
        print(f"     {'GESAMT':<52} {total:>7}  ({len(AREAS)} Calls)")
        return

    # ── Initialisierung ───────────────────────────────────────────────────
    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"System-Prompt : {SYSTEM_PROMPT}")
    print(f"Anker-xlsx    : {ANCHOR_XLSX}")
    print(f"Ausgabe-Dir   : {out_dir}")
    print(f"Modell        : {MODEL}  max_tokens={args.max_tokens}")

    print("\nLade System-Prompt …")
    system = load_system_prompt()
    print(f"  {len(system):,} Zeichen.")

    print("Lade Anker-Tabelle …")
    anchor_table = load_anchor_table()

    # ── Gebiets-Filter ────────────────────────────────────────────────────
    areas = AREAS
    if args.area:
        f = args.area.lower()
        areas = [
            a for a in AREAS
            if f in a[0].lower()
            or (a[1] and f in a[1].lower())
            or f in area_slug(a[0], a[1])
        ]
        if not areas:
            sys.exit(f"Kein Gebiet für Filter '{args.area}'. Tipp: --list")

    client = None if args.dry_run else anthropic.Anthropic()

    # ── Haupt-Loop ────────────────────────────────────────────────────────
    print(f"\nStarte {len(areas)} Call(s) …")
    ok_list, fail_list = [], []
    for thema, unter, budget in areas:
        ok = run_area(
            client, system, anchor_table,
            thema, unter, budget,
            out_dir, args.max_tokens, args.dry_run,
        )
        slug = area_slug(thema, unter)
        (ok_list if ok else fail_list).append(slug)

    # ── Abschluss-Report ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Fertig: {len(ok_list)}/{len(areas)} erfolgreich.")
    if fail_list:
        print(f"Fehlgeschlagen ({len(fail_list)}):")
        for s in fail_list:
            print(f"  {s}  →  {out_dir / (s + '_raw.txt')}")
        print("→ Raw-Texte für manuelle JSON-Rettung oder erneuten --area-Lauf.")


if __name__ == "__main__":
    main()
