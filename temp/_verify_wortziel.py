#!/usr/bin/env python3
"""Verifikation: wortziel_for() + appeal_for() gegen xlsx-Ground-Truth."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_grounded import wortziel_for, appeal_for

EXPECT_W = {
    "Kühlschrank": (83, 240, 375),
    "Wirtschaft":  (117, 347, 650),
    "Vulkan":      (217, 400, 650),
    "Düsseldorf":  (217, 400, 650),
    "Hund":        (250, 400, 650),
    "Dinosaurier": (250, 400, 650),
}

EXPECT_APPEAL = {
    "Dinosaurier": "high",
    "Hund":        "high",
    "Vulkan":      "high",
    "Düsseldorf":  "high",
    "Indianer":    "high",
    "Markt":       "high",
    "Wirtschaft":  "medium",
    "Kühlschrank": "medium",
    "Viereck":     "medium",
    "Pangolin":    "medium",
}

failures = []

# ── Wortziel-Checks ───────────────────────────────────────────────────────────
print(f"{'Thema':<14} {'S':>2}  {'Erwartet':>8}  {'Ist':>8}  {'Src':<16}  Status")
print("-" * 65)
for thema, (e1, e2, e3) in EXPECT_W.items():
    for lvl, expected in enumerate((e1, e2, e3), 1):
        wmin, wmax, src = wortziel_for(thema, lvl)
        ok = wmax == expected
        status = "PASS" if ok else f"FAIL (got {wmax})"
        if not ok:
            failures.append(f"  Wortziel {thema} S{lvl}: erwartet {expected}, got {wmax}")
        print(f"{thema:<14} {lvl:>2}  {expected:>8}  {wmax:>8}  {src:<16}  {status}")

# ── Appeal-Checks ─────────────────────────────────────────────────────────────
print()
print(f"{'Thema':<14}  {'Erwartet':<8}  {'Ist':<8}  {'Src':<16}  Status")
print("-" * 60)
for thema, expected in EXPECT_APPEAL.items():
    tier, src = appeal_for(thema)
    ok = tier == expected
    status = "PASS" if ok else f"FAIL (got {tier})"
    if not ok:
        failures.append(f"  Appeal {thema}: erwartet {expected}, got {tier}")
    print(f"{thema:<14}  {expected:<8}  {tier:<8}  {src:<16}  {status}")

# ── Fallback-Smoke ────────────────────────────────────────────────────────────
print()
print("── Fallback-Smoke ──")
wmin_fb, wmax_fb, src_fb = wortziel_for("zzz_unbekannt", 2)
# ERG_FALLBACK_SCORE=6, S2 band (80,400): frac=4/6=0.667, wmax=round(80+213.3)=293
exp_wmax_fb = 293
ok_fb_wz = (src_fb == "fallback-medium" and wmax_fb == exp_wmax_fb)
print(f"  wortziel_for('zzz_unbekannt', 2): src={src_fb!r}  wmax={wmax_fb}  "
      f"{'PASS' if ok_fb_wz else f'FAIL (expected src=fallback-medium wmax={exp_wmax_fb})'}")
if not ok_fb_wz:
    failures.append(f"  Fallback wortziel: src={src_fb!r} wmax={wmax_fb}")

tier_fb, src_ap = appeal_for("zzz_unbekannt")
ok_fb_ap = (tier_fb == "medium" and src_ap == "fallback-medium")
print(f"  appeal_for('zzz_unbekannt'):       src={src_ap!r}  tier={tier_fb!r}  "
      f"{'PASS' if ok_fb_ap else 'FAIL'}")
if not ok_fb_ap:
    failures.append(f"  Fallback appeal: tier={tier_fb!r} src={src_ap!r}")

# ── Ergebnis ─────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"ERGEBNIS: FAIL ({len(failures)} Fehler)")
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print("ERGEBNIS: PASS — alle Wortziele + Appeal-Tiers korrekt")
