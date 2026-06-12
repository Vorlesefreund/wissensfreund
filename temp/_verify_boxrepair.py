#!/usr/bin/env python3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv; load_dotenv(ROOT / ".env")

from generate_grounded import (
    _box_lint,
    _box_signature,
    _box_repair_pass,
    GEMINI_MODEL,
    _make_thinking_config,
)

# Geclusterter Fake-Artikel: 4 Abschnitte, beide Boxen im letzten
article = {
    "title": "Der Regenwald",
    "intro": "Der Regenwald ist ein faszinierendes Ökosystem.",
    "sections": [
        {
            "heading": "Pflanzen",
            "sentences": [
                {"text": "Im Regenwald wachsen tausende verschiedene Pflanzenarten."},
                {"text": "Viele Pflanzen klettern an Bäumen empor, um Licht zu bekommen."},
            ],
            "boxes": [],
        },
        {
            "heading": "Tiere",
            "sentences": [
                {"text": "Affen, Papageien und Schmetterlinge leben im Regenwald."},
                {"text": "Jaguare sind die größten Raubtiere im Amazonas-Regenwald."},
            ],
            "boxes": [],
        },
        {
            "heading": "Klima",
            "sentences": [
                {"text": "Im Regenwald regnet es fast täglich, oft nachmittags."},
                {"text": "Die Temperaturen liegen das ganze Jahr über bei etwa 25 Grad."},
            ],
            "boxes": [],
        },
        {
            "heading": "Bedrohung",
            "sentences": [
                {"text": "Jedes Jahr werden große Flächen Regenwald abgeholzt."},
                {"text": "Das bedroht nicht nur Tiere und Pflanzen, sondern auch das Weltklima."},
            ],
            "boxes": [
                {"type": "stimmt_das", "text": "Regnete es im Regenwald jeden Tag?", "reveal_text": "Ja, fast täglich."},
                {"type": "wusstest_du", "text": "Der Amazonas-Regenwald produziert 20% des Sauerstoffs der Erde.", "reveal_text": None},
            ],
        },
    ],
    "meta": {"thema": "Regenwald", "age_level": 2},
}

# Vorbedingung: Lint erkennt Problem
issue_before = _box_lint(article)
print(f"Box-Issue vor Reparatur: {issue_before!r}")
assert issue_before is not None, "FAIL: Lint hätte Problem erkennen sollen"

sig_before = _box_signature(article)
thinking_config = _make_thinking_config(GEMINI_MODEL, budget_for_2_5=1024)

print("Starte Box-Reparatur-Pass...")
repaired = _box_repair_pass(article, GEMINI_MODEL, thinking_config)
sig_after = _box_signature(repaired)
issue_after = _box_lint(repaired)

print(f"Box-Issue nach Reparatur: {issue_after!r}")
print(f"Signatur gleich:          {sig_before == sig_after}")

assert sig_before == sig_after, f"FAIL: Inhalt verändert!\nVorher: {sig_before}\nNachher: {sig_after}"
assert issue_after is None, f"FAIL: Box-Issue nach Reparatur noch vorhanden: {issue_after}"

print("\nERGEBNIS: PASS (Reparatur erfolgreich, Inhalt unverändert)")
