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
  {"desc":"GEMINI_MODEL = aktives Generierungs-Modell (Einfrier-Stand Gemini Flash)","sev":"FAIL","type":"const",
   "file":"scripts/generate_grounded.py","const":"GEMINI_MODEL","expect":"gemini-3.5-flash"},
  # Einfrier-Stand-Routing (stage_models.py) — Weg B verworfen 26.06.2026,
  # Generierung zurueck auf Gemini Flash + v4. Diese Checks schuetzen den
  # eingefrorenen Vor-Weg-B-Stand vor Drift (bis Gemini Flash wieder zuverlaessig).
  {"desc":"Generierung eingefroren: Lemma-Routing = Gemini (bis Flash zuverlässig)","sev":"FAIL","type":"regex",
   "file":"scripts/stage_models.py",
   "pattern":r'"lemma":\s*\{\s*"provider":\s*"gemini"'},
  {"desc":"Generierung eingefroren: Kompass-Routing = Gemini (bis Flash zuverlässig)","sev":"FAIL","type":"regex",
   "file":"scripts/stage_models.py",
   "pattern":r'"kompass":\s*\{\s*"provider":\s*"gemini"'},
  {"desc":"Generierung eingefroren: Generator-Routing = Gemini (bis Flash zuverlässig)","sev":"FAIL","type":"regex",
   "file":"scripts/stage_models.py",
   "pattern":r'"generator":\s*\{\s*"provider":\s*"gemini",\s*"model":\s*"gemini-3.5-flash"'},
  {"desc":"Generierung eingefroren: Trim = Gemini (bis Flash zuverlässig)","sev":"FAIL","type":"regex",
   "file":"scripts/stage_models.py",
   "pattern":r'"trim":\s*\{\s*"provider":\s*"gemini"'},
  {"desc":"Generierung eingefroren: Box-Repair = Gemini (bis Flash zuverlässig)","sev":"FAIL","type":"regex",
   "file":"scripts/stage_models.py",
   "pattern":r'"box_repair":\s*\{\s*"provider":\s*"gemini"'},
  {"desc":"Generator Thinking-Stufe MEDIUM","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"ThinkingLevel.MEDIUM"},
  {"desc":"run_batch.py erbt GEMINI_MODEL (kein eigener Owner)","sev":"FAIL","type":"contains",
   "file":"scripts/run_batch.py","needle":"GEMINI_MODEL"},
  {"desc":"Lektorat-Modell = Claude Sonnet-5 (besser + günstiger als 4-6)","sev":"FAIL","type":"const",
   "file":"scripts/lektorat_common.py","const":"LEKTORAT_MODEL","expect":"claude-sonnet-5"},
  {"desc":"Vision/Bild-Auswahl-Modell = gemini-2.5-flash-lite (PO 2026-07: kein Sonnet-Vision, Kosten)","sev":"FAIL","type":"contains",
   "file":"scripts/stage_models.py","needle":'"vision":         {"provider": "gemini",    "model": "gemini-2.5-flash-lite"'},
  {"desc":"Bild-Recheck deaktiviert (Option A, Gemini-only) — reaktivierbar via provider 'anthropic'","sev":"FAIL","type":"contains",
   "file":"scripts/stage_models.py","needle":'"vision_recheck": {"provider": "none"'},
  {"desc":"Aktiver Generator-Prompt verdrahtet (v5.2 Produktion)","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"wissensfreund_generator_prompt_v5_2.md"},
  {"desc":"Generator-Prompt-Datei existiert (v5.2 Produktion)","sev":"FAIL","type":"file_exists",
   "file":"wissensfreund_generator_prompt_v5_2.md"},
  {"desc":"Hörspiel-Prompt verdrahtet (content_type-Auswahl, Paket B)","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":"wissensfreund_hoerspiel_prompt_v2_B.md"},
  {"desc":"Hörspiel-Prompt-Datei existiert (v2_B Story-first, einzige Fassung)","sev":"FAIL","type":"file_exists",
   "file":"wissensfreund_hoerspiel_prompt_v2_B.md"},
  {"desc":"Stufen-Umbau: Erzähltext-Band = (225,975)","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":'"erzaehltext": (225, 975)'},
  {"desc":"Hörspiel-Band = (275,1100) — PO 2026-07-21 angehoben fuer mehr Aspekte","sev":"FAIL","type":"contains",
   "file":"scripts/generate_grounded.py","needle":'"hoerspiel":   (275, 1100)'},
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
        if t == "regex":
            txt = read(c["file"])
            if txt is None: return "FAIL", f"{c['file']} fehlt"
            return ("PASS", "Pattern gefunden") if re.search(c["pattern"], txt) else \
                   ("FAIL", f"Pattern nicht gefunden: {c['pattern']}")
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
