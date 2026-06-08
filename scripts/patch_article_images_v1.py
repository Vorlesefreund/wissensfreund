#!/usr/bin/env python3
# NOTE: Ab generate_articles.py mit IMAGE_METADATA-Prompt (Juni 2026) befüllt
# Flash images[] direkt — dieser Patch wird für neue Artikel NICHT mehr benötigt.
# Nur noch für Legacy-Artikel ohne Bilder verwenden.
"""
patch_article_images_v1.py
Wissensfreund — Bilder-Patch für bestehende Artikel-JSONs

Artikel mit images: [] werden mit echten Bildern von Wikimedia Commons befüllt,
ohne den Artikel neu zu generieren.

Verwendung:
    python patch_article_images_v1.py --articles-dir articles/ --dry-run
    python patch_article_images_v1.py --articles-dir articles/ --limit 10
    python patch_article_images_v1.py --articles-dir articles/ --force --limit 5
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

WIKIPEDIA_API   = "https://de.wikipedia.org/w/api.php"
COMMONS_API     = "https://commons.wikimedia.org/w/api.php"
CLAUDE_API_URL  = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL    = "claude-sonnet-4-6"
THUMB_WIDTH     = 960
RATE_PAUSE      = 0.5
MAX_IMAGES      = 6    # Fallback ohne KI
MAX_CANDIDATES  = 15   # Kandidaten-Pool für KI-Filter

FILTER_PATTERN = re.compile(
    r"logo|flag|wappen|karte|map|icon|picto|portrait|stamp",
    re.IGNORECASE,
)
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

AGE_LABELS = {1: "4-6 Jahre", 2: "7-9 Jahre", 3: "10-12 Jahre"}

AI_PROMPT = """\
Du bist Redakteur für das Kinderlexikon Wissensfreund.
Aufgabe: Wähle passende Bilder für einen Artikel aus und weise jedem Satz einen img_index zu.

Artikel: {titel}
Altersstufe: {age_level} ({age_label})
Maximale Bildanzahl: {max_images}

ALTERSSTUFEN-HINWEISE:
Stufe 1 (4-6 J.): Nur lebende Tiere, bunte Natur, freundliche \
Bilder. Keine Skelette, Fossilien, Anatomie, tote Tiere, \
Jagdszenen, verstörende Inhalte.
Stufe 2 (7-9 J.): Wie Stufe 1, aber Skelette und anatomische \
Darstellungen sind ok wenn sie lehrreich sind. Keine Fossilien \
ausgestorbener Arten als Hauptthema.
Stufe 3 (10-12 J.): Alle sachlich korrekten Bilder erlaubt, \
auch Fossilien, Vergleichsanatomie, historische Darstellungen.

ZUWEISUNG — REGELN:
- Weise jedem Satz einen img_index zu (0-basiert, Position im images[]-Array)
- Ein Bildwechsel soll dort stattfinden wo sich das Thema inhaltlich ändert — das kann mitten im Abschnitt sein
- Mehrere aufeinanderfolgende Sätze können denselben img_index haben
- Wähle so viele Bilder wie nötig um den Artikel visuell abwechslungsreich zu gestalten (max. {max_images})
- Kein Bild einem Satz zuweisen wenn es inhaltlich nicht passt — lieber denselben img_index weiterführen
- Jeder Satz muss eine Zuweisung erhalten

ABSCHNITTE UND SÄTZE:
{sections_json}

BILDKANDIDATEN:
{filenames_list}

Antworte NUR mit validem JSON — kein Text davor oder danach.
Format:
{{
  "images": [{{"filename": "...", "reason": "..."}}],
  "sentence_image_assignments": [
    {{"section_id": "...", "sent_id": "...", "img_index": 0}}
  ]
}}

img_index verweist auf die Position im images[]-Array (0-basiert). Jeder Satz muss eine Zuweisung haben.
Maximale Bildanzahl nach Interesse: high=15, medium=10, low=6"""


# ─── Lizenz-Whitelist ────────────────────────────────────────────────────────

def _is_free_license(s: str) -> bool:
    """Lizenz-Whitelist — spiegelt generate_articles._is_free_license() 1:1."""
    s = s.upper()
    if "-NC" in s or "-ND" in s:
        return False
    return any(k in s for k in (
        "CC0", "CC BY", "PUBLIC DOMAIN", "PD",
        "FAL", "LAL", "FREE ART", "ART LIBRE",
    ))


# ─── Checkpoint ──────────────────────────────────────────────────────────────

def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_checkpoint(path: Path, done: set[str]) -> None:
    path.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


# ─── Wikipedia API ───────────────────────────────────────────────────────────

_DE_ARTICLE = re.compile(r"^(?:Der|Die|Das)\s+", re.IGNORECASE)

def get_wikipedia_title(article: dict) -> str | None:
    """
    Liest meta.wikipedia_title, Fallback auf meta.title.
    Führende Artikel (Der/Die/Das) werden abgeschnitten, da Wikipedia-Titel
    normalerweise ohne Artikel stehen (z.B. "Elefant" statt "Der Elefant").
    meta.wikipedia_title wird unverändert übernommen (bereits korrekt gesetzt).
    """
    meta = article.get("meta", {})
    title = meta.get("wikipedia_title") or meta.get("title") or None
    if title and not meta.get("wikipedia_title"):
        title = _DE_ARTICLE.sub("", title).strip() or title
    return title or None


def fetch_wikipedia_image_names(title: str, session: requests.Session) -> list[str]:
    """Holt alle Dateinamen der Bilder im deutschen Wikipedia-Artikel."""
    try:
        r = session.get(WIKIPEDIA_API, params={
            "action":        "query",
            "titles":        title,
            "redirects":     "1",
            "prop":          "images",
            "imlimit":       "50",
            "format":        "json",
            "formatversion": "2",
        }, timeout=20)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", [])
    except Exception as e:
        log.warning("  Wikipedia API Fehler: %s", e)
        return []

    if not pages or pages[0].get("missing"):
        log.warning("  Wikipedia-Artikel nicht gefunden: %r", title)
        return []

    names = []
    for img in pages[0].get("images", []):
        t = img.get("title", "")
        if t.startswith("File:"):
            names.append(t.removeprefix("File:"))
        elif t.startswith("Datei:"):
            names.append(t.removeprefix("Datei:"))
    return names


# ─── Filter ──────────────────────────────────────────────────────────────────

def filter_images(filenames: list[str], limit: int = MAX_IMAGES) -> list[str]:
    """Filtert nicht-inhaltliche Bilder (SVG, Icons, …) und begrenzt auf limit."""
    result = []
    for fn in filenames:
        if Path(fn).suffix.lower() not in ALLOWED_EXT:
            continue
        if FILTER_PATTERN.search(fn):
            continue
        result.append(fn)
        if len(result) >= limit:
            break
    return result


# ─── Commons API ─────────────────────────────────────────────────────────────

def fetch_commons_metadata(filenames: list[str], session: requests.Session) -> dict[str, dict]:
    """
    Holt source_url, author, license und thumb_url (960px) für Commons-Dateien.
    Verarbeitet bis zu 50 Dateien pro API-Aufruf.
    """
    results: dict[str, dict] = {}

    for i in range(0, len(filenames), 50):
        batch = filenames[i:i + 50]
        titles = "|".join(f"File:{fn}" for fn in batch)

        try:
            r = session.get(COMMONS_API, params={
                "action":              "query",
                "titles":              titles,
                "prop":                "imageinfo",
                "iiprop":              "url|descriptionurl|extmetadata",
                "iiurlwidth":          str(THUMB_WIDTH),
                "iiextmetadatafilter": "Artist|LicenseShortName",
                "iimetadatalanguage":  "de",
                "format":              "json",
                "formatversion":       "2",
            }, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("  Commons API Fehler: %s", e)
            for fn in batch:
                results[fn] = {"source_url": "", "author": "", "license": "", "thumb_url": ""}
            continue

        for page in data.get("query", {}).get("pages", []):
            raw_title = page.get("title", "")
            fn = raw_title.removeprefix("File:") if raw_title.startswith("File:") else raw_title

            if page.get("missing") or "imageinfo" not in page:
                results[fn] = {"source_url": "", "author": "", "license": "", "thumb_url": ""}
                continue

            info    = page["imageinfo"][0] if page["imageinfo"] else {}
            extmeta = info.get("extmetadata", {})
            artist  = re.sub(r"<[^>]+>", "", extmeta.get("Artist", {}).get("value", "")).strip()

            results[fn] = {
                "source_url": info.get("descriptionurl", ""),
                "author":     artist,
                "license":    extmeta.get("LicenseShortName", {}).get("value", ""),
                "thumb_url":  info.get("thumburl", ""),
            }

    return results


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def filename_to_alt(filename: str) -> str:
    """Dateiname → lesbarer Alt-Text (Unterstriche, trailing Ziffern entfernen)."""
    stem = Path(filename).stem
    text = re.sub(r"[_\-]+", " ", stem)
    text = re.sub(r"\s+\d+$", "", text).strip()
    return text.title()


def build_image_entry(idx: int, filename: str, meta: dict) -> dict:
    return {
        "index":          idx,
        "filename":       filename,
        "alt":            filename_to_alt(filename),
        "caption":        "",
        "license":        meta.get("license", ""),
        "license_author": meta.get("author", ""),
        "source_url":     meta.get("source_url", ""),
        "thumb_url":      meta.get("thumb_url", ""),
    }


# ─── KI-Bildfilter ───────────────────────────────────────────────────────────

def build_sections_json(article: dict) -> str:
    """Kompakte Abschnitt+Satz-Struktur für den KI-Prompt."""
    sections = []
    for sec in article.get("sections", []):
        sections.append({
            "id":        sec.get("id", ""),
            "heading":   sec.get("heading", ""),
            "sentences": [
                {"id": s.get("id", ""), "text": s.get("text", "")}
                for s in sec.get("sentences", [])
            ],
        })
    return json.dumps(sections, ensure_ascii=False, indent=2)


def call_claude_image_filter(
    api_key: str,
    article: dict,
    filenames: list[str],
) -> dict | None:
    """
    Lässt Claude Bilder filtern, sortieren und Sätzen zuweisen.
    Gibt das geparste JSON-Objekt zurück oder None bei Fehler.
    """
    meta      = article.get("meta", {})
    age_level = meta.get("age_level", 2)
    titel     = meta.get("title", "")

    prompt = AI_PROMPT.format(
        titel=titel,
        age_level=age_level,
        age_label=AGE_LABELS.get(age_level, "7-9 Jahre"),
        max_images=15,
        sections_json=build_sections_json(article),
        filenames_list="\n".join(f"{i}. {fn}" for i, fn in enumerate(filenames)),
    )

    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":    CLAUDE_MODEL,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(3):
        try:
            resp = requests.post(CLAUDE_API_URL, headers=headers, json=body, timeout=60)
            if resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            resp.raise_for_status()
            raw     = resp.json()["content"][0]["text"]
            cleaned = re.sub(r"^```json\s*", "", raw.strip())
            cleaned = re.sub(r"```\s*$",     "", cleaned)
            return json.loads(cleaned)
        except Exception as e:
            log.warning("  Claude-Versuch %d fehlgeschlagen: %s", attempt + 1, e)
            time.sleep(5)
    return None


def needs_patch(article: dict, force: bool) -> bool:
    if force:
        return True
    images = article.get("images")
    return images is None or len(images) == 0


# ─── Patch-Logik ─────────────────────────────────────────────────────────────

def patch_article(
    path: Path,
    article: dict,
    session: requests.Session,
    dry_run: bool,
    api_key: str | None = None,
) -> bool:
    """
    Holt Bilder von Wikipedia/Commons, filtert und sortiert sie per KI,
    weist sie den Sätzen zu und schreibt zurück.
    Setzt voraus, dass needs_patch() bereits True ergeben hat.
    """
    title = get_wikipedia_title(article)
    if not title:
        log.warning("  Kein Titel in meta: %s", path.stem)
        return False

    log.info("Verarbeite: %s  (Wikipedia: %r)", path.stem, title)

    raw_names = fetch_wikipedia_image_names(title, session)
    time.sleep(RATE_PAUSE)

    if not raw_names:
        log.warning("  Keine Bilder auf Wikipedia gefunden")
        return False

    # Kandidaten-Pool für KI (mehr als MAX_IMAGES, SVG/Icons bereits raus)
    candidates = filter_images(raw_names, limit=MAX_CANDIDATES)
    log.info(
        "  Wikipedia: %d Bilder gesamt → %d Kandidaten nach Vorfilter",
        len(raw_names), len(candidates),
    )

    if not candidates:
        log.warning("  Alle Bilder herausgefiltert — Artikel übersprungen")
        return False

    meta_map = fetch_commons_metadata(candidates, session)
    time.sleep(RATE_PAUSE)

    # Lizenzfilter: nur freie Lizenzen in den KI-Pool
    candidates = [fn for fn in candidates if _is_free_license(meta_map.get(fn, {}).get("license", ""))]
    if not candidates:
        log.warning("  Keine Bilder mit freier Lizenz — Artikel übersprungen")
        return False

    # ── KI-Filter ────────────────────────────────────────────────────────────
    selected_filenames = candidates  # Fallback: alle Kandidaten
    ai_result = None

    if api_key:
        log.info("  KI-Filter: %d Kandidaten → Claude ...", len(candidates))
        ai_result = call_claude_image_filter(api_key, article, candidates)
        time.sleep(RATE_PAUSE)

    if ai_result:
        ai_images = ai_result.get("images", [])
        log.info("  KI wählte %d Bilder aus:", len(ai_images))
        for item in ai_images:
            log.info("    • %-55s  %s", item.get("filename", "")[:55], item.get("reason", ""))

        # Nur KI-gewählte Dateinamen die im meta_map vorhanden sind
        selected_filenames = [
            item["filename"] for item in ai_images
            if item.get("filename") in meta_map
        ]

        # Satz-Zuweisungen anwenden
        assignments = {
            (a["section_id"], a["sent_id"]): a["img_index"]
            for a in ai_result.get("sentence_image_assignments", [])
            if "section_id" in a and "sent_id" in a and "img_index" in a
        }
        if assignments:
            for sec in article.get("sections", []):
                for sent in sec.get("sentences", []):
                    key = (sec.get("id", ""), sent.get("id", ""))
                    if key in assignments:
                        sent["img_index"] = assignments[key]
            log.info("  %d Satz-Zuweisungen gesetzt", len(assignments))
    else:
        if api_key:
            log.warning("  KI-Filter fehlgeschlagen — Fallback auf Vorfilter-Ergebnis")
        # Ohne KI: Kandidaten auf MAX_IMAGES begrenzen
        selected_filenames = candidates[:MAX_IMAGES]

    # ── images[]-Array aufbauen ───────────────────────────────────────────────
    images = []
    for idx, fn in enumerate(selected_filenames):
        cm = meta_map.get(fn, {})
        entry = build_image_entry(idx, fn, cm)
        log.info(
            "  [%d] %-60s  thumb: %s",
            idx, fn[:60], "✓" if entry["thumb_url"] else "FEHLT",
        )
        images.append(entry)

    if dry_run:
        log.info("  DRY-RUN: würde %d Bilder schreiben (kein Write)", len(images))
        return True

    article["images"] = images
    path.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("  ✓ %d Bilder in %s geschrieben", len(images), path.name)
    return True


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Bilder-Patch für Wissensfreund Artikel-JSONs")
    p.add_argument("--articles-dir", required=True, type=Path, metavar="PATH")
    p.add_argument("--checkpoint",   default=Path("checkpoint_patch_images.json"), type=Path)
    p.add_argument("--dry-run",      action="store_true", help="Kein Schreiben")
    p.add_argument("--force",        action="store_true", help="Auch nicht-leere images[] überschreiben")
    p.add_argument("--limit",        type=int, default=0, metavar="N", help="Max N Artikel (0 = alle)")
    args = p.parse_args()

    if not args.articles_dir.is_dir():
        sys.exit(f"Verzeichnis nicht gefunden: {args.articles_dir}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY nicht gesetzt — KI-Filter deaktiviert, Fallback aktiv")

    files = sorted(args.articles_dir.glob("*.json"))
    log.info("%d Artikel-Dateien gefunden", len(files))

    done = load_checkpoint(args.checkpoint)
    if done:
        log.info("Checkpoint: %d bereits gepatch", len(done))

    session = requests.Session()
    session.headers["User-Agent"] = "Wissensfreund/1.0 (az@expansionssupport.de)"

    ok = skip = err = 0
    processed = 0

    for path in files:
        if args.limit and processed >= args.limit:
            break

        article_id = path.stem

        # Checkpoint-Check
        if article_id in done and not args.force:
            skip += 1
            continue

        # JSON laden
        try:
            article = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.error("JSON-Fehler bei %s: %s", path.name, e)
            err += 1
            processed += 1
            continue

        # Schon Bilder vorhanden?
        if not needs_patch(article, args.force):
            log.info("Übersprungen (images[] nicht leer): %s", article_id)
            if article_id not in done and not args.dry_run:
                done.add(article_id)
                save_checkpoint(args.checkpoint, done)
            skip += 1
            processed += 1
            continue

        # Patch durchführen
        success = patch_article(path, article, session, args.dry_run, api_key)
        processed += 1

        if success:
            ok += 1
            if not args.dry_run:
                done.add(article_id)
                save_checkpoint(args.checkpoint, done)
        else:
            err += 1

    log.info("─" * 50)
    log.info("Fertig: %d gepatch, %d übersprungen, %d Fehler", ok, skip, err)


if __name__ == "__main__":
    main()
