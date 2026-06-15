#!/usr/bin/env python3
"""
tts_compose.py  v1  (2026-06-15)
Wissensfreund — Canonical-JSON → tag-freier Vorlesetext

Nimmt einen Artikel im Canonical-JSON-Format (sections/sentences/boxes)
und erzeugt sauberen, emoji-freien Fließtext für die TTS-Pipeline.

  - Emojis gestrippt
  - Box-Typen mit altersgerechten Professor-Einleitungsphrasen
  - stimmt_das: Frage → Absatzpause → Antwort
  - Quiz wird ausgelassen
  - tts_config-Pausen als Blank-Lines kodiert (\n\n = natürliche Pause)

Nutzung:
  python tts_compose.py articles/test_compare/biene_3-5-flash_l2.json
  from tts_compose import compose, strip_emoji
"""

import json, pathlib, re, sys

# ---------------------------------------------------------------------------
# Professor-Einleitungsphrasen je Box-Typ und Stufe
# ---------------------------------------------------------------------------
_PHRASES: dict[str, dict[str, list[str]]] = {
    "wow": {
        "S1": [
            "Und weißt du was? ",
            "Stell dir mal vor — ",
            "Das ist wirklich erstaunlich: ",
        ],
        "S2": [
            "Hier kommt etwas Bemerkenswertes: ",
            "Und weißt du was? ",
            "Das ist wirklich faszinierend: ",
        ],
        "S3": [
            "Interessant dabei: ",
            "Bemerkenswert ist außerdem: ",
            "Ein faszinierendes Detail: ",
        ],
    },
    "fakt": {
        "S1": [
            "Und das solltest du wissen: ",
            "Hier ist noch etwas Wichtiges: ",
            "Übrigens: ",
        ],
        "S2": [
            "Ein wichtiger Fakt: ",
            "Noch etwas Interessantes: ",
            "Übrigens: ",
        ],
        "S3": [
            "Ergänzend dazu: ",
            "Ein weiterer Aspekt: ",
            "Zu beachten: ",
        ],
    },
    "warnung": {
        "S1": [
            "Achtung, das ist wichtig! ",
            "Aufgepasst: ",
            "Das solltest du unbedingt wissen: ",
        ],
        "S2": [
            "Achtung: ",
            "Aber Vorsicht — ",
            "Wichtig zu wissen: ",
        ],
        "S3": [
            "Wichtig: ",
            "Ein wichtiger Hinweis: ",
            "Zu beachten ist: ",
        ],
    },
    "stimmt_das": {
        "S1": [
            "Jetzt habe ich eine Frage für dich: ",
            "Kannst du das erraten? ",
            "Rate mal — ",
        ],
        "S2": [
            "Eine Frage: ",
            "Was denkst du — ",
            "Kannst du das beantworten? ",
        ],
        "S3": [
            "Kurze Frage: ",
            "Überlege kurz — ",
            "Hierzu eine Frage: ",
        ],
    },
}

_REVEAL_INTRO: dict[str, str] = {
    "S1": "Hier ist die Antwort: ",
    "S2": "Die Antwort: ",
    "S3": "",  # S3: Antwort direkt, keine Einleitung nötig
}

# Jeder Box-Typ bekommt deterministisch die erste Phrase (kein Random —
# identisches Ergebnis bei wiederholten Aufrufen, fair für A/B-Vergleich).
def _phrase(box_type: str, stufe: str) -> str:
    return (_PHRASES.get(box_type, {}).get(stufe) or [""])[0]


# ---------------------------------------------------------------------------
# Emoji-Strip
# ---------------------------------------------------------------------------
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"   # Symbole & Pictogramme
    "\U0001FA00-\U0001FA9F"
    "\U00002600-\U000027BF"   # Sonstige Symbole, Dingbats
    "\U0001F600-\U0001F64F"   # Emoticons
    "\U0001F680-\U0001F6FF"   # Transport
    "\U0001F1E0-\U0001F1FF"   # Flaggen
    "]+",
    flags=re.UNICODE,
)

def strip_emoji(text: str) -> str:
    """Entfernt alle Emoji-Zeichen und normalisiert Whitespace."""
    return _EMOJI_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------
def compose(article: dict, stufe: str | None = None) -> str:
    """
    Erzeugt den vollständigen, tag-freien Vorlesetext aus einem Canonical-JSON-Artikel.

    stufe: "S1" | "S2" | "S3"  — falls None, wird aus meta.age_level abgeleitet.
    Rückgabe: Fließtext, Abschnitte durch \\n\\n getrennt, kein Emoji, kein Markdown.
    """
    if stufe is None:
        level = article.get("meta", {}).get("age_level", 2)
        stufe = f"S{max(1, min(3, int(level)))}"

    parts: list[str] = []

    for sec in article.get("sections", []):
        # Überschrift als gesprochener Satz
        heading = strip_emoji((sec.get("heading") or "").strip())
        if heading:
            parts.append(heading if heading[-1] in ".!?" else heading + ".")

        # Fließtext-Sätze
        for sent in sec.get("sentences", []):
            text = strip_emoji((sent.get("text") or "").strip())
            if text:
                parts.append(text)

        # Boxen
        for box in sec.get("boxes", []):
            box_type = (box.get("type") or "").strip()
            box_text = strip_emoji((box.get("text") or "").strip())
            if not box_text:
                continue

            if box_type == "stimmt_das":
                reveal = strip_emoji((box.get("reveal_text") or "").strip())
                intro  = _phrase("stimmt_das", stufe)
                # Frage, dann Absatzpause, dann Antwort
                if reveal:
                    answer_intro = _REVEAL_INTRO.get(stufe, "")
                    parts.append(f"{intro}{box_text}\n\n{answer_intro}{reveal}")
                else:
                    parts.append(f"{intro}{box_text}")
            else:
                intro = _phrase(box_type, stufe)
                parts.append(f"{intro}{box_text}")

    # Quiz bewusst ausgelassen

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# CLI-Vorschau
# ---------------------------------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print("Nutzung: python tts_compose.py <artikel.json> [S1|S2|S3]")
        sys.exit(1)

    path = pathlib.Path(sys.argv[1])
    if not path.exists():
        print(f"Datei nicht gefunden: {path}")
        sys.exit(1)

    article = json.loads(path.read_text(encoding="utf-8"))
    stufe   = sys.argv[2].upper() if len(sys.argv) > 2 else None

    meta = article.get("meta", {})
    eff_stufe = stufe or f"S{meta.get('age_level', 2)}"
    print(f"=== {meta.get('title', path.stem)}  "
          f"(age_level={meta.get('age_level')}, stufe={eff_stufe}) ===\n")

    result = compose(article, stufe)
    print(result)
    print(f"\n--- {len(result)} Zeichen | {len(result.split())} Wörter ---")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
