#!/usr/bin/env python3
"""
Flash-Importance: alle 33 Themen in EINEM Call, gemini-3.5-flash.
Scores S1(4-6)/S2(7-9)/S3(10-12) je 1-10, relativ gegeneinander bewertet.
Ergebnis → scripts/importance_cache_33.json

Aufruf: python scripts/_flash_importance_probe.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from gemini_client import call_gemini

from dotenv import load_dotenv
from google.genai import types as gtypes

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

MODEL = "gemini-3.5-flash"
OUT   = Path(__file__).parent / "importance_cache_33.json"

TOPICS_13 = [
    "Indianer", "Beethoven", "Elefant", "Vulkan", "Fußball",
    "Hund", "Apfel", "Feuerwehr", "Regenbogen", "Schmetterling",
    "Dinosaurier", "Ägypten", "Mozart",
]
TOPICS_20 = [
    "Pangolin", "Seefahrer", "Lego", "Kinderrechte", "Süßigkeiten",
    "Jahreszeiten", "Schule", "Schiffe", "Eis", "Kühlschrank",
    "Düsseldorf", "VW", "Brennessel", "Krankenschwester", "Pupille",
    "Zigaretten", "Hades", "Fasten", "Viereck", "Airbag",
]
ALL_TOPICS = TOPICS_13 + TOPICS_20

SYSTEM = """
Du bewertest Themen nach ihrer Faszination / Anziehungskraft für Kinder.
Skala 1–10 (1=kaum Interesse, 10=maximale Begeisterung).
Bewerte ALLE Themen RELATIV gegeneinander — scharfe Trennung anstreben.
Bewerte nach innerer Anziehungskraft für Kinder, NICHT nach Nachschlage-Häufigkeit.
Intuition erwünscht. Antworte NUR mit JSON-Array, kein Fließtext.
""".strip()

topics_str = ", ".join(ALL_TOPICS)
USER = f"""Bewerte für jedes Thema: S1=Kinder 4–6 J., S2=7–9 J., S3=10–12 J. (je 1–10).

Themen ({len(ALL_TOPICS)}): {topics_str}

Antworte als JSON-Array (genau {len(ALL_TOPICS)} Einträge):
[{{"thema":"Indianer","s1":N,"s2":N,"s3":N}}, ...]
"""


def _thinking_cfg():
    try:
        return gtypes.ThinkingConfig(thinking_level=gtypes.ThinkingLevel.MEDIUM)
    except AttributeError:
        return gtypes.ThinkingConfig(thinking_budget=8192)


def run_call(system: str, user: str) -> list[dict]:
    raw = call_gemini(
        system_prompt=system,
        user_message=user,
        model=MODEL,
        thinking_config=_thinking_cfg(),
        response_mime_type="application/json",
    )
    return json.loads(raw)


# ── Erster Versuch: alle 33 in einem Call ─────────────────────────────────────
print(f"Rufe {MODEL} auf — {len(ALL_TOPICS)} Themen in einem Call ...")
scores: list[dict] = []

try:
    data = run_call(SYSTEM, USER)
    if isinstance(data, list) and len(data) >= len(ALL_TOPICS) * 0.8:
        scores = data
        print(f"  OK — {len(data)} Einträge erhalten.")
    else:
        print(f"  Nur {len(data)} Einträge — teile in 2 Calls auf.")
        raise ValueError("zu wenig Einträge")
except Exception as e:
    print(f"  Erster Call fehlgeschlagen ({e}), teile auf ...")
    time.sleep(5)
    # Split: 13 + 20
    for group_topics, label in [(TOPICS_13, "13er"), (TOPICS_20, "20er")]:
        print(f"  {label} ...", end=" ", flush=True)
        g_str = ", ".join(group_topics)
        g_user = (
            f"Bewerte: S1=4–6 J., S2=7–9 J., S3=10–12 J. (je 1–10).\n"
            f"Themen ({len(group_topics)}): {g_str}\n"
            f"Antworte als JSON-Array: [{{\"thema\":\"...\",\"s1\":N,\"s2\":N,\"s3\":N}}, ...]"
        )
        try:
            part = run_call(SYSTEM, g_user)
            scores.extend(part)
            print(f"OK ({len(part)} Einträge)")
        except Exception as e2:
            print(f"FEHLER: {e2}")
        time.sleep(3)

# ── Normalisieren (Index nach Themenname) ──────────────────────────────────────
score_map: dict[str, dict] = {}
for entry in scores:
    t = entry.get("thema", "")
    if t:
        score_map[t] = {
            "thema": t,
            "s1": int(entry.get("s1", 5)),
            "s2": int(entry.get("s2", 5)),
            "s3": int(entry.get("s3", 5)),
        }

result_list = []
for t in ALL_TOPICS:
    if t in score_map:
        result_list.append(score_map[t])
    else:
        print(f"  WARNUNG: '{t}' fehlt in Antwort — Fallback 5/5/5")
        result_list.append({"thema": t, "s1": 5, "s2": 5, "s3": 5})

# ── Ausgabe ────────────────────────────────────────────────────────────────────
print(f"\n{'Thema':<20} {'S1':>3} {'S2':>3} {'S3':>3}")
print("-" * 35)
for e in result_list:
    print(f"{e['thema']:<20} {e['s1']:>3} {e['s2']:>3} {e['s3']:>3}")

# ── Cache speichern ────────────────────────────────────────────────────────────
cache = {
    "model":     MODEL,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "scores":    result_list,
}
OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nGespeichert: {OUT}")
