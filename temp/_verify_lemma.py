#!/usr/bin/env python3
"""Verifikation resolve_lemma: Redirect + BKS via Wikipedia-Netz."""
import sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
import requests
from generate_articles import resolve_lemma, USER_AGENT

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT

CASES = [
    ("Hund",          "resolved_title", "Haushund"),
    ("Schmetterling", "resolved_title", "Schmetterlinge"),
]

failures = []
print(f"{'Thema':<16}  {'resolved_title':<20}  {'flags':<30}  Status")
print("-" * 80)
for thema, field, expected in CASES:
    try:
        lr = resolve_lemma(session, thema)
        got = lr.get(field, "")
        flags = lr.get("flags", [])
        dd = (lr.get("doppelbedeutung_directive") or {}).get("directive", "")
        ok = got == expected
        status = "PASS" if ok else f"FAIL (got '{got}')"
        if not ok:
            failures.append(f"  {thema}: erwartet {field}={expected!r}, got {got!r}")
        print(f"{thema:<16}  {got:<20}  {str(flags):<30}  {status}")
        if dd:
            print(f"  → Direktive: {dd}")
    except Exception as e:
        print(f"{thema:<16}  NETZWERK-FEHLER: {e}")
        failures.append(f"  {thema}: Netzwerk-Fehler: {e}")
    time.sleep(1.0)

print()
if failures:
    print(f"ERGEBNIS: FAIL ({len(failures)} Fehler)")
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print("ERGEBNIS: PASS")
