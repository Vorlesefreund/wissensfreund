#!/usr/bin/env python3
"""
convert_zim_to_json.py
Wissensfreund Artikel-Pipeline — Einmalkonverter

Liest alle Klexikon-Artikel aus der ZIM-Datei, konvertiert das
HTML in das Wissensfreund-JSON-Schema (v1.0) und schreibt die
Ergebnisse nach out-dir/.

Da Klexikon keine Altersabstufung hat, werden alle Artikel als
age_level=2 (7–9 Jahre) gesetzt — das ist die passendste Stufe
für Klexikon-Texte. age_level=1 und =3 werden später durch die
KI-generierten Artikel abgedeckt.

Verwendung:
    python convert_zim_to_json.py \
        --zim       klexikon_de_all_maxi_2026-05.zim \
        --image-map image_map.json \
        --out-dir   articles/ \
        --dry-run

Abhängigkeiten:
    pip install libzim beautifulsoup4 requests

image_map.json:
    Die von build_image_map.py erzeugte Datei:
    { "md5hash": { "filename": "...", "source_url": "...", ... } }
    Wenn nicht vorhanden: Bilder werden als Platzhalter eingetragen.
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

SCHEMA_VERSION = "1.0"
AGE_LEVEL      = 2          # Klexikon-Artikel = Stufe 2
SOURCE_BASE    = "https://klexikon.zum.de/wiki/"

# Themenfarben nach Klexikon-Kategorie (best-effort Zuordnung)
CATEGORY_COLORS = {
    "Tiere":        "#4caf50",
    "Pflanzen":     "#33691e",
    "Länder":       "#e65100",
    "Städte":       "#e65100",
    "Geschichte":   "#795548",
    "Personen":     "#6a1b9a",
    "Technik":      "#37474f",
    "Wissenschaft": "#37474f",
    "Natur":        "#1565c0",
    "Erde":         "#1565c0",
    "Sport":        "#c62828",
    "Kultur":       "#c62828",
    "Musik":        "#c62828",
    "default":      "#546e7a",
}

PATTERN_MAP = {
    "Tiere":        "living_being",
    "Pflanzen":     "living_being",
    "Länder":       "place_geography",
    "Städte":       "place_geography",
    "Geschichte":   "history_person",
    "Personen":     "history_person",
    "Technik":      "tech_science",
    "Wissenschaft": "tech_science",
    "default":      "tech_science",
}


# ─────────────────────────────────────────────
# ZIM-Zugriff
# ─────────────────────────────────────────────

def open_zim(zim_path: Path):
    """Öffnet die ZIM-Datei und gibt ein libzim.Archive zurück."""
    try:
        from libzim.reader import Archive
    except ImportError:
        raise SystemExit(
            "libzim nicht installiert.\n"
            "Installieren mit: pip install libzim"
        )
    return Archive(str(zim_path))


def iter_articles(archive) -> list[tuple[str, str]]:
    """
    Gibt alle Artikel-Einträge zurück als (title, html).
    Überspringt Weiterleitungen, Metaseiten und sehr kurze Einträge.
    Unterstützt altes ZIM-Format (A/-Namespace) und neues (flat namespace).
    """
    articles = []
    for i in range(archive.entry_count):
        try:
            entry = archive._get_entry_by_id(i)
            if entry.is_redirect:
                continue
            path = entry.path
            # Titel: aus A/-Namespace, C/-Namespace oder flachem Pfad
            if path.startswith("A/"):
                raw_title = path[2:]
            elif path.startswith("C/"):
                raw_title = path[2:]
            elif "/" not in path:
                raw_title = path
            else:
                # Subpfad (Bilder, Assets usw.) — überspringen
                continue
            title = entry.title or raw_title.replace("_", " ")
            # Metaseiten überspringen
            if any(title.startswith(skip) for skip in (
                "Klexikon:", "Vorlage:", "Kategorie:", "Hilfe:", "Wikipedia:"
            )):
                continue
            item = entry.get_item()
            # Nur HTML-Einträge sind Artikel
            if "text/html" not in item.mimetype:
                continue
            html = bytes(item.content).decode("utf-8", errors="replace")
            if len(html) < 500:
                continue
            articles.append((title, html))
        except Exception:
            continue
    return articles


# ─────────────────────────────────────────────
# HTML → JSON Konverter
# ─────────────────────────────────────────────

def html_to_article(
    title: str,
    html: str,
    image_map: dict,
    article_idx: int = 0,
) -> dict | None:
    """
    Konvertiert einen Klexikon-HTML-Artikel ins Wissensfreund-JSON-Schema.
    Gibt None zurück wenn der Artikel zu wenig verwertbaren Inhalt hat.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Metadaten ──────────────────────────────
    category    = _detect_category(soup, title)
    theme_color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["default"])
    pattern     = PATTERN_MAP.get(category, PATTERN_MAP["default"])
    subtitle    = _extract_subtitle(soup, title)
    emoji       = _guess_emoji(title, category)

    # ── Bilder ────────────────────────────────
    images = _extract_images(soup, image_map)
    if not images:
        # Artikel ohne Bilder bekommen einen Platzhalter-Eintrag
        images = [{
            "index":          0,
            "filename":       "",
            "alt":            title,
            "caption":        "",
            "license":        "CC BY-SA",
            "license_author": "Klexikon",
            "source_url":     f"{SOURCE_BASE}{title.replace(' ', '_')}",
            "wikimedia_id":   "",
            "thumb_url":      "",
        }]

    # ── Abschnitte + Sätze ───────────────────
    sections = _extract_sections(soup, images)
    if not sections:
        log.warning("  Keine Abschnitte in '%s' — übersprungen", title)
        return None

    total_sentences = sum(len(s["sentences"]) for s in sections)
    if total_sentences < 5:
        log.warning("  Zu wenige Sätze (%d) in '%s' — übersprungen", total_sentences, title)
        return None

    word_count = sum(
        len(s["text"].split())
        for sec in sections
        for s in sec["sentences"]
    )

    # ── Quiz ──────────────────────────────────
    # Klexikon hat kein Quiz — wir generieren 3 einfache Fragen
    # aus dem Text (Schlagwort-Extraktion)
    quiz = _generate_simple_quiz(title, sections)

    article_id = f"{_slugify(title)}_l{AGE_LEVEL}"

    return {
        "meta": {
            "id":                   article_id,
            "title":                title,
            "subtitle":             subtitle,
            "emoji":                emoji,
            "age_level":            AGE_LEVEL,
            "pattern":              pattern,
            "theme_color":          theme_color,
            "word_count":           word_count,
            "source_wikipedia_url": f"{SOURCE_BASE}{title.replace(' ', '_')}",
            "source_wikipedia_rev": "",
            "generated_at":         datetime.now(timezone.utc).isoformat(),
            "schema_version":       SCHEMA_VERSION,
            "review_flag":          False,
            "review_reason":        "",
            "category_top":         _category_to_top_id(category),
            "category_sub":         "",
            "converted_from":       "klexikon_zim",
        },
        "images":   images,
        "sections": sections,
        "quiz":     quiz,
        "tts_config": {
            "reading_speed_factor":    1.0,
            "pause_after_heading_ms":  600,
            "pause_after_sentence_ms": 300,
            "pause_before_quiz_ms":    1000,
        },
    }


# ─────────────────────────────────────────────
# HTML-Parsing Hilfsfunktionen
# ─────────────────────────────────────────────

def _extract_sections(soup: BeautifulSoup, images: list[dict]) -> list[dict]:
    """
    Extrahiert Abschnitte aus dem Klexikon-HTML.
    Klexikon-Struktur: <h2> trennt Abschnitte, <p> enthält Fließtext.
    """
    sections = []
    sentence_counter = 1
    img_count = len(images)

    # Einleitung: alles vor der ersten <h2>
    intro_paras = []
    for el in soup.find_all(["p", "h2"]):
        if el.name == "h2":
            break
        if el.name == "p":
            text = el.get_text(" ", strip=True)
            if len(text) > 30:
                intro_paras.append(text)

    if intro_paras:
        sentences, sentence_counter = _paras_to_sentences(
            intro_paras, sentence_counter, img_index=0
        )
        if sentences:
            sections.append({
                "id":        "sec_01",
                "heading":   "Einleitung",
                "sentences": sentences,
                "boxes":     [],
            })

    # Weitere Abschnitte
    sec_num = 2
    current_heading = None
    current_paras   = []

    for el in soup.find_all(["h2", "h3", "p"]):
        if el.name in ("h2", "h3"):
            # Vorigen Abschnitt abschließen
            if current_heading and current_paras:
                img_idx = min(sec_num - 2, img_count - 1)
                sentences, sentence_counter = _paras_to_sentences(
                    current_paras, sentence_counter, img_index=max(0, img_idx)
                )
                if sentences:
                    sections.append({
                        "id":        f"sec_{sec_num:02d}",
                        "heading":   current_heading,
                        "sentences": sentences,
                        "boxes":     [],
                    })
                    sec_num += 1
            current_heading = el.get_text(strip=True)
            current_paras   = []
        elif el.name == "p":
            text = el.get_text(" ", strip=True)
            if len(text) > 30:
                current_paras.append(text)

    # Letzten Abschnitt abschließen
    if current_heading and current_paras:
        img_idx = min(sec_num - 2, img_count - 1)
        sentences, sentence_counter = _paras_to_sentences(
            current_paras, sentence_counter, img_index=max(0, img_idx)
        )
        if sentences:
            sections.append({
                "id":        f"sec_{sec_num:02d}",
                "heading":   current_heading,
                "sentences": sentences,
                "boxes":     [],
            })

    return sections


def _paras_to_sentences(
    paras: list[str],
    start_counter: int,
    img_index: int,
) -> tuple[list[dict], int]:
    """
    Splittet Absätze in Sätze und weist IDs + img_index zu.
    Gibt (sentences, neuer_counter) zurück.
    """
    sentences = []
    counter   = start_counter

    for para in paras:
        # Satz-Splitting: nach . ! ? — aber nicht bei Abkürzungen
        raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ])', para)
        for raw in raw_sentences:
            text = raw.strip()
            # Zu kurze oder reine Sonderzeichen-Reste überspringen
            if len(text) < 15 or not re.search(r'[a-zA-ZäöüÄÖÜ]', text):
                continue
            # Satzzeichen am Ende sicherstellen
            if text and text[-1] not in ".!?":
                text += "."
            sentences.append({
                "id":        f"s{counter:03d}",
                "text":      text,
                "img_index": img_index,
            })
            counter += 1

    return sentences, counter


def _extract_images(soup: BeautifulSoup, image_map: dict) -> list[dict]:
    """
    Extrahiert Bilder aus dem HTML und reichert sie mit image_map an.
    Klexikon speichert Bilder als /_assets_/{md5}.jpg
    """
    images = []
    seen_hashes = set()
    img_index = 0

    for img_tag in soup.find_all("img"):
        src = img_tag.get("src", "")
        # Nur /_assets_/-Bilder (keine Icons)
        if "/_assets_/" not in src:
            continue
        # MD5-Hash extrahieren
        match = re.search(r'/_assets_/([a-f0-9]{32})\.(jpg|png|webp)', src)
        if not match:
            continue
        md5 = match.group(1)
        if md5 in seen_hashes:
            continue
        seen_hashes.add(md5)

        # Alt-Text
        alt = img_tag.get("alt", "").strip()
        if not alt or alt.endswith((".jpg", ".png", ".webp")):
            alt = ""

        # Caption aus umgebendem figure/figcaption
        caption = ""
        parent = img_tag.find_parent("figure")
        if parent:
            figcap = parent.find("figcaption")
            if figcap:
                caption = figcap.get_text(" ", strip=True)[:200]

        # image_map anreichern
        map_entry = image_map.get(md5, {})

        images.append({
            "index":          img_index,
            "filename":       map_entry.get("filename", f"{md5}.jpg"),
            "alt":            alt or map_entry.get("alt", ""),
            "caption":        caption or map_entry.get("caption", ""),
            "license":        map_entry.get("license", "CC BY-SA"),
            "license_author": map_entry.get("license_author", "Klexikon"),
            "source_url":     map_entry.get("source_url", ""),
            "wikimedia_id":   map_entry.get("wikimedia_id", ""),
            "thumb_url":      map_entry.get("thumb_url", ""),
            "zim_hash":       md5,
        })
        img_index += 1
        if img_index >= 6:
            break

    return images


def _extract_subtitle(soup: BeautifulSoup, title: str) -> str:
    """Erster Satz des ersten Absatzes als Untertitel."""
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) > 20:
            # Ersten Satz nehmen
            first = re.split(r'(?<=[.!?])\s', text)[0]
            if len(first) < 150:
                return first
    return title


def _detect_category(soup: BeautifulSoup, title: str) -> str:
    """Versucht die Klexikon-Kategorie aus Kategorie-Links im HTML zu lesen."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for cat in CATEGORY_COLORS:
            if cat in href or cat in a.get_text():
                return cat
    return "default"


def _category_to_top_id(category: str) -> str:
    mapping = {
        "Tiere":        "tiere",
        "Pflanzen":     "pflanzen",
        "Länder":       "laender",
        "Städte":       "laender",
        "Geschichte":   "geschichte",
        "Personen":     "personen",
        "Technik":      "technik",
        "Wissenschaft": "technik",
        "Natur":        "erde_natur",
        "Erde":         "erde_natur",
        "Sport":        "kultur",
        "Kultur":       "kultur",
        "Musik":        "kultur",
    }
    return mapping.get(category, "")


def _guess_emoji(title: str, category: str) -> str:
    """Einfaches Emoji-Mapping — wird manuell nachgebessert."""
    cat_emojis = {
        "Tiere": "🐾", "Pflanzen": "🌿", "Länder": "🗺️",
        "Städte": "🏙️", "Geschichte": "🏛️", "Personen": "👤",
        "Technik": "⚙️", "Wissenschaft": "🔬", "Natur": "🌍",
        "Sport": "⚽", "Kultur": "🎭", "Musik": "🎵",
    }
    return cat_emojis.get(category, "📖")


def _generate_simple_quiz(title: str, sections: list[dict]) -> dict:
    """
    Erzeugt 3 einfache Platzhalter-Quizfragen.
    Diese werden später durch KI-generierte Fragen ersetzt — für jetzt
    stellen sie sicher dass das Schema erfüllt ist.
    """
    # Ersten Satz des Artikels als Basis
    first_text = ""
    if sections and sections[0]["sentences"]:
        first_text = sections[0]["sentences"][0]["text"]

    return {
        "heading": "Teste dein Wissen!",
        "questions": [
            {
                "id":          "q01",
                "question":    f"Was hast du über {title} gelernt?",
                "options": [
                    {"key": "A", "text": "Antwort A"},
                    {"key": "B", "text": "Antwort B"},
                    {"key": "C", "text": "Antwort C"},
                ],
                "correct_key": "A",
                "explanation": first_text[:100] if first_text else "",
                "image_quiz":  False,
                "review_flag": True,
            },
            {
                "id":          "q02",
                "question":    f"Was ist besonders an {title}?",
                "options": [
                    {"key": "A", "text": "Antwort A"},
                    {"key": "B", "text": "Antwort B"},
                    {"key": "C", "text": "Antwort C"},
                ],
                "correct_key": "B",
                "explanation": "",
                "image_quiz":  False,
                "review_flag": True,
            },
            {
                "id":          "q03",
                "question":    f"Wo kommt {title} vor?",
                "options": [
                    {"key": "A", "text": "Antwort A"},
                    {"key": "B", "text": "Antwort B"},
                    {"key": "C", "text": "Antwort C"},
                ],
                "correct_key": "C",
                "explanation": "",
                "image_quiz":  False,
                "review_flag": True,
            },
        ],
    }


def _slugify(title: str) -> str:
    slug = title.lower().replace(" ", "_")
    slug = re.sub(r"[äöüß]", lambda m: {"ä":"ae","ö":"oe","ü":"ue","ß":"ss"}[m.group()], slug)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug[:60]


# ─────────────────────────────────────────────
# Checkpoint
# ─────────────────────────────────────────────

def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_checkpoint(path: Path, done: set[str]) -> None:
    path.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────
# Hauptprogramm
# ─────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Klexikon ZIM → Wissensfreund JSON")
    p.add_argument("--zim",        required=True,  type=Path)
    p.add_argument("--image-map",  default=None,   type=Path,
                   help="image_map.json von build_image_map.py (optional)")
    p.add_argument("--out-dir",    default="articles", type=Path)
    p.add_argument("--checkpoint", default=Path("checkpoint_zim.json"), type=Path)
    p.add_argument("--dry-run",    action="store_true",
                   help="Nur 10 Artikel konvertieren, dann stoppen")
    p.add_argument("--limit",      type=int, default=0,
                   help="Max. Artikel (0 = alle)")
    args = p.parse_args()

    # image_map laden
    image_map: dict = {}
    if args.image_map and args.image_map.exists():
        image_map = json.loads(args.image_map.read_text(encoding="utf-8"))
        log.info("Image-Map geladen: %d Einträge", len(image_map))
    else:
        log.warning("Keine image_map.json — Bilder werden ohne Metadaten eingetragen")

    # ZIM öffnen
    log.info("ZIM öffnen: %s", args.zim)
    archive = open_zim(args.zim)
    log.info("ZIM geöffnet")

    # Artikel iterieren
    log.info("Artikel aus ZIM lesen …")
    all_articles = iter_articles(archive)
    log.info("%d Artikel gefunden", len(all_articles))

    # Checkpoint
    done = load_checkpoint(args.checkpoint)
    if done:
        log.info("Checkpoint: %d bereits konvertiert", len(done))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    errors_dir = args.out_dir / "_errors"
    errors_dir.mkdir(exist_ok=True)

    limit      = 10 if args.dry_run else (args.limit or len(all_articles))
    ok = skip = err = 0

    for i, (title, html) in enumerate(all_articles[:limit], 1):
        article_id = f"{_slugify(title)}_l{AGE_LEVEL}"
        log.info("[%d/%d] %s", i, min(limit, len(all_articles)), title)

        if article_id in done:
            skip += 1
            continue

        out_path = args.out_dir / f"{article_id}.json"
        if out_path.exists():
            done.add(article_id)
            skip += 1
            continue

        try:
            article = html_to_article(title, html, image_map, article_idx=i)
        except Exception as e:
            log.error("  Konvertierungsfehler: %s", e)
            err += 1
            continue

        if article is None:
            err += 1
            continue

        out_path.write_text(
            json.dumps(article, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        done.add(article_id)
        save_checkpoint(args.checkpoint, done)
        ok += 1

    log.info("Fertig: %d konvertiert, %d übersprungen, %d Fehler", ok, skip, err)

    # Zusammenfassung
    print(f"\n{'='*50}")
    print(f"ZIM → JSON Konvertierung")
    print(f"  Konvertiert:   {ok}")
    print(f"  Übersprungen:  {skip}")
    print(f"  Fehler:        {err}")
    print(f"  Ausgabe:       {args.out_dir}")
    print(f"\nHINWEIS: Quiz-Fragen sind Platzhalter (review_flag=true).")
    print(f"Diese können später per Claude API nachgeneriert werden.")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
