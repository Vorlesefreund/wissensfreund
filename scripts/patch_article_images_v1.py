#!/usr/bin/env python3
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
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

KLEXIKON_API  = "https://klexikon.zum.de/api.php"
COMMONS_API   = "https://commons.wikimedia.org/w/api.php"
THUMB_WIDTH   = 960
RATE_PAUSE    = 0.5
MAX_IMAGES    = 6

FILTER_PATTERN = re.compile(
    r"logo|flag|wappen|karte|map|icon|picto|portrait|stamp",
    re.IGNORECASE,
)
ALLOWED_EXT    = {".jpg", ".jpeg", ".png", ".webp"}
WIKITEXT_FILE  = re.compile(r"\[\[(?:File|Datei):([^\]\|]+)", re.IGNORECASE)


# ─── Checkpoint ──────────────────────────────────────────────────────────────

def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_checkpoint(path: Path, done: set[str]) -> None:
    path.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


# ─── Klexikon API ────────────────────────────────────────────────────────────

def get_klexikon_title(article: dict) -> str | None:
    """Extrahiert den Artikeltitel aus meta.source_url."""
    source_url = article.get("meta", {}).get("source_url", "")
    m = re.search(r"/wiki/(.+)$", source_url)
    if not m:
        return None
    return unquote(m.group(1).replace("_", " "))


def fetch_klexikon_image_names(title: str, session: requests.Session) -> list[str]:
    """
    Holt Bildnamen aus dem Klexikon-Wikitext.
    Klexikon's prop=images liefert keine Ergebnisse — Bilder stehen als
    [[File:...]] / [[Datei:...]] direkt im Wikitext.
    redirects=1 folgt Weiterleitungen automatisch (z.B. Elefant → Elefanten).
    """
    try:
        r = session.get(KLEXIKON_API, params={
            "action":        "query",
            "titles":        title,
            "redirects":     "1",
            "prop":          "revisions",
            "rvprop":        "content",
            "format":        "json",
            "formatversion": "2",
        }, timeout=20)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", [])
    except Exception as e:
        log.warning("  Klexikon API Fehler: %s", e)
        return []

    if not pages or pages[0].get("missing"):
        log.warning("  Klexikon-Artikel nicht gefunden: %r", title)
        return []

    revisions = pages[0].get("revisions", [])
    if not revisions:
        return []

    wikitext = revisions[0].get("content", "")
    names = [m.strip() for m in WIKITEXT_FILE.findall(wikitext)]
    return names


# ─── Filter ──────────────────────────────────────────────────────────────────

def filter_images(filenames: list[str]) -> list[str]:
    """Filtert nicht-inhaltliche Bilder und begrenzt auf MAX_IMAGES."""
    result = []
    for fn in filenames:
        if Path(fn).suffix.lower() not in ALLOWED_EXT:
            continue
        if FILTER_PATTERN.search(fn):
            continue
        result.append(fn)
        if len(result) >= MAX_IMAGES:
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
) -> bool:
    """
    Holt Bilder von Klexikon/Commons und schreibt sie in den Artikel.
    Setzt voraus, dass needs_patch() bereits True ergeben hat.
    Gibt True bei Erfolg zurück.
    """
    title = get_klexikon_title(article)
    if not title:
        log.warning("  Kein Klexikon-Titel in source_url: %s", path.stem)
        return False

    log.info("Verarbeite: %s  (Klexikon: %r)", path.stem, title)

    raw_names = fetch_klexikon_image_names(title, session)
    time.sleep(RATE_PAUSE)

    if not raw_names:
        log.warning("  Keine Bilder auf Klexikon gefunden")
        return False

    filtered = filter_images(raw_names)
    log.info(
        "  Klexikon: %d Bilder gesamt → %d nach Filter (SVG/Icon/Portrait/Stamp entfernt)",
        len(raw_names), len(filtered),
    )

    if not filtered:
        log.warning("  Alle Bilder herausgefiltert — Artikel übersprungen")
        return False

    meta_map = fetch_commons_metadata(filtered, session)
    time.sleep(RATE_PAUSE)

    images = []
    for idx, fn in enumerate(filtered):
        meta  = meta_map.get(fn, {})
        entry = build_image_entry(idx, fn, meta)
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
        success = patch_article(path, article, session, args.dry_run)
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
