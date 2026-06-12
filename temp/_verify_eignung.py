#!/usr/bin/env python3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grounded as gg

# Inject Testdaten direkt
gg._EIGNUNG = {
    "porno":      {"eignung": "exclude", "age_floor": 1, "framing_note": ""},
    "sexualität": {"eignung": "include", "age_floor": 3, "framing_note": "sachlich-biologisch"},
}

# Test 1: exclude
r = gg.eignung_for("Porno")
assert r["eignung"] == "exclude", f"FAIL exclude: {r}"
print(f"Test 1 (exclude):        PASS  {r}")

# Test 2: age_floor + framing_note
s = gg.eignung_for("Sexualität")
assert s["age_floor"] == 3 and s["framing_note"] == "sachlich-biologisch", f"FAIL sexualität: {s}"
print(f"Test 2 (age_floor/note): PASS  {s}")

# Test 3: fallback-permissive
u = gg.eignung_for("Elefant")
assert u["eignung"] == "include" and u["age_floor"] == 1 and u["source"] == "fallback-permissive", \
    f"FAIL fallback-permissive: {u}"
print(f"Test 3 (fallback-perm.): PASS  {u}")

# Test 4: STRICT-Schalter
gg.EIGNUNG_STRICT = True
v = gg.eignung_for("Elefant")
assert v["eignung"] == "exclude", f"FAIL strict: {v}"
print(f"Test 4 (strict):         PASS  {v}")
gg.EIGNUNG_STRICT = False

# Test 5: FRAMING-Injektion in build_grounded_user_message
job = {
    "thema": "Sexualität", "title": "Sexualität",
    "age_level": 3, "framing_note": "sachlich-biologisch",
}
full = gg.build_grounded_user_message(job, "TXT", {}, [], [])
assert "FRAMING: sachlich-biologisch" in full, f"FAIL FRAMING fehlt:\n{full[:500]}"
assert full.index("FRAMING:") < full.index("AGE_LEVEL:"), \
    "FAIL FRAMING nicht im stabilen Prefix"
print(f"Test 5 (FRAMING-Inj.):   PASS  (im stabilen Prefix)")

print("\nERGEBNIS: PASS (exclude / age_floor / fallback / strict / FRAMING-Injektion)")
