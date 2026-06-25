#!/usr/bin/env python3
"""stage_models.py — zentrale Provider/Modell-Konfiguration pro Pipeline-Stufe.

Single Point of Truth: welche Stufe läuft über welchen Provider + welches Modell.
Aufrufstellen lesen die Konfig via get_stage_config(stage) statt eigener Konstanten.

Provider-Werte: "gemini" | "anthropic".
fallback: optionaler Modellname (gleicher Provider) bei Erschöpfung — None = keiner.
"""

STAGE_MODELS = {
    "lemma":          {"provider": "anthropic", "model": "claude-haiku-4-5",  "fallback": None},
    "kompass":        {"provider": "anthropic", "model": "claude-haiku-4-5",  "fallback": None},
    "vision":         {"provider": "gemini",    "model": "gemini-2.5-flash",  "fallback": None},
    "vision_recheck": {"provider": "anthropic", "model": "claude-opus-4-8",   "fallback": None},
    "generator":      {"provider": "gemini",    "model": "gemini-3.5-flash",  "fallback": None},
    "trim":           {"provider": "gemini",    "model": "gemini-3.5-flash",  "fallback": None},
    "box_repair":     {"provider": "gemini",    "model": "gemini-3.5-flash",  "fallback": None},
    "lektorat":       {"provider": "anthropic", "model": "claude-sonnet-4-6", "fallback": None},
}


def get_stage_config(stage):
    """Gibt eine Kopie der Konfig für die Stufe zurück. KeyError bei unbekannter Stufe."""
    if stage not in STAGE_MODELS:
        raise KeyError(f"Unbekannte Stufe: {stage}")
    return dict(STAGE_MODELS[stage])
