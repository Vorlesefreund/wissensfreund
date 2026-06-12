#!/usr/bin/env python3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_grounded import _box_lint

def make_article(box_counts):
    """Erstellt Artikel mit gegebener Anzahl Boxen je Abschnitt."""
    secs = []
    for i, n in enumerate(box_counts):
        secs.append({
            "heading": f"Abschnitt {i+1}",
            "sentences": [{"text": f"Satz {i+1}."}],
            "boxes": [{"type": "stimmt_das", "text": f"Box {i+1}/{j+1}", "reveal_text": "x"}
                      for j in range(n)],
        })
    return {"sections": secs}

# ── Test 1: Clusterung (5 Abschnitte, letzter hat 2 Boxen) ──────────────────
a1 = make_article([0, 0, 0, 0, 2])
r1 = _box_lint(a1)
print(f"Test 1 (Clusterung):      {r1!r}")
assert r1 is not None and "Clusterung" in r1, f"FAIL: erwartet 'Clusterung', got {r1!r}"
print("  → PASS")

# ── Test 2: kein Mittelteil (4 Abschnitte, Box nur in 0 und 3) ──────────────
a2 = make_article([1, 0, 0, 1])
r2 = _box_lint(a2)
print(f"Test 2 (kein Mittelteil): {r2!r}")
assert r2 is not None and "mittleren Drittel" in r2, f"FAIL: erwartet 'mittleren Drittel', got {r2!r}"
print("  → PASS")

# ── Test 3: sauber (3 Abschnitte, Box in 0 und 1) ───────────────────────────
a3 = make_article([1, 1, 0])
r3 = _box_lint(a3)
print(f"Test 3 (sauber):          {r3!r}")
assert r3 is None, f"FAIL: erwartet None, got {r3!r}"
print("  → PASS")

# ── Test 4: <2 Boxen → immer None ───────────────────────────────────────────
a4 = make_article([0, 0, 1])
r4 = _box_lint(a4)
print(f"Test 4 (<2 Boxen):        {r4!r}")
assert r4 is None, f"FAIL: erwartet None, got {r4!r}"
print("  → PASS")

print("\nERGEBNIS: PASS (alle 4 Box-Lint-Tests)")
