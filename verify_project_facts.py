#!/usr/bin/env python3
"""verify_project_facts.py — prueft deklarierte Projekt-Fakten gegen den echten Code.
Einzige Stelle fuer tragende Fakten (CHECKS). Bei ABSICHTLICHER Aenderung: hier UND im
Code anpassen, sonst FAIL. Severity FAIL bricht (exit 1); KNOWN_OPEN ist nur Hinweis (exit 0).
Aufruf:  python verify_project_facts.py          (Pruefung)
         python verify_project_facts.py --dump    (Fakten als JSON, fuer PROJEKTDOKUMENT)
Stand der Deklaration: 2026-06-22, aus Code + Lauf-Artefakten verifiziert.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CHECKS = [
  {"desc":"Produktions-Generator-Modell","sev":"FAIL","type":"const",
   "file":"scripts/generate_grounded.py","const":"GEMINI_MODEL","expect":"gemini-3.5-flash"},
  {"desc":"Generator Thinking-Stufe MEDIUM","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"ThinkingLevel.MEDIUM"},
  {"desc":"run_batch.py erbt GEMINI_MODEL (kein eigener Owner)","sev":"FAIL","type":"contains",
   "file":"scripts/run_batch.py","needle":"GEMINI_MODEL"},
  {"desc":"Lektorat-Modell","sev":"FAIL","type":"const",
   "file":"scripts/lektorat_common.py","const":"LEKTORAT_MODEL","expect":"claude-sonnet-4-6"},
  {"desc":"Vision/Bild-Altersrating-Modell","sev":"FAIL","type":"const",
   "file":"scripts/run_batch.py","const":"VISION_MODEL","expect":"gemini-2.5-flash"},
  {"desc":"Bild-Recheck sensibler Themen = Opus 4.8","sev":"FAIL","type":"contains",
   "file":"scripts/run_batch.py","needle":"claude-opus-4-8"},
  {"desc":"Aktiver Generator-Prompt verdrahtet (v4 Produktion)","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"wissensfreund_generator_prompt_v4_production.md"},
  {"desc":"Generator-Prompt-Datei existiert (v4 Produktion)","sev":"FAIL","type":"file_exists",
   "file":"wissensfreund_generator_prompt_v4_production.md"},
  {"desc":"S1-Wortziel-Untergrenze ERG_BANDS[1]=(88,250)","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"1: (88, 250)"},
  {"desc":"Exclude-Backstop in Pipeline verdrahtet","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"_EXCLUDE_SET"},
  {"desc":"Wahrheitsquelle catalog_review_master.xlsx existiert","sev":"FAIL","type":"file_exists",
   "file":"catalog_review_master.xlsx"},
  {"desc":"ergiebigkeit_scores deckt Katalog (nicht der 134-Stub)","sev":"FAIL","type":"json_min",
   "file":"ergiebigkeit_scores.json","path":"scores","min":4000},
  {"desc":"eignung_exclude.json == XLSX-Excludes (reproduzierbar)","sev":"FAIL","type":"exclude_matches_xlsx"},
  {"desc":"Lektorat prueft Phase-1-Snapshot (kein eigener Quell-Fetch)","sev":"FAIL","type":"regex_absent",
   "file":"scripts/lektorat_common.py",
   "patterns":[r"\bfetch_wikipedia_text\s*\(", r"\bresolve_lemma\s*\(",
               r"(?m)^\s*(?:import\s+requests|from\s+requests\b)", r"\brequests\.[A-Za-z_]",
               r"(?m)^\s*import\s+urllib", r"\burllib\.request\b", r"\burlopen\s*\(",
               r"\bhttpx\."],
   "note":"Snapshot-Konsistenz: Lektorat darf die Quelle nicht neu holen (sonst Phantom-Flags durch Drift)."},
  {"desc":"CI-Workflow ruft Produktions-Skript run_batch.py","sev":"KNOWN_OPEN","type":"contains",
   "file":".github/workflows/artikel_pipeline.yml","needle":"run_batch.py",
   "note":"Migration ausstehend: Workflow ruft noch generate_articles.py (Legacy-Claude)."},
  {"desc":"CI-Workflow ruft NICHT den Legacy-Claude-Generator","sev":"KNOWN_OPEN","type":"not_contains",
   "file":".github/workflows/artikel_pipeline.yml","needle":"generate_articles.py",
   "note":"Bis Migration darf generate_articles.py NICHT der Produktions-Trigger sein."},
]

def read(rel):
    p = ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None

def const_val(txt, name):
    m = re.search(rf'{re.escape(name)}\s*=\s*["\']([^"\']+)["\']', txt)
    return m.group(1) if m else None

def run_check(c):
    t = c["type"]
    try:
        if t == "const":
            txt = read(c["file"])
            if txt is None: return "FAIL", f"{c['file']} fehlt"
            v = const_val(txt, c["const"])
            if v is None: return "FAIL", f"{c['const']} nicht gefunden"
            return ("PASS", f"{c['const']} = {v}") if v == c["expect"] else ("FAIL", f"{c['const']} = {v} (erwartet {c['expect']})")
        if t == "contains":
            txt = read(c["file"])
            if txt is None: return "FAIL", f"{c['file']} fehlt"
            return ("PASS", f"enthaelt '{c['needle']}'") if c["needle"] in txt else ("FAIL", f"'{c['needle']}' nicht gefunden")
        if t == "not_contains":
            txt = read(c["file"])
            if txt is None: return "PASS", f"{c['file']} fehlt (ok)"
            return ("PASS", f"'{c['needle']}' nicht vorhanden") if c["needle"] not in txt else ("FAIL", f"'{c['needle']}' noch vorhanden")
        if t == "file_exists":
            return ("PASS", "vorhanden") if (ROOT / c["file"]).exists() else ("FAIL", "fehlt")
        if t == "json_min":
            p = ROOT / c["file"]
            if not p.exists(): return "FAIL", "Datei fehlt"
            d = json.loads(p.read_text(encoding="utf-8"))
            node = d.get(c["path"], d); n = len(node)
            return ("PASS", f"{n} Eintraege") if n >= c["min"] else ("FAIL", f"nur {n} (< {c['min']} -> veralteter Stub?)")
        if t == "exclude_matches_xlsx":
            p = ROOT / "eignung_exclude.json"; x = ROOT / "catalog_review_master.xlsx"
            if not p.exists(): return "FAIL", "eignung_exclude.json fehlt"
            ex_json = set(json.loads(p.read_text(encoding="utf-8")).get("exclude", []))
            try:
                import pandas as pd
            except ImportError:
                return "SKIP", "pandas nicht verfuegbar — XLSX-Abgleich uebersprungen"
            if not x.exists(): return "SKIP", "XLSX nicht vorhanden (z. B. CI) — Abgleich uebersprungen"
            df = pd.read_excel(x, dtype=str)
            ex_xlsx = {str(r["thema"]).strip().lower() for _, r in df.iterrows()
                       if str(r["eignung"]).strip().lower() == "exclude"}
            if ex_json == ex_xlsx: return "PASS", f"{len(ex_json)} Excludes deckungsgleich"
            return "FAIL", f"JSON {len(ex_json)} vs XLSX {len(ex_xlsx)} — build_eignung_exclude.py neu laufen"
        if t == "regex_absent":
            # Verbotene Aufruf-/Import-Muster duerfen NICHT vorkommen. Robust gegen
            # Falschtreffer: zuerst Docstrings (''' / """) und #-Kommentare entfernen,
            # dann nur gegen echten Code matchen (Aufruf-/Import-Pattern, kein Substring).
            txt = read(c["file"])
            if txt is None: return "FAIL", f"{c['file']} fehlt"
            code = re.sub(r'""".*?"""', "", txt, flags=re.S)
            code = re.sub(r"'''.*?'''", "", code, flags=re.S)
            code = "\n".join(re.sub(r"#.*$", "", ln) for ln in code.splitlines())
            hits = [p for p in c["patterns"] if re.search(p, code)]
            return ("PASS", "keine verbotenen Aufruf-/Import-Muster") if not hits else \
                   ("FAIL", f"verbotenes Muster gefunden: {hits}")
        return "FAIL", f"unbekannter Check-Typ {t}"
    except Exception as e:
        return "FAIL", f"Check-Fehler: {type(e).__name__}: {e}"

def main():
    if "--dump" in sys.argv:
        print(json.dumps([{k:c.get(k) for k in ("desc","expect","sev")} for c in CHECKS], ensure_ascii=False, indent=2)); return 0
    results, hard_fail = [], 0
    for c in CHECKS:
        status, detail = run_check(c)
        if status == "FAIL" and c["sev"] == "KNOWN_OPEN": status = "KNOWN_OPEN"
        if status == "FAIL": hard_fail += 1
        results.append((status, c["desc"], detail, c.get("note","")))
    w = max(len(r[1]) for r in results)
    print(f"\n{'='*72}\n  PROJEKT-FAKTEN-CHECK  ({ROOT.name})\n{'='*72}")
    for status, desc, detail, note in results:
        print(f"  [{status:10}] {desc:<{w}}  {detail}")
        if note and status == "KNOWN_OPEN": print(f"               -> {note}")
    ko = sum(1 for r in results if r[0]=="KNOWN_OPEN"); sk = sum(1 for r in results if r[0]=="SKIP")
    print(f"{'='*72}\n  Hart-FAIL: {hard_fail} | KNOWN_OPEN: {ko} | SKIP: {sk} | gesamt: {len(results)}\n{'='*72}\n")
    return 1 if hard_fail else 0

if __name__ == "__main__":
    sys.exit(main())
