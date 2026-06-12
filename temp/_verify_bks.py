#!/usr/bin/env python3
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

# ── Schmetterling: Selbst-BKS ─────────────────────────────────────────────────
print("── Schmetterling ──")
r = resolve_lemma(session, "Schmetterling")
print(f"  resolved_title: {r['resolved_title']}")
print(f"  flags:          {r['flags']}")
assert r["resolved_title"] != "Schmetterling", f"BKS nicht aufgelöst: {r['resolved_title']}"
assert any(f.startswith("BITTE PRUEFEN: BKS") for f in r["flags"]), \
    f"kein BKS-Flag: {r['flags']}"
print("  → PASS (BKS erkannt + aufgelöst)")

time.sleep(2.0)

# ── Hund: Redirect, KEINE BKS ────────────────────────────────────────────────
print("\n── Hund (Kontrolle) ──")
c = resolve_lemma(session, "Hund")
print(f"  resolved_title: {c['resolved_title']}")
print(f"  flags:          {c['flags']}")
assert c["resolved_title"] == "Haushund", f"Kontrolle falsch: {c['resolved_title']}"
assert not any("BKS" in f for f in c["flags"]), f"Hund fälschlich als BKS: {c['flags']}"
print("  → PASS (Redirect ohne BKS-Flag)")

time.sleep(2.0)

# ── Apfel: Augenschein ────────────────────────────────────────────────────────
print("\n── Apfel ──")
a = resolve_lemma(session, "Apfel")
print(f"  resolved_title: {a['resolved_title']}")
print(f"  flags:          {a['flags']}")

print("\nERGEBNIS: PASS")
