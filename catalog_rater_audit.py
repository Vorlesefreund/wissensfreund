#!/usr/bin/env python3
"""
catalog_rater_audit.py  v1  (2026-06-15)
──────────────────────────────────────────────────────────────────────────────
Nachbewertung von 393 audit-freigegebenen Themen.
Input:  audit_include_topics.json  (STATUS_NEU=NEU + eignung=include)
Output: catalog_raw_audit/<gebiet>.json  (gleiches Schema wie catalog_raw/)

Pro Themengebiet ein Opus-Call:
  • Nur Ergiebigkeit + Eignung bewerten — KEINE neuen Themen vorschlagen
  • Rater darf themengebiet korrigieren falls falsch einsortiert
  • Resume-fähig: vorhandene .json überspringen

Nutzung:
  python catalog_rater_audit.py                     # alle Gebiete
  python catalog_rater_audit.py --area Tiere        # nur Tiere
  python catalog_rater_audit.py --area Geschichte   # Präfix-Match
  python catalog_rater_audit.py --dry-run           # kein API-Call
  python catalog_rater_audit.py --list              # Gebiete + Anzahl
"""

import anthropic
import json
import pathlib
import re
import sys
import time
import argparse
from collections import defaultdict

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Pfade ─────────────────────────────────────────────────────────────────────
REPO_ROOT      = pathlib.Path(__file__).parent
SYSTEM_PROMPT  = REPO_ROOT / "wissensfreund_rater_kuratierung_v2.md"
ANCHOR_XLSX    = REPO_ROOT / "wortziele_ergiebigkeit_134_v2.xlsx"
INPUT_JSON     = REPO_ROOT / "audit_include_topics.json"
OUT_DIR        = REPO_ROOT / "catalog_raw_audit"

MODEL          = "claude-opus-4-8"
MAX_TOKENS     = 32000
RETRY_DELAYS   = [15, 45, 120]
INTER_CALL_PAUSE = 5

REQUIRED_FIELDS = {
    "thema", "themengebiet", "leuchtturm",
    "erg_s1", "erg_s2", "erg_s3",
    "eignung", "age_floor", "kategorie_nr",
    "framing_note", "sensibel", "begruendung_eignung",
    "dublette_von", "notiz",
}

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
    if not ANCHOR_XLSX.exists():
        sys.exit(f"FEHLER: Anker-xlsx nicht gefunden: {ANCHOR_XLSX}")
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
    missing = [k for k,v in idx.items() if v < 0]
    if missing:
        sys.exit(f"FEHLER: Spalten nicht erkannt: {missing}\nHeader: {raw_hdr}")
    lines = [f"{'Thema':<32} {'S1':>3} {'S2':>3} {'S3':>3}", "─"*44]
    count = 0
    for row in rows[1:]:
        t = row[idx["thema"]]
        if not t: continue
        def fmt(v): return str(int(v)) if isinstance(v,(int,float)) else (str(v) if v else "—")
        lines.append(f"{str(t):<32} {fmt(row[idx['s1']]):>3} {fmt(row[idx['s2']]):>3} {fmt(row[idx['s3']]):>3}")
        count += 1
    if count == 0: sys.exit("FEHLER: Keine Anker-Daten.")
    print(f"  {count} Anker geladen.")
    return "\n".join(lines)


def load_input() -> dict[str, list[dict]]:
    """Gibt Themen gruppiert nach themengebiet zurück."""
    if not INPUT_JSON.exists():
        sys.exit(f"FEHLER: {INPUT_JSON} nicht gefunden. Zuerst Aufgabe 1 ausführen.")
    data = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in data:
        g = (item.get("themengebiet") or "Unbekannt").strip()
        groups[g].append(item)
    return dict(groups)


def build_user_message(gebiet: str, themen: list[dict], anchor_table: str) -> str:
    n = len(themen)
    thema_liste = "\n".join(f"- {x['thema']}" for x in themen)

    # Kommentare (nur wenn vorhanden)
    with_kommentar = [(x["thema"], x["kommentar"]) for x in themen if x.get("kommentar")]
    kommentar_block = ""
    if with_kommentar:
        lines = [f"  {t}: {k}" for t, k in with_kommentar]
        kommentar_block = (
            "\n\nHinweise/Kommentare zu einzelnen Themen (bitte berücksichtigen):\n"
            + "\n".join(lines)
        )

    return (
        f"Themengebiet: {gebiet}\n\n"
        f"Die folgenden {n} Themen wurden bereits für den Wissensfreund-Katalog "
        f"freigegeben. Deine Aufgabe:\n"
        f"1. Weise jedem Thema Ergiebigkeit zu (erg_s1/s2/s3) anhand der Anker-Tabelle.\n"
        f"2. Vergib Eignungs-Urteil (eignung, age_floor, kategorie_nr, framing_note, "
        f"   sensibel, begruendung_eignung).\n"
        f"3. Setze leuchtturm=true für die Top-5% des Gebiets (max. {max(1,n//20)} Themen).\n"
        f"4. Setze notiz wenn sinnvoll.\n"
        f"5. Falls ein Thema offensichtlich ins FALSCHE Gebiet einsortiert ist, "
        f"   setze das korrekte themengebiet im Objekt.\n\n"
        f"WICHTIG:\n"
        f"- Schlage KEINE neuen Themen vor — nur die genannte Liste bewerten.\n"
        f"- Lass KEIN Thema weg — alle {n} müssen im JSON-Array erscheinen.\n"
        f"- Eignung: alle sind bereits als 'include' freigegeben. Setze 'exclude' "
        f"  nur wenn du eine echte Ungeeignetheit siehst (z.B. harm, kein Klexikon-Treffer).\n\n"
        f"Themenliste ({n} Themen):\n{thema_liste}"
        f"{kommentar_block}\n\n"
        f"Anker-Tabelle (verbindliche Ergiebigkeits-Skala, alle 134 Referenz-Themen):\n"
        f"{anchor_table}"
    )


def extract_json(raw: str) -> list[dict] | None:
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
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
        if item.get("eignung") not in ("include", "exclude", None):
            issues.append(f"  [{name}] ungültiges eignung='{item.get('eignung')}'")
    return issues


def call_api(client: anthropic.Anthropic, system: str, user: str, max_tokens: int) -> str:
    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    Retry {attempt}/{len(RETRY_DELAYS)} — warte {delay}s …", flush=True)
            time.sleep(delay)
        try:
            chunks: list[str] = []
            if max_tokens > 32000:
                ctx = client.beta.messages.stream(
                    model=MODEL, max_tokens=max_tokens,
                    system=system, messages=[{"role":"user","content":user}],
                    betas=["output-128k-2025-02-19"],
                )
            else:
                ctx = client.messages.stream(
                    model=MODEL, max_tokens=max_tokens,
                    system=system, messages=[{"role":"user","content":user}],
                )
            with ctx as stream:
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
                raise
    raise RuntimeError(f"Alle Retries erschöpft: {last_exc}")


def run_gebiet(
    client: anthropic.Anthropic | None,
    system: str,
    anchor_table: str,
    gebiet: str,
    themen: list[dict],
    max_tokens: int,
    dry_run: bool,
) -> bool:
    slug     = area_slug(gebiet)
    out_json = OUT_DIR / f"{slug}.json"
    out_raw  = OUT_DIR / f"{slug}_raw.txt"
    n        = len(themen)

    print(f"\n{'─'*60}")
    print(f"  {gebiet}  ({n} Themen)  slug={slug}")

    if out_json.exists() and not dry_run:
        existing = json.loads(out_json.read_text(encoding="utf-8"))
        print(f"  ✓ Übersprungen — {len(existing)} Themen bereits vorhanden.")
        return True

    # max_tokens skalieren: ~500 Token/Thema Output, aber mind. 8k
    adaptive_max = max(8000, min(max_tokens, n * 600 + 4000))

    user_msg = build_user_message(gebiet, themen, anchor_table)

    if dry_run:
        print(f"\n[DRY-RUN] {n} Themen, adaptive_max_tokens={adaptive_max}")
        print("User-Message (erste 600 Zeichen):")
        print(user_msg[:600])
        print("…\n")
        return True

    print(f"  → {MODEL}  max_tokens={adaptive_max} …", flush=True)
    t0 = time.time()
    try:
        raw = call_api(client, system, user_msg, adaptive_max)
    except Exception as e:
        print(f"  ✗ API-Fehler: {e}")
        return False
    elapsed = time.time() - t0
    print(f"    {elapsed:.1f}s | {len(raw):,} Zeichen")

    out_raw.write_text(raw, encoding="utf-8")

    data = extract_json(raw)
    if data is None:
        print(f"  ✗ JSON-Parse fehlgeschlagen → {out_raw.name}")
        return False

    issues = validate_items(data, n)
    if issues:
        print(f"  ⚠ {len(issues)} Validierungs-Hinweis(e):")
        for iss in issues[:5]:
            print(iss)
        if len(issues) > 5:
            print(f"    … und {len(issues)-5} weitere.")

    # Alle Themen sind bereits freigegeben → tier=primary
    for item in data:
        item.setdefault("tier", "primary")
        if item.get("eignung") is None:
            item["eignung"] = "include"

    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n_lthm = sum(1 for x in data if x.get("leuchtturm"))
    n_sens = sum(1 for x in data if x.get("sensibel"))
    n_corr = sum(1 for x in data if x.get("themengebiet","") != gebiet and x.get("themengebiet"))
    print(
        f"  ✓ {len(data)} Themen gespeichert  "
        f"({n_lthm} Leuchtturm, {n_sens} sensibel"
        + (f", {n_corr} Gebiet-Korrekturen" if n_corr else "")
        + f")  → {out_json.name}"
    )
    time.sleep(INTER_CALL_PAUSE)
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Audit-Nachbewertung — Ergiebigkeit + Eignung für 393 neue Themen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--area", help="Filter: Gebietsname (Präfix/Substring).")
    parser.add_argument("--dry-run", action="store_true", help="Kein API-Call.")
    parser.add_argument("--list", action="store_true", help="Zeigt Gebiete + Anzahl.")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    args = parser.parse_args()

    groups = load_input()
    # Sortierung: größte Gebiete zuerst (fehlschlagende eher auffällig)
    sorted_gebiete = sorted(groups.keys(), key=lambda g: -len(groups[g]))

    if args.list:
        print(f"{'Gebiet':<48} {'Themen':>7}")
        print("─"*57)
        total = 0
        for g in sorted_gebiete:
            n = len(groups[g])
            print(f"{g:<48} {n:>7}")
            total += n
        print("─"*57)
        print(f"{'GESAMT':<48} {total:>7}  ({len(sorted_gebiete)} Calls)")
        return

    # Gebiet-Filter
    areas = sorted_gebiete
    if args.area:
        f = args.area.lower()
        areas = [g for g in sorted_gebiete if f in g.lower()]
        if not areas:
            sys.exit(f"Kein Gebiet für Filter '{args.area}'. Tipp: --list")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"System-Prompt : {SYSTEM_PROMPT}")
    print(f"Anker-xlsx    : {ANCHOR_XLSX}")
    print(f"Input         : {INPUT_JSON}  ({sum(len(v) for v in groups.values())} Themen)")
    print(f"Ausgabe-Dir   : {OUT_DIR}")
    print(f"Modell        : {MODEL}  max_tokens={args.max_tokens}")
    print(f"Gebiete       : {len(areas)} (von {len(sorted_gebiete)})")

    print("\nLade System-Prompt …")
    system = load_system_prompt()
    print(f"  {len(system):,} Zeichen.")

    print("Lade Anker-Tabelle …")
    anchor_table = load_anchor_table()

    client = None if args.dry_run else anthropic.Anthropic()

    print(f"\nStarte {len(areas)} Call(s) …")
    ok_list, fail_list = [], []
    for gebiet in areas:
        themen = groups[gebiet]
        ok = run_gebiet(
            client, system, anchor_table,
            gebiet, themen,
            args.max_tokens, args.dry_run,
        )
        (ok_list if ok else fail_list).append(gebiet)

    print(f"\n{'='*60}")
    print(f"Fertig: {len(ok_list)}/{len(areas)} erfolgreich.")
    if fail_list:
        print(f"Fehlgeschlagen ({len(fail_list)}):")
        for g in fail_list:
            slug = area_slug(g)
            print(f"  {g}  →  {OUT_DIR / (slug+'_raw.txt')}")
        print("→ --area <Gebiet> für erneuten Versuch.")


if __name__ == "__main__":
    main()
