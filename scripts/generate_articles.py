#!/usr/bin/env python3
"""
generate_articles.py
Wissensfreund Artikel-Pipeline — Schritt 2

Liest Job-Batches aus prepare_articles.py, holt den Wikipedia-Volltext,
ruft die Claude API auf (System-Prompt + Wikipedia-Text), validiert das
JSON-Ergebnis und schreibt fertige Artikel-JSONs nach out-dir/.

Verwendung:
    python generate_articles.py \
        --jobs-dir   jobs/ \
        --out-dir    articles/ \
        --system-prompt wissensfreund_system_prompt_v3.8.md \
        --batch      0001 \
        --dry-run

Umgebungsvariablen:
    ANTHROPIC_API_KEY  — Claude API Key (Pflicht für --model sonnet)
    GEMINI_API_KEY     — Google API Key (Pflicht für --model flash, via .env)
"""

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CLAUDE_MODEL      = "claude-sonnet-4-6"
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"
WIKIPEDIA_API     = "https://de.wikipedia.org/w/api.php"
USER_AGENT        = "Wissensfreund-Pipeline/1.0 (educational children's app)"

MAX_TOKENS        = 8000   # Ausreichend für Stufe-3-Artikel (~700 Wörter + Struktur)
RATE_LIMIT_PAUSE  = 1.0    # Sekunden zwischen Claude-API-Calls
RETRY_ATTEMPTS    = 3
RETRY_BACKOFF     = 5      # Sekunden, verdoppelt bei jedem Retry

# Plausibilitätsgrenzen für Qualitätsprüfung
MIN_SENTENCES_PER_ARTICLE = {"1": 8,  "2": 15, "3": 25}
MAX_SENTENCES_PER_ARTICLE = {"1": 30, "2": 60, "3": 100}
MIN_QUIZ_QUESTIONS        = {"1": 3,  "2": 3,  "3": 4}


# ─────────────────────────────────────────────
# Wikipedia Text-Fetcher
# ─────────────────────────────────────────────

def fetch_wikipedia_text(session: requests.Session, title: str, rev_id: str = "") -> str:
    """Holt den bereinigten Wikipedia-Plaintext (ohne Infoboxen, Templates)."""
    params = {
        "action":          "query",
        "titles":          title,
        "redirects":       "1",
        "prop":            "extracts",
        "explaintext":     True,
        "exsectionformat": "plain",
        "format":          "json",
    }
    if rev_id:
        params["rvstartid"] = rev_id

    resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    for page in pages.values():
        text = page.get("extract", "")
        if text:
            return _clean_wikipedia_text(text)
    return ""


def _clean_wikipedia_text(text: str) -> str:
    """Entfernt typische Wikipedia-Artefakte aus dem Plaintext."""
    # Abschnitte die nichts für Kinder taugen
    skip_sections = [
        "== Weblinks ==", "== Literatur ==", "== Einzelnachweise ==",
        "== Siehe auch ==", "== Quellen ==", "== Anmerkungen ==",
    ]
    lines = text.split("\n")
    filtered = []
    skip = False
    for line in lines:
        if any(line.strip().startswith(s) for s in skip_sections):
            skip = True
        if skip and line.startswith("== ") and not any(line.strip().startswith(s) for s in skip_sections):
            skip = False
        if not skip:
            filtered.append(line)

    cleaned = "\n".join(filtered)
    # Mehrfache Leerzeilen reduzieren
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_IMG_SKIP_PREFIXES = (
    "File:Commons-logo", "File:Wikidata", "File:Question",
    "File:Symbol", "File:OOjs", "File:Portal", "File:Flag_of",
    "File:Nuvola", "File:Gnome-", "File:Red_Pencil", "File:Emblem",
    "File:Pictogram", "File:P_", "File:Disambig",
)
_IMG_SKIP_LOWER = (
    "_map.", "_karte.", "locator_map", "location_map",
    "_logo.", "logo_of", "_icon.", "icon_of",
    "pictogram", "emblem_of", "coat_of_arms", "wappen",
    "flag_of", "flagge_", "national_flag",
)
_IMG_SKIP_EXT = (".webm", ".ogv", ".ogg", ".svg")  # Keine Videos, keine reinen Vektorgrafiken


def _normalize_file_title(t: str) -> str:
    """'Datei:Foo.jpg' → 'File:Foo.jpg' (de.wikipedia → Commons)."""
    if t.startswith("Datei:"):
        return "File:" + t[6:]
    return t


def fetch_images_for_article(session: requests.Session, title: str, max_images: int = 30) -> list[dict]:
    """
    Holt Bild-Metadaten von Wikimedia Commons für einen Artikel.
    Gibt bis zu max_images Einträge zurück (für AVAILABLE_IMAGES im Prompt).
    Flash wählt daraus die besten aus und befüllt images[] direkt.
    """
    params = {
        "action":    "query",
        "titles":    title,
        "redirects": "1",
        "prop":      "images",
        "imlimit":   50,
        "format":    "json",
    }
    resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
    if resp.status_code == 429:
        time.sleep(5)
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    raw_titles = []
    for page in pages.values():
        for img in page.get("images", []):
            t = _normalize_file_title(img.get("title", ""))  # Datei: → File:
            t_lower = t.lower()
            if t_lower.endswith(_IMG_SKIP_EXT):
                continue
            if any(t.startswith(skip) for skip in _IMG_SKIP_PREFIXES):
                continue
            if any(sub in t_lower for sub in _IMG_SKIP_LOWER):
                continue
            raw_titles.append(t)

    if not raw_titles:
        return []

    time.sleep(0.5)  # Commons-API schonen
    # Commons-API für Lizenz + URL (800px thumb)
    params2 = {
        "action":     "query",
        "titles":     "|".join(raw_titles[:50]),
        "prop":       "imageinfo",
        "iiprop":     "url|extmetadata",
        "iiurlwidth": 800,
        "format":     "json",
    }
    resp2 = session.get("https://commons.wikimedia.org/w/api.php", params=params2, timeout=30)
    if resp2.status_code == 429:
        time.sleep(5)
        resp2 = session.get("https://commons.wikimedia.org/w/api.php", params=params2, timeout=30)
    resp2.raise_for_status()
    cpages = resp2.json().get("query", {}).get("pages", {})

    images = []
    idx = 0
    for page in cpages.values():
        ii = page.get("imageinfo", [{}])[0]
        thumb_url = ii.get("thumburl", "")
        if not thumb_url:
            continue  # kein 800px-Thumb → überspringen
        meta = ii.get("extmetadata", {})
        license_raw = meta.get("LicenseShortName", {}).get("value", "")
        if not _is_free_license(license_raw):
            continue
        images.append({
            "index":          idx,
            "filename":       _filename_from_title(page.get("title", "")),
            "alt":            _strip_html(meta.get("ImageDescription", {}).get("value", ""))[:200],
            "caption":        "",
            "license":        _normalize_license(license_raw),
            "license_author": _strip_html(meta.get("Artist", {}).get("value", ""))[:100],
            "source_url":     ii.get("descriptionurl", ""),
            "wikimedia_id":   page.get("title", ""),
            "thumb_url":      thumb_url,
        })
        idx += 1
        if idx >= max_images:
            break

    return images


def _is_free_license(s: str) -> bool:
    s = s.upper()
    if "-NC" in s or "-ND" in s:
        return False
    return any(k in s for k in (
        "CC0", "CC BY", "PUBLIC DOMAIN", "PD",
        "FAL", "LAL", "FREE ART", "ART LIBRE",
    ))


def _normalize_license(s: str) -> str:
    for k, v in [("CC0","CC0"),("CC BY-SA 4","CC BY-SA 4.0"),("CC BY-SA","CC BY-SA"),
                  ("CC BY 4","CC BY 4.0"),("CC BY","CC BY"),("PUBLIC","Public Domain"),("PD","Public Domain")]:
        if k in s.upper():
            return v
    return s


def _filename_from_title(title: str) -> str:
    return title.replace("File:", "").replace("Datei:", "").replace(" ", "_")


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


# ─────────────────────────────────────────────
# Claude API
# ─────────────────────────────────────────────

def load_system_prompt(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_user_message(job: dict, wikipedia_text: str, images: list[dict]) -> str:
    """Baut den User-Message-String nach v3.7-Vertrag.

    Pflicht: WIKIPEDIA_TEXT, ARTICLE_TITLE, AGE_LEVEL
    Optional: WIKIPEDIA_LINKS, ARTICLE_INDEX, KLEXIKON_AUFRUF_QUARTIL, IMAGE_METADATA
    Nicht mehr übergeben (Modell leitet selbst ab in Schritt 0):
      ARTICLE_PATTERN, CONTENT_DEPTH, TOPIC_APPEAL/TOPIC_INTEREST
    """
    parts = [
        "WIKIPEDIA_TEXT:",
        wikipedia_text,
        "",
        f"ARTICLE_TITLE: {job['title']}",
        f"AGE_LEVEL: {job['age_level']}",
    ]

    # Optionale Felder — nur wenn im Job vorhanden
    if job.get("wikipedia_links"):
        parts.append(f"WIKIPEDIA_LINKS: {json.dumps(job['wikipedia_links'], ensure_ascii=False)}")
    if job.get("article_index"):
        parts.append(f"ARTICLE_INDEX: {json.dumps(job['article_index'], ensure_ascii=False)}")
    if job.get("klexikon_aufruf_quartil"):
        parts.append(f"KLEXIKON_AUFRUF_QUARTIL: {job['klexikon_aufruf_quartil']}")

    # Bild-Metadaten als lesbare Liste für Flash (AVAILABLE_IMAGES)
    if images:
        parts.append("")
        parts.append("AVAILABLE_IMAGES (wähle die passendsten Fotos für diesen Artikel):")
        for img in images:
            author = img.get("license_author", "")[:50]
            line = f"[{img['index']}] {img['filename']} | {img['thumb_url']} | {img['license']}"
            if author:
                line += f" | {author}"
            parts.append(line)
        parts += [
            "",
            "Bildauswahl-Regeln:",
            "- images[0] = Hero-Bild: das repräsentativste Foto des Themas",
            "- thumb_url in images[] = URL aus AVAILABLE_IMAGES (exakt übernehmen)",
            "- img_index in sentences = 0-basierter Index in DEINEM images[]-Array",
            "- Kein Bild doppelt verwenden",
            "- High-appeal-Themen: 8–12 Bilder gesamt; Low-appeal: 4–6 Bilder",
            "- Für jedes Bild in images[]: filename, alt, caption, license, license_author, source_url, thumb_url befüllen",
        ]

    return "\n".join(parts)


def call_claude_api(
    api_key: str,
    system_prompt: str,
    user_message: str,
    model: str = CLAUDE_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Ruft die Claude API auf und gibt den Rohtext zurück."""
    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      model,
        "max_tokens": max_tokens,
        "system":     system_prompt,
        "messages":   [{"role": "user", "content": user_message}],
    }

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.post(CLAUDE_API_URL, headers=headers, json=body, timeout=120)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * (2 ** (attempt - 1))
                log.warning("Rate-limit (429) — warte %ds (Versuch %d/%d)", wait, attempt, RETRY_ATTEMPTS)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
        except requests.RequestException as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            wait = RETRY_BACKOFF * attempt
            log.warning("API-Fehler: %s — Retry in %ds", e, wait)
            time.sleep(wait)

    raise RuntimeError("Claude API: Alle Retry-Versuche ausgeschöpft")


# ─────────────────────────────────────────────
# JSON-Validierung
# ─────────────────────────────────────────────

def parse_article_json(raw: str) -> dict:
    """Extrahiert und parst JSON aus der Claude-Antwort."""
    if not raw:
        raise ValueError("Leere API-Antwort")
    # <planung>-Block vor dem JSON entfernen (Backend-Filter)
    cleaned = re.sub(r"<planung>.*?</planung>", "", raw, flags=re.DOTALL)
    # Markdown-Fences entfernen falls vorhanden
    cleaned = re.sub(r"^```json\s*", "", cleaned.strip())
    cleaned = re.sub(r"```\s*$", "", cleaned)
    article = json.loads(cleaned.strip())
    # Fehlende/null img_index normalisieren → -1 (Gemini lässt key manchmal weg)
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            if s.get("img_index") is None:
                s["img_index"] = -1
    return article


def validate_article(article: dict, job: dict) -> list[str]:
    """
    Grundlegende Plausibilitätsprüfung.
    Gibt eine Liste von Fehlern zurück (leer = OK).
    """
    errors = []
    level_str = str(job["age_level"])

    # Pflichtfelder meta
    meta = article.get("meta", {})
    for field in ["id", "title", "subtitle", "emoji", "age_level", "pattern",
                  "theme_color", "word_count", "source_wikipedia_url", "schema_version"]:
        if not meta.get(field):
            errors.append(f"meta.{field} fehlt")

    if meta.get("schema_version") != "1.0":
        errors.append(f"schema_version ist '{meta.get('schema_version')}', erwartet '1.0'")

    # Sections + Sentences
    sections = article.get("sections", [])
    if len(sections) < 2:
        errors.append(f"Nur {len(sections)} Abschnitte (min. 2)")

    all_sentences = [s for sec in sections for s in sec.get("sentences", [])]
    n = len(all_sentences)
    lo = MIN_SENTENCES_PER_ARTICLE.get(level_str, 8)
    hi = MAX_SENTENCES_PER_ARTICLE.get(level_str, 100)
    if not (lo <= n <= hi):
        errors.append(f"{n} Sätze außerhalb [{lo},{hi}] für Stufe {level_str}")

    # Satz-IDs fortlaufend
    ids = [s.get("id","") for s in all_sentences]
    for i, sid in enumerate(ids):
        expected = f"s{i+1:03d}"
        if sid != expected:
            errors.append(f"Satz-ID '{sid}' an Position {i+1}, erwartet '{expected}'")
            break  # nur ersten Fehler melden

    # img_index range: -1 = kein Bild (gültig), 0..n-1 = Index in images[]
    n_images = len(article.get("images", []))
    for s in all_sentences:
        idx = s.get("img_index")
        if idx is None:
            errors.append(f"Satz '{s.get('id')}' hat img_index=None")
            break
        if idx != -1 and (idx < 0 or (n_images > 0 and idx >= n_images)):
            errors.append(f"Satz '{s.get('id')}' hat img_index {idx} außerhalb [0,{n_images-1}]")
            break

    # Quiz
    quiz = article.get("quiz", {})
    questions = quiz.get("questions", [])
    min_q = MIN_QUIZ_QUESTIONS.get(level_str, 3)
    if len(questions) < min_q:
        errors.append(f"Nur {len(questions)} Quiz-Fragen (min. {min_q} für Stufe {level_str})")

    for q in questions:
        keys = {o.get("key") for o in q.get("options", [])}
        if keys != {"A", "B", "C"}:
            errors.append(f"Quiz-Frage '{q.get('id')}' hat falsche Keys: {keys}")
        if q.get("correct_key") not in {"A", "B", "C"}:
            errors.append(f"Quiz-Frage '{q.get('id')}' hat ungültigen correct_key")

    # myth-Box Pflichtfelder
    for sec in sections:
        for box in sec.get("boxes", []):
            if box.get("type") == "myth":
                if not box.get("reveal_text"):
                    errors.append("myth-Box ohne reveal_text")
                if box.get("reveal_mode") not in ("auto", "manual"):
                    errors.append(f"myth-Box hat ungültigen reveal_mode: {box.get('reveal_mode')}")

    return errors


# ─────────────────────────────────────────────
# Checkpoint
# ─────────────────────────────────────────────

def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def save_checkpoint(path: Path, done: set[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f, ensure_ascii=False)


# ─────────────────────────────────────────────
# Run-Statistik
# ─────────────────────────────────────────────

class RunStats:
    def __init__(self):
        self.ok = 0
        self.skipped = 0
        self.validation_errors = 0
        self.api_errors = 0
        self.flagged = 0

    def summary(self) -> str:
        total = self.ok + self.validation_errors + self.api_errors
        return (f"OK={self.ok}  Skip={self.skipped}  ValErr={self.validation_errors}  "
                f"APIErr={self.api_errors}  Flagged={self.flagged}  Total={total}")


# ─────────────────────────────────────────────
# Haupt-Loop
# ─────────────────────────────────────────────

def process_batch(
    batch_path: Path,
    out_dir: Path,
    system_prompt: str,
    api_key: str,
    checkpoint_path: Path,
    dry_run: bool = False,
    model: str = "sonnet",
) -> RunStats:
    stats = RunStats()
    done = load_checkpoint(checkpoint_path)

    with open(batch_path, encoding="utf-8") as f:
        batch = json.load(f)

    jobs = batch["jobs"]
    log.info("Batch %s: %d Jobs", batch_path.name, len(jobs))

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    out_dir.mkdir(parents=True, exist_ok=True)
    errors_dir = out_dir / "_errors"
    errors_dir.mkdir(exist_ok=True)

    for i, job in enumerate(jobs, 1):
        article_id = job["article_id"]
        log.info("[%d/%d] %s", i, len(jobs), article_id)

        # Skip wenn bereits erledigt
        if article_id in done:
            log.debug("  → bereits erledigt, skip")
            stats.skipped += 1
            continue

        # Skip wenn Ausgabedatei bereits existiert
        out_path = out_dir / f"{article_id}.json"
        if out_path.exists():
            log.debug("  → Datei existiert, skip")
            done.add(article_id)
            stats.skipped += 1
            continue

        # Wikipedia-Text holen
        try:
            wp_text = fetch_wikipedia_text(session, job["title"], job.get("source_rev", ""))
        except Exception as e:
            log.error("  Wikipedia-Fehler für '%s': %s", job["title"], e)
            stats.api_errors += 1
            continue

        if len(wp_text) < 300:
            log.warning("  Wikipedia-Text zu kurz (%d Zeichen) — skip", len(wp_text))
            stats.skipped += 1
            continue

        # Bilder holen
        try:
            images = fetch_images_for_article(session, job["title"])
            log.info("  %d AVAILABLE_IMAGES für '%s'", len(images), job["title"])
        except Exception as e:
            log.warning("  Bilder konnten nicht geladen werden: %s", e)
            images = []

        if dry_run:
            log.info("  DRY-RUN: Wikipedia-Text %d Zeichen, %d Bilder gefunden", len(wp_text), len(images))
            stats.ok += 1
            continue

        # API-Aufruf (Claude oder Gemini)
        user_msg = build_user_message(job, wp_text, images)
        try:
            if model == "flash":
                import gemini_client
                raw_response = gemini_client.call_gemini(system_prompt, user_msg)
            else:
                raw_response = call_claude_api(api_key, system_prompt, user_msg)
        except Exception as e:
            log.error("  API-Fehler (%s): %s", model, e)
            stats.api_errors += 1
            continue
        finally:
            time.sleep(RATE_LIMIT_PAUSE)

        # JSON parsen
        try:
            article = parse_article_json(raw_response)
        except (json.JSONDecodeError, ValueError) as e:
            log.error("  JSON-Parse-Fehler: %s", e)
            err_path = errors_dir / f"{article_id}_raw.txt"
            err_path.write_text(raw_response or "", encoding="utf-8")
            stats.validation_errors += 1
            continue

        # meta.id auf Job-Slug fixieren (Modell generiert sonst Wikipedia-basierte IDs)
        article.setdefault("meta", {})["id"] = article_id

        # generated_at setzen (Pflicht)
        article["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()

        # review_flag aus Job übernehmen wenn KI keines gesetzt hat
        if job.get("review_flag") and not article["meta"].get("review_flag"):
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = job.get("review_reason", "pipeline_flag")

        # Validierung
        errors = validate_article(article, job)
        if errors:
            log.warning("  Validierungsfehler (%d):", len(errors))
            for err in errors:
                log.warning("    • %s", err)
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = f"validation_errors: {'; '.join(errors[:3])}"
            # Trotzdem schreiben, aber in _errors/
            err_path = errors_dir / f"{article_id}.json"
            with open(err_path, "w", encoding="utf-8") as f:
                json.dump(article, f, ensure_ascii=False, indent=2)
            stats.validation_errors += 1
            done.add(article_id)
            save_checkpoint(checkpoint_path, done)
            continue

        # Artikel schreiben
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        if article["meta"].get("review_flag"):
            stats.flagged += 1
            log.info("  ✓ geschrieben (⚑ review_flag gesetzt)")
        else:
            stats.ok += 1
            log.info("  ✓ geschrieben")

        done.add(article_id)
        save_checkpoint(checkpoint_path, done)

    log.info("Batch fertig: %s", stats.summary())
    return stats


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Wissensfreund Artikel-Pipeline — Schritt 2: generate_articles")
    p.add_argument("--jobs-dir",        default=None,  type=Path)
    p.add_argument("--out-dir",         default="articles", type=Path)
    p.add_argument("--system-prompt",   default=Path("wissensfreund_generator_prompt_v3.20_production.md"), type=Path)
    p.add_argument("--batch",           default=None,  help="Nur diese Batch-Nummer verarbeiten, z.B. '0001'")
    p.add_argument("--checkpoint",      type=Path, default=Path("checkpoint_done.json"))
    p.add_argument("--dry-run",         action="store_true")
    p.add_argument("--model",           choices=["sonnet", "flash"], default="sonnet",
                                        help="Modell: sonnet (Claude, Standard) oder flash (Gemini 2.5 Flash)")
    p.add_argument("--test-connection", action="store_true",
                                        help="Testet API-Verbindung mit Minimal-Prompt und beendet")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Verbindungstest: minimaler API-Call, dann exit
    if args.test_connection:
        system_prompt = load_system_prompt(args.system_prompt)
        if args.model == "flash":
            import gemini_client
            resp = gemini_client.call_gemini(system_prompt[:500], "Antworte mit OK")
            print(f"Gemini Flash OK: {resp.strip()[:120]}")
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise SystemExit("ANTHROPIC_API_KEY nicht gesetzt")
            resp = call_claude_api(api_key, system_prompt[:500], "Antworte mit OK")
            print(f"Claude Sonnet OK: {resp.strip()[:120]}")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run and args.model == "sonnet":
        raise SystemExit("ANTHROPIC_API_KEY nicht gesetzt")

    if args.jobs_dir is None:
        raise SystemExit("--jobs-dir ist Pflicht (außer bei --test-connection)")

    system_prompt = load_system_prompt(args.system_prompt)
    log.info("System-Prompt geladen: %d Zeichen", len(system_prompt))

    # Batch-Dateien ermitteln
    if args.batch:
        batch_files = [args.jobs_dir / f"batch_{args.batch}.json"]
    else:
        batch_files = sorted(args.jobs_dir.glob("batch_*.json"))

    if not batch_files:
        raise SystemExit(f"Keine Batch-Dateien in {args.jobs_dir} gefunden")

    total_stats = RunStats()
    for batch_path in batch_files:
        if not batch_path.exists():
            log.error("Batch-Datei nicht gefunden: %s", batch_path)
            continue
        s = process_batch(
            batch_path      = batch_path,
            out_dir         = args.out_dir,
            system_prompt   = system_prompt,
            api_key         = api_key or "",
            checkpoint_path = args.checkpoint,
            dry_run         = args.dry_run,
            model           = args.model,
        )
        total_stats.ok               += s.ok
        total_stats.skipped          += s.skipped
        total_stats.validation_errors += s.validation_errors
        total_stats.api_errors       += s.api_errors
        total_stats.flagged          += s.flagged

    log.info("=== GESAMT: %s ===", total_stats.summary())


if __name__ == "__main__":
    main()
