#!/usr/bin/env python3
"""test_quote_repair.py — Verifikation _repair_article_quotes + parse_article_json.

SCHRITT 4: parse_article_json auf echte Sonnet-Freitext-Antworten (raw/*.txt) +
           _repair_article_quotes auf die stringifizierten Batch-Felder
           (sections, source_passages aus wal_l2_raw.json).
SCHRITT 5: sauberes JSON (mit U+201D-Quotes UND quote-frei) bleibt unverändert.

Reiner Verifikationstest, kein Pipeline-Code. KEIN Commit.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from generate_articles import parse_article_json, _repair_article_quotes

OK = "✅"
NO = "❌"


def hr(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


# ----------------------------------------------------------------------------
hr("SCHRITT 4a — parse_article_json auf Sonnet-Freitext (raw/*.txt)")
for p in sorted(Path("articles/test_sonnet/raw").glob("*.txt")):
    raw = p.read_text(encoding="utf-8")
    try:
        art = parse_article_json(raw)
        secs = len(art.get("sections", []))
        wc = sum(len(s.get("text", "").split())
                 for sec in art.get("sections", [])
                 for s in sec.get("sentences", []))
        imgs = len([s for sec in art.get("sections", [])
                    for s in sec.get("sentences", []) if s.get("img_index", -1) >= 0])
        quiz = len(art.get("quiz", {}).get("questions", []))
        sp = len(art.get("source_passages", []))
        print(f"{OK} {p.name}: sections={secs} woerter~{wc} bilder={imgs} "
              f"quiz={quiz} source_passages={sp}")
    except Exception as e:
        print(f"{NO} {p.name}: {type(e).__name__}: {e}")


# ----------------------------------------------------------------------------
hr("SCHRITT 4b — _repair_article_quotes auf stringifizierte Batch-Felder")
batch = json.load(open("articles/test_sonnet_batch/wal_l2_raw.json", encoding="utf-8"))
for field in ("sections", "source_passages"):
    val = batch.get(field)
    if not isinstance(val, str):
        print(f"  {field}: bereits strukturiert ({type(val).__name__}) — uebersprungen")
        continue
    # roh: defekt?
    raw_ok = True
    try:
        json.loads(val)
    except json.JSONDecodeError as e:
        raw_ok = False
        raw_err = e
    rep = _repair_article_quotes(val)
    try:
        parsed = json.loads(rep)
        n = len(parsed) if isinstance(parsed, list) else "?"
        roh = "ROH-OK" if raw_ok else f"roh-defekt({raw_err.msg})"
        print(f"{OK} {field}: {roh} -> repariert geparst, eintraege={n}")
    except json.JSONDecodeError as e:
        print(f"{NO} {field}: auch nach Repair defekt: {e}")


# ----------------------------------------------------------------------------
hr("SCHRITT 5 — sauberes JSON bleibt unveraendert (kein Verhaltenswechsel)")
clean_cases = {
    "korrektes_dt_quote": '{"text": "Der Name „Walfisch“ ist alt."}',
    "korrektes_dt_quote_201D": '{"text": "Er sagte „Hallo” zu mir."}',
    "quote_frei": '{"meta": {"title": "Wale", "age_level": 2}, "n": 5}',
    "ascii_quote_struktur": '{"a": "wert", "b": "x"}',
    "verschachtelt": '{"s":[{"text":"ohne quotes","img_index":-1}]}',
}
all_unchanged = True
for name, s in clean_cases.items():
    out = _repair_article_quotes(s)
    same = out == s
    all_unchanged = all_unchanged and same
    # zusaetzlich: bleibt parsebar
    json.loads(out)
    print(f"{OK if same else NO} {name}: unveraendert={same}")
print(f"\n{'ALLE sauberen Faelle unveraendert' if all_unchanged else 'FEHLER: sauberes JSON veraendert!'}")


# ----------------------------------------------------------------------------
hr("ZUSATZ — Defekt-Minimalfall wird tatsaechlich repariert")
defect = '{"text": "Der alte Name „Walfisch" klingt vertraut, ist aber falsch."}'
print(f"roh parsebar? ", end="")
try:
    json.loads(defect)
    print("JA (unerwartet)")
except json.JSONDecodeError:
    print("NEIN (erwartet — Defekt)")
fixed = _repair_article_quotes(defect)
try:
    d = json.loads(fixed)
    print(f"{OK} nach Repair geparst: text endet auf "
          f"...{d['text'][-25:]!r}")
    assert "”" in fixed, "U+201D nicht gesetzt"
    print(f"{OK} typografisches U+201D gesetzt, ASCII-\" entfernt")
except Exception as e:
    print(f"{NO} {type(e).__name__}: {e}")
