#!/usr/bin/env python3
"""stage_models.py — zentrale Provider/Modell-Konfiguration pro Pipeline-Stufe.

Single Point of Truth: welche Stufe läuft über welchen Provider + welches Modell.
Aufrufstellen lesen die Konfig via get_stage_config(stage) statt eigener Konstanten.

Provider-Werte: "gemini" | "anthropic".
fallback: optionaler Modellname (gleicher Provider) bei Erschöpfung — None = keiner.
"""

STAGE_MODELS = {
    "lemma":          {"provider": "gemini",    "model": "gemini-3.5-flash",  "fallback": None},
    "kompass":        {"provider": "gemini",    "model": "gemini-3.5-flash",  "fallback": "gemini-2.5-flash"},
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


# Zentrales Artikel-JSON-Schema (input_schema für forced tool-use bei Anthropic).
# Geteilt von Generator, Trim und Box-Repair, damit alle drei dieselbe Struktur
# erzwingen. Bewusst permissiv (nur required-Kerne), damit das Modell nicht an
# optionalen Feldern scheitert.
ARTICLE_SCHEMA = {
    "type": "object",
    "required": ["meta", "sections", "quiz"],
    "properties": {
        "meta": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"},
            "subtitle": {"type": "string"}, "emoji": {"type": "string"},
            "age_level": {"type": "integer"}, "pattern": {"type": "string"},
            "theme_color": {"type": "string"}, "word_count": {"type": "integer"},
            "source_wikipedia_url": {"type": "string"}, "schema_version": {"type": "string"},
            "category_top": {"type": "string"}, "category_sub": {"type": "string"}}},
        "images": {"type": "array", "items": {"type": "object", "properties": {
            "index": {"type": "integer"}, "filename": {"type": "string"},
            "alt": {"type": "string"}, "caption": {"type": "string"},
            "license": {"type": "string"}, "license_author": {"type": "string"},
            "source_url": {"type": "string"}, "wikimedia_id": {"type": "string"},
            "thumb_url": {"type": "string"}}}},
        "sections": {"type": "array", "items": {"type": "object",
            "required": ["id", "heading", "sentences"], "properties": {
            "id": {"type": "string"}, "heading": {"type": "string"},
            "section_role": {"type": "string"},
            "sentences": {"type": "array", "items": {"type": "object",
                "required": ["id", "text", "img_index"], "properties": {
                "id": {"type": "string"}, "text": {"type": "string"},
                "img_index": {"type": "integer"}}}},
            "boxes": {"type": "array", "items": {"type": "object",
                "required": ["type", "text"], "properties": {
                "type": {"type": "string"}, "text": {"type": "string"},
                "reveal_text": {"type": "string"}, "reveal_mode": {"type": "string"}}}}}}},
        "quiz": {"type": "object", "properties": {"questions": {"type": "array",
            "items": {"type": "object", "required": ["id", "text", "options", "correct_key"],
            "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                "correct_key": {"type": "string"},
                "options": {"type": "array", "items": {"type": "object",
                    "required": ["key", "text"], "properties": {
                    "key": {"type": "string"}, "text": {"type": "string"}}}}}}}}},
        "related_terms": {"type": "object", "properties": {
            "core": {"type": "array", "items": {"type": "string"}},
            "discover": {"type": "array", "items": {"type": "string"}}}},
        "source_passages": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"}, "source": {"type": "string"},
            "passage": {"type": "string"}}}},
    },
}
