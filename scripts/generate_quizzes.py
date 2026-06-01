#!/usr/bin/env python3
"""
generate_quizzes.py
Wissensfreund — Quiz-Nachgenerierung für ZIM-konvertierte Artikel

Der ZIM-Konverter legt Platzhalter-Quizfragen an (review_flag=true).
Dieses Skript ersetzt sie durch echte Claude-generierte Fragen.

Verwendet einen schlanken Prompt — nur Artikeltext + Quiz-Regeln,
kein voller System-Prompt nötig.

Verwendung:
    python generate_quizzes.py \
        --articles-dir articles/ \
        --only-placeholders        # nur Artikel mit review_flag in Quiz
        --dry-run
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-haiku-4-5-20251001"
RATE_PAUSE     = 0.5

QUIZ_PROMPT = """Du generierst 3 Quiz-Fragen für einen Kinderlexikon-Artikel (Altersgruppe 7–9 Jahre).

REGELN:
- Immer genau 3 Antwortoptionen: A, B, C
- Fragen testen Textverständnis — kein Auswendiglernen
- correct_key gleichmäßig auf A/B/C verteilen
- explanation: ein kurzer Satz, positiv, TTS-tauglich
- Ausgabe: NUR valides JSON, kein Markdown, keine Erklärung

FORMAT:
{{
  "questions": [
    {{
      "id": "q01",
      "question": "...",
      "options": [
        {{"key": "A", "text": "..."}},
        {{"key": "B", "text": "..."}},
        {{"key": "C", "text": "..."}}
      ],
      "correct_key": "A",
      "explanation": "...",
      "image_quiz": false
    }}
  ]
}}

ARTIKELTITEL: {title}

ARTIKELTEXT:
{text}"""


def extract_article_text(article: dict) -> str:
    """Extrahiert den reinen Fließtext für den Quiz-Prompt."""
    lines = []
    for sec in article.get("sections", []):
        lines.append(sec.get("heading", ""))
        for s in sec.get("sentences", []):
            lines.append(s.get("text", ""))
    return " ".join(lines)[:3000]  # Max 3000 Zeichen für den Prompt


def needs_quiz_generation(article: dict) -> bool:
    """True wenn Quiz Platzhalter enthält."""
    questions = article.get("quiz", {}).get("questions", [])
    return any(q.get("review_flag") for q in questions)


def call_claude(api_key: str, title: str, text: str) -> list[dict] | None:
    prompt = QUIZ_PROMPT.format(title=title, text=text)
    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1000,
        "messages":   [{"role": "user", "content": prompt}],
    }
    for attempt in range(3):
        try:
            resp = requests.post(CLAUDE_API_URL, headers=headers, json=body, timeout=60)
            if resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            resp.raise_for_status()
            raw = resp.json()["content"][0]["text"]
            cleaned = re.sub(r"^```json\s*", "", raw.strip())
            cleaned = re.sub(r"```\s*$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("questions", [])
        except Exception as e:
            log.warning("  Versuch %d fehlgeschlagen: %s", attempt + 1, e)
            time.sleep(5)
    return None


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_checkpoint(path: Path, done: set[str]) -> None:
    path.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--articles-dir",     required=True, type=Path)
    p.add_argument("--only-placeholders", action="store_true")
    p.add_argument("--dry-run",          action="store_true")
    p.add_argument("--checkpoint",       default=Path("checkpoint_quiz.json"), type=Path)
    args = p.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        raise SystemExit("ANTHROPIC_API_KEY nicht gesetzt")

    files = sorted(args.articles_dir.glob("*.json"))
    log.info("%d Artikel-Dateien gefunden", len(files))

    done = load_checkpoint(args.checkpoint)
    if done:
        log.info("Checkpoint: %d bereits generiert", len(done))

    ok = skip = err = 0

    for path in files:
        article_id = path.stem
        try:
            article = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if article_id in done:
            skip += 1
            continue

        if args.only_placeholders and not needs_quiz_generation(article):
            done.add(article_id)
            skip += 1
            continue

        title = article.get("meta", {}).get("title", path.stem)
        log.info("Quiz für: %s", title)

        if args.dry_run:
            ok += 1
            continue

        text      = extract_article_text(article)
        questions = call_claude(api_key, title, text)
        time.sleep(RATE_PAUSE)

        if not questions or len(questions) < 3:
            log.warning("  Kein brauchbares Quiz erhalten")
            err += 1
            continue

        for q in questions:
            q.pop("review_flag", None)

        article["quiz"]["questions"] = questions
        if article.get("meta", {}).get("review_reason") == "":
            article["meta"]["review_flag"] = False

        path.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
        done.add(article_id)
        save_checkpoint(args.checkpoint, done)
        ok += 1
        log.info("  ✓ Quiz ersetzt")

    log.info("Fertig: %d OK, %d skip, %d Fehler", ok, skip, err)


if __name__ == "__main__":
    main()
