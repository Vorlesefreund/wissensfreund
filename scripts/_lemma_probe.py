#!/usr/bin/env python3
"""
Smoke-Test für resolve_lemma.

Auflösungsfälle:
  Schiffe   → Plural-Redirect zu "Schiff" (source: redirect, keine Flags)
  Seefahrer → kein Direkt-Artikel → Suche → "Liste von ..." (Flag: Listenartikel)
  Eis       → Direkt-Treffer, aber BKS-Schwesterseite (Flag: Doppelbedeutung)

Kontrolle (dürfen NICHT verändert werden):
  Elefant, Vulkan, Hund → direkt, keine Flags

Aufruf: python scripts/_lemma_probe.py
"""
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from generate_articles import resolve_lemma

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOPICS = [
    # Auflösungsfälle
    "Schiffe",
    "Seefahrer",
    "Eis",
    # Kontrolle
    "Elefant",
    "Vulkan",
    "Hund",
]

session = requests.Session()
session.headers.update({"User-Agent": "WissensfreundLemmaProbe/1.0"})

print(f"\n{'Thema':<14} {'Aufgeloest':<32} {'Vol':>8}  {'Quelle':<10} Flags")
print("-" * 95)
for topic in TOPICS:
    try:
        r = resolve_lemma(session, topic)
        title_str = str(r["resolved_title"]) if r["resolved_title"] else "—"
        flags_str = " | ".join(r["flags"]) if r["flags"] else "—"
        print(
            f"{topic:<14} {title_str:<32} {r['vol']:>8,}  {r['source']:<10} {flags_str}"
        )
    except Exception as e:
        print(f"{topic:<14} FEHLER: {type(e).__name__}: {e}")
    time.sleep(15.0)

print("-" * 95)
print("Fertig.")
