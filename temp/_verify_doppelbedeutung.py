#!/usr/bin/env python3
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_grounded import build_grounded_user_message

job = {
    "thema": "Fußball", "title": "Fußball", "primaer_wikipedia": "Fußball",
    "age_level": 2,
    "doppelbedeutung_directive": "Erkläre zuerst Fußball (die Sportart), dann den Spielball.",
}
full = build_grounded_user_message(job, "PRIMARTEXT", {}, [], [])
assert "DOPPELBEDEUTUNG: Erkläre zuerst Fußball" in full, "Direktive nicht injiziert"
assert full.index("DOPPELBEDEUTUNG:") < full.index("AGE_LEVEL:"), "nicht im stabilen Prefix"

job2 = {k: v for k, v in job.items() if k != "doppelbedeutung_directive"}
assert "DOPPELBEDEUTUNG:" not in build_grounded_user_message(job2, "PRIMARTEXT", {}, [], []), \
    "ohne Direktive trotzdem injiziert"

print("PASS: injiziert, im stabilen Prefix, fehlt korrekt ohne Direktive")
