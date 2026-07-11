"""
image_vision_filter.py
Vision-basierter Bild-Filter: prüft Wikipedia-Bilder mit Gemini Flash auf Kindgerechtheit + Relevanz.

Usage:
  python scripts/image_vision_filter.py --thema biene --wikipedia "Biene"
  python scripts/image_vision_filter.py --thema demokratie --wikipedia "Demokratie" --max 20

Output:
  articles/test_5topics/_images/{thema}_images.json
  Konsole: Kandidaten -> Vision-Analyse -> Hero + Ranking
"""

import argparse
import base64
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

ROOT = Path(__file__).parent.parent
_DOTENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "articles" / "test_5topics" / "_images"

_CACHE_DIR = ROOT / ".cache"
_META_CACHE_PATH = _CACHE_DIR / "image_meta_cache.json"
_DL_CACHE_DIR = _CACHE_DIR / "downloads"

_DL_PAUSE = 3.0                      # Pause zwischen Downloads (Wikimedia-konform: ~20/Min)
_DL_RETRY_WAITS = [15, 30]           # 429-Wartezeiten (Fallback wenn kein Retry-After-Header)

# Speichermessung: frische Downloads protokollieren (für Tier-Entscheidung 600 vs 800)
_download_size_samples: list[dict] = []

def get_download_sizes() -> list[dict]:
    return list(_download_size_samples)

def clear_download_sizes() -> None:
    _download_size_samples.clear()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

WIKIPEDIA_API = "https://de.wikipedia.org/w/api.php"
GEMINI_MODEL = "gemini-2.5-flash"

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
    "qsicon", "favicon",   # SVG-Chrome (Qualitaets-Icons, Favicons)
)
# SVG bleibt erlaubt (didaktische Diagramme); Deko faengt der trenner-agnostische
# Namensfilter (_IMG_SKIP_PREFIXES_KEY/_LOWER) + die Vision-Relevanzpruefung ab.
_IMG_SKIP_EXT = (".webm", ".ogv", ".ogg", ".gif")
# Prefixe trenner-normalisiert (- und Leerzeichen -> _), damit sie auch fuer
# Bindestrich-/Leerzeichen-Titel greifen (z.B. "Flag of X.svg", "Enigma-logo.svg").
_IMG_SKIP_PREFIXES_KEY = tuple(
    p.lower().replace(" ", "_").replace("-", "_") for p in _IMG_SKIP_PREFIXES
)

VISION_SYSTEM_PROMPT = """Du bist ein Bildredakteur für eine Kinder-Wissensapp (Zielgruppe 4–12 Jahre).
Antworte ausschließlich mit gültigem JSON ohne Markdown-Code-Blöcke oder Erklärungen."""

VISION_PROMPT_TEMPLATE = """Analysiere dieses Bild für den Wissensfreund-Artikel zum Thema "{thema}".

Wissensfreund ist eine Kinder-Wissens-App mit drei Altersstufen:
  Stufe 1 = 4–6 Jahre | Stufe 2 = 7–9 Jahre | Stufe 3 = 10–12 Jahre

SCHRITT 1 — GRENZFALL-PRÜFUNG (VOR der Alterseinstufung beantworten):

grenzfall (true | false): Zeigt das Bild eines oder mehrere dieser Merkmale?
  - sichtbares Leid, Schmerz, Krankheit oder Verletzung an Menschen oder Tieren
  - Krankheitssymptome am Körper (Ausschlag, Lähmung, Wunden, Schwellungen, Deformationen)
  - medizinische Eingriffe (Spritzen, Operationen, Verbände, Behandlungen an Personen/Tieren)
  - Tod, Sterben, Trauer oder traumatisierende Situationen
  - historisch ernste Darstellungen (Krieg, Gewalt, Unterdrückung, Gefangenschaft)
  - nackte oder teils nackte Körper in Fotos oder realistisch-expliziten Darstellungen (unabhängig vom Kontext)
  - potenziell beängstigende, erschreckende oder belastende Szenen für Kinder unter 12 Jahren
  → true, wenn mindestens ein Merkmal zutrifft — auch wenn das Bild lehrreich gemeint ist
  → false nur, wenn das Bild eindeutig harmlos und nicht verstörend ist

  KUNST-AUSNAHME: Berühmte klassische Kunstwerke — Gemälde, Zeichnungen und Skulpturen
  alter Meister, wie ein Museum sie ausstellt (z. B. der Vitruvianische Mensch, Statuen
  der Antike, Aktstudien der Kunstgeschichte) — sind KEIN Grenzfall, auch wenn sie den
  menschlichen Körper künstlerisch und unbekleidet zeigen. Sie gelten als Museumsexponate.
  Nur bei EXPLIZIT sexueller Darstellung oder grafischer Gewalt bleibt es grenzfall=true.

grenzfall_grund (string): Falls grenzfall=true — welches Merkmal trifft zu? (1 Satz, konkret)
  Falls grenzfall=false: leerer String "".

SCHRITT 2 — ALTERSFREIGABE (unter Berücksichtigung des grenzfall-Ergebnisses):

  ab_stufe=1  → für ALLE geeignet (auch 4–6 J.): freundliche Tierfotos, Landschaften,
                Alltagsobjekte, lebendige Tiere, fröhliche Szenen.
                Ebenfalls ab_stufe=1: Museumspräparate und Fossilien prähistorischer Tiere
                (Dinosaurierskelette, Ammoniten, Mammuts u. Ä.) — das sind Lern-/
                Ausstellungsobjekte in einem Museum- oder Wissenschaftskontext, keine
                verstörenden Inhalte.
                ACHTUNG: grenzfall=true Bilder dürfen NIEMALS ab_stufe=1 bekommen.
  ab_stufe=2  → ab 7 J.: Tierskelette oder Knochen OHNE Museumskontext (z.B. Tierknochen in
                der Natur, Verwesungsszenen), leichte historische Darstellungen,
                mäßig komplexe Diagramme mit klarem Bezug zum Thema
  ab_stufe=3  → ab 10 J.: detaillierte Anatomie (Organe, Muskeln), komplexe
                wissenschaftliche Darstellungen, historisch ernste Motive
  ab_stufe=0  → GESPERRT (keine Stufe geeignet): Blut, offene Verletzungen, tote Tiere,
                Nacktheit in Fotos/expliziten Darstellungen, Kriegsfotos, grafische Gewalt,
                beängstigende Inhalte

Berühmte klassische Kunstwerke (Gemälde, Zeichnungen, Skulpturen der Kunstgeschichte,
inkl. künstlerischer Aktdarstellungen alter Meister) sind wie Museumsexponate für ALLE
geeignet → ab_stufe=1 (bei ernstem/komplexem Motiv 2). NICHT wegen künstlerischer
Nacktheit sperren oder auf Stufe 3 hochstufen.

Im Zweifel IMMER die höhere Stufe wählen.
Rein dekorative oder inhaltlich leere Grafiken ohne erkennbaren thematischen Bezug → ab_stufe=0.
Thematisch relevante Diagramme, Karten, Querschnitte oder Skizzen (z.B. Vulkanquerschnitt,
Enigma-Schema, Stadtplan Pompeji) erhalten ab_stufe=2 oder 3 — sie sind lehrreich und für
ältere Kinder wertvoll.

SCHRITT 3 — MOTIV-ART (entscheidet über Eignung als Kinderbild):

  ist_symbol_oder_logo (bool): Ist das Bild ein Logo, eine Wortmarke, ein Wappen,
    ein Emblem, ein Organisations-/Auszeichnungszeichen (z. B. UNESCO-Welterbe-Logo),
    ein Piktogramm/Icon (z. B. ein Mikrofon-Symbol), eine reine Text-/Schrifttafel
    oder ein abstraktes Zeichen OHNE gegenständliches Motiv? → true.
    WICHTIG zur Relevanz: Ein Symbol ist NUR dann relevant, wenn es den Gegenstand
    des Artikels DIREKT repräsentiert (z. B. Landesflagge/Wappen bei einem Länder-
    oder Ortsartikel, Vereinslogo beim Verein). Als bloßes Umfeld-Zeichen (fremdes
    Logo, generisches Piktogramm) → relevanz ≤ 2. Als Hero nur, wenn es DAS Wahr-
    zeichen des Themas ist.

  ist_konkret (bool): Zeigt das Bild etwas, das ein JUNGES Kind (4–6 J.) direkt
    erkennt — ein echtes Tier, einen Menschen, einen Ort, einen Gegenstand, eine
    klare Szene? → true.
    Abstrakte Diagramme, Schemata, Mikroskop-/Detailaufnahmen, anatomische
    Zeichnungen, Karten, Symbole → false.

  motiv_key (string): snake_case-Schlüssel für die KONKRETE Szene, damit nur ECHTE
    Dubletten (dasselbe Motiv aus fast gleicher Sicht) denselben key bekommen.
    Unterscheide verschiedene Szenen/Aspekte im key: Nahaufnahme ≠ Luftbild,
    Lavafontäne ≠ Rauchsäule ≠ Krater ≠ Landschaft, Tag ≠ Nacht, Objekt A ≠ Objekt B,
    Skelett ≠ lebendes Tier ≠ Zeichnung. Nur zwei Fotos, die WIRKLICH dasselbe zeigen,
    teilen den key. Im Zweifel lieber feiner unterscheiden als zu grob zusammenwerfen
    (grobe keys werfen später gute, verschiedene Bilder als Schein-Dubletten weg).

SCHRITT 4 — RELEVANZ & HERO:

  relevanz (0–10): Bildet das Bild WIRKLICH den Gegenstand des Artikels ab — die
    Sache, Person oder Szene, um die es im Thema "{thema}" geht?
    - 8–10: zeigt den Kern des Themas konkret und lebendig
    - 5–7: passt, aber nur mittelbar / Randaspekt
    - 0–4: nur lose verwandt, Symbolbild, tangentiales Bauwerk, Nebenfigur
    WICHTIG: Ein Bild, das „irgendwie zum Umfeld gehört" (z. B. ein modernes
    Touristenfoto eines nur am Rande verwandten Bauwerks, das Porträt einer
    Nebenfigur, eine allgemeine Landkarte), ist NICHT relevant — relevanz ≤ 4.
    Ein Symbol/Logo ist nur relevant, wenn es das Thema DIREKT repräsentiert
    (siehe oben); sonst relevanz ≤ 2.

  hero_candidate (bool): Als ERSTES Bild (Hero) geeignet? NUR true, wenn
    ist_konkret=true UND ist_symbol_oder_logo=false UND das Bild den Haupt-
    gegenstand/Protagonisten des Themas klar, attraktiv und repräsentativ zeigt.
    Bauwerke am Rande, Karten, Diagramme, Symbole, Porträts von Nebenfiguren,
    Texttafeln → hero_candidate=false.
    Geht es im Thema um eine PERSON oder ein EREIGNIS, muss der Hero die Person
    selbst bzw. ihre Tätigkeit zeigen (z. B. bei "Spartacus" ein Gladiator, nicht
    ein beliebiger römischer Helm oder eine Waffe der Epoche). Ein bloß
    zeitgenössisches Umfeld-Objekt (Helm, Rüstung, Gebäude, Alltagsgegenstand)
    ANSTELLE des Protagonisten → hero_candidate=false und relevanz ≤ 4.

  bildqualitaet (0–10): Wie GUT ist das Foto als solches — UNABHÄNGIG von der Relevanz.
    Achte auf: scharf und klar (nicht verschwommen/verpixelt), EIN deutlich erkennbares
    Hauptmotiv (nicht überladen, kein winziges Detail), gute Belichtung und lebendige
    Farben, kein störender Text/Wasserzeichen/Rahmen, eindrucksvoll und ansprechend für
    ein Kind.
    - 8–10: eindrucksvoll, klar, würde ein Kind fesseln
    - 5–7: brauchbar, aber unspektakulär
    - 0–4: schwach (unscharf, überladen, fad oder störende Overlays)

  confidence ("hoch" | "mittel" | "niedrig"): Sicherheit deiner ab_stufe-Einschätzung.

  beschreibung (string): Was ist WIRKLICH zu sehen? (1–2 Sätze, sachlich)
    Beschreibe nur sichtbare Objekte, Personen und Handlungen. Schließe keine typische
    Tätigkeit oder Szene hinzu, die das Motiv zwar nahelegt, aber nicht zeigt — im
    Zweifel neutral benennen statt aus dem Kontext zu raten.
    Bei ab_stufe=0: kurze Begründung für die Sperrung.

Antworte NUR mit diesem JSON (kein Markdown, kein Text davor/danach):
{{
  "grenzfall": false,
  "grenzfall_grund": "",
  "ab_stufe": 1,
  "kindgerecht": true,
  "ist_symbol_oder_logo": false,
  "ist_konkret": true,
  "motiv_key": "elefanten_herde",
  "confidence": "hoch",
  "relevanz": 7,
  "bildqualitaet": 8,
  "beschreibung": "...",
  "hero_candidate": false
}}"""

# JSON-Schema für Claude forced tool-use (Vision-Urteil). Feldnamen == Gemini-Ausgabe.
VISION_RESULT_SCHEMA = {
    "type": "object",
    "required": ["grenzfall", "ab_stufe", "ist_symbol_oder_logo", "ist_konkret",
                 "motiv_key", "relevanz", "beschreibung", "hero_candidate"],
    "properties": {
        "grenzfall":            {"type": "boolean"},
        "grenzfall_grund":      {"type": "string"},
        "ab_stufe":             {"type": "integer", "minimum": 0, "maximum": 3},
        "kindgerecht":          {"type": "boolean"},
        "ist_symbol_oder_logo": {"type": "boolean"},
        "ist_konkret":          {"type": "boolean"},
        "motiv_key":            {"type": "string"},
        "confidence":           {"type": "string"},
        "relevanz":             {"type": "integer", "minimum": 0, "maximum": 10},
        "bildqualitaet":        {"type": "integer", "minimum": 0, "maximum": 10},
        "beschreibung":         {"type": "string"},
        "hero_candidate":       {"type": "boolean"},
    },
}


def _analyze_vision_claude(image_bytes: bytes, mime_type: str, thema: str,
                           model: str) -> tuple[dict | None, dict]:
    """Bild-Urteil via Claude (andere KI-Familie, schärferes Motiv-/Relevanz-Urteil).
    Gleiche Rückgabe-Signatur wie analyze_with_vision (Gemini): (result, usage)."""
    import claude_client
    prompt = VISION_PROMPT_TEMPLATE.format(thema=thema)
    try:
        result = claude_client.call_claude_json(
            VISION_SYSTEM_PROMPT, prompt, VISION_RESULT_SCHEMA,
            model=model, image_bytes=image_bytes, image_media_type=mime_type,
            max_tokens=1024, call_name="vision")
    except Exception as e:
        log.warning("  Claude-Vision-Fehler: %s", str(e)[:120])
        return None, {}
    u = {}
    try:
        lu = claude_client.get_last_usage()
        u = {"input_tok": int(lu.get("input_tokens", 0)), "output_tok": int(lu.get("output_tokens", 0)),
             "cached_tok": 0, "thoughts_tok": 0}
    except Exception:
        pass
    return result, u


# ── Request-Zaehler (Modul-Global, fuer Tests) ──────────────────────────────
_wikimedia_req_count: int = 0

def reset_request_count() -> None:
    global _wikimedia_req_count
    _wikimedia_req_count = 0

def get_request_count() -> int:
    return _wikimedia_req_count


# ── Metadaten-Cache (persistent, filename -> {url_orig, artist, license}) ───
_meta_cache: dict | None = None
_meta_cache_dirty: bool = False

def _ensure_meta_cache() -> dict:
    global _meta_cache
    if _meta_cache is None:
        _CACHE_DIR.mkdir(exist_ok=True)
        if _META_CACHE_PATH.exists():
            try:
                _meta_cache = json.loads(_META_CACHE_PATH.read_text(encoding="utf-8"))
                log.debug("Meta-Cache geladen: %d Eintraege", len(_meta_cache))
            except Exception:
                _meta_cache = {}
        else:
            _meta_cache = {}
    return _meta_cache

def save_meta_cache() -> None:
    global _meta_cache_dirty
    if _meta_cache is not None and _meta_cache_dirty:
        _CACHE_DIR.mkdir(exist_ok=True)
        _META_CACHE_PATH.write_text(
            json.dumps(_meta_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _meta_cache_dirty = False
        log.debug("Meta-Cache gespeichert: %d Eintraege", len(_meta_cache))


# ── Wikimedia-Hilfsfunktionen ────────────────────────────────────────────────

def _normalize_file_title(t: str) -> str:
    if t.startswith("Datei:"):
        return "File:" + t[6:]
    return t


def _is_free_license(s: str) -> bool:
    u = s.upper()
    if "-NC" in u or "-ND" in u:
        return False
    return any(k in u for k in ("CC0", "CC BY", "CC-BY", "PUBLIC DOMAIN", "PD-", "GFDL", "FAL"))


def _filename_from_title(title: str) -> str:
    return title.replace("File:", "").replace("Datei:", "").replace(" ", "_")


def _handle_maxlag(resp: requests.Response) -> float:
    if resp.status_code != 200:
        return 0.0
    try:
        data = resp.json()
        err = data.get("error", {})
        if isinstance(err, dict) and err.get("code") == "maxlag":
            lag = float(err.get("lag", 5))
            wait = float(resp.headers.get("Retry-After", min(lag + 1, 30)))
            log.warning("  maxlag=%.1fs -- warte %.0fs ...", lag, wait)
            time.sleep(wait)
            return wait
    except Exception:
        pass
    return 0.0


def _wikimedia_thumb_url(filename: str, width: int = 1280) -> str:
    """Konstruiert Wikimedia-Thumb-URL ohne API-Request (fuer TIF/SVG/Groessen-Fallback)."""
    name = filename.replace(" ", "_")
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    a, ab = h[0], h[:2]
    ext = Path(name).suffix.lower()
    if ext == ".svg":
        thumb_name = f"{width}px-{name}.png"
    elif ext in (".tif", ".tiff"):
        thumb_name = f"{width}px-{name}.jpg"
    else:
        thumb_name = f"{width}px-{name}"
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{a}/{ab}/{name}/{thumb_name}"


def _scale_image(raw_bytes: bytes, max_width: int) -> bytes:
    """Skaliert Bild auf max. max_width px (LANCZOS), gibt JPEG-Bytes zurueck."""
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        # Transparenz (v.a. gerasterte SVG-Diagramme) auf WEISS legen statt auf Schwarz
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, rgba).convert("RGB")
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = max(1, int(img.height * ratio))
        img = img.resize((max_width, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


# ── Metadaten holen: EINE Generator-API-Anfrage pro Artikel ─────────────────

def fetch_image_candidates(
    session: requests.Session,
    wikipedia_title: str,
    max_candidates: int = 50,
) -> list[dict]:
    """Laedt Bild-Metadaten via generator=images (1 Request).
    Kein iiurlwidth → Original-URL (statisches CDN, kein Thumb-Generierungs-Trigger)."""
    global _wikimedia_req_count, _meta_cache_dirty
    cache = _ensure_meta_cache()

    params = {
        "action": "query",
        "format": "json",
        "titles": wikipedia_title,
        "redirects": "1",
        "generator": "images",
        "gimlimit": str(max_candidates),
        "prop": "imageinfo",
        "iiprop": "url|thumburl|extmetadata",
        "iiurlwidth": "1600",      # CDN-Thumbnail (JPEG, max 1600px) statt Original
        "iiextmetadatafilter": "Artist|LicenseShortName|License",
        "maxlag": 5,
    }

    data: dict = {}
    for attempt in range(1, 4):
        try:
            resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
            _wikimedia_req_count += 1
        except Exception as e:
            log.warning("  fetch_image_candidates Verbindungsfehler (V%d): %s", attempt, e)
            time.sleep(5)
            continue

        if _handle_maxlag(resp) > 0:
            continue

        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 15))
            log.warning("  fetch_image_candidates 429 (V%d) -- warte %.0fs", attempt, wait)
            time.sleep(wait)
            continue

        try:
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            log.warning("  fetch_image_candidates Fehler (V%d): %s", attempt, e)
            time.sleep(5)
    else:
        log.warning("  fetch_image_candidates fehlgeschlagen: %s", wikipedia_title)
        return []

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return []

    images: list[dict] = []
    for page in pages.values():
        title = _normalize_file_title(page.get("title", ""))
        t_lower = title.lower()
        t_key = t_lower.replace(" ", "_").replace("-", "_")  # Trenner-agnostisch (SVG-Deko)

        if t_lower.endswith(_IMG_SKIP_EXT):
            continue
        if any(t_key.startswith(skip) for skip in _IMG_SKIP_PREFIXES_KEY):
            continue
        if any(sub in t_key for sub in _IMG_SKIP_LOWER):
            continue

        filename = _filename_from_title(title)

        if filename in cache and "url_orig" in cache[filename]:
            cached = cache[filename]
            images.append({
                "wikimedia_id":  title,
                "filename":      filename,
                "thumb_url":     cached.get("url_1600") or cached["url_orig"],
                "original_url":  cached["url_orig"],
                "license":       cached["license"],
                "license_author": cached["artist"],
            })
            continue

        ii_list = page.get("imageinfo", [])
        if not ii_list:
            continue
        ii = ii_list[0]
        orig_url  = ii.get("url", "")
        api_thumb = ii.get("thumburl", "")               # 1600px CDN (bei SVG bereits PNG-Render)
        if api_thumb:
            thumb_url = api_thumb
        elif t_lower.endswith(".svg"):
            thumb_url = _wikimedia_thumb_url(filename, 1600)  # SVG->PNG serverseitig, nie roh
        else:
            thumb_url = orig_url
        if not orig_url and not thumb_url:
            continue

        meta = ii.get("extmetadata", {})
        license_str = (
            meta.get("LicenseShortName", {}).get("value", "")
            or meta.get("License", {}).get("value", "")
        )
        if not _is_free_license(license_str):
            continue

        raw_author = (
            meta.get("Artist", {}).get("value", "")
            or meta.get("Credit", {}).get("value", "")
        )
        clean_author = re.sub(r"<[^>]+>", "", raw_author).strip()[:80]

        cache[filename] = {
            "url_orig":  orig_url,
            "url_1600":  thumb_url,
            "artist":    clean_author,
            "license":   license_str,
        }
        _meta_cache_dirty = True

        images.append({
            "wikimedia_id":  title,
            "filename":      filename,
            "thumb_url":     thumb_url,     # 1600px CDN-URL (Download-Quelle)
            "original_url":  orig_url,
            "license":       license_str,
            "license_author": clean_author,
        })

    save_meta_cache()
    return images


def fetch_lead_image(session: requests.Session, wikipedia_title: str) -> dict | None:
    """Holt das LEIT-/Infobox-Bild eines Artikels (prop=pageimages) als Prioritäts-
    Kandidat — das kanonische, bekannteste Bild des Lemmas (z. B. die Mona Lisa auf
    dem Artikel 'Mona Lisa', das Selbstbildnis auf 'Leonardo da Vinci'). generator=images
    liefert nur alphabetisch und kappt das Leitbild oft weg; hier holen wir es gezielt."""
    global _wikimedia_req_count
    cache = _ensure_meta_cache()
    # 1) Dateiname des Leitbilds
    p1 = {"action": "query", "format": "json", "titles": wikipedia_title,
          "redirects": "1", "prop": "pageimages", "piprop": "name", "maxlag": 5}
    try:
        r = session.get(WIKIPEDIA_API, params=p1, timeout=30)
        _wikimedia_req_count += 1
        if _handle_maxlag(r) > 0:
            return None
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
    except Exception as e:
        log.warning("  fetch_lead_image (name) Fehler bei '%s': %s", wikipedia_title, e)
        return None

    name = next((page.get("pageimage") for page in pages.values() if page.get("pageimage")), None)
    if not name:
        return None
    file_title = _normalize_file_title("File:" + name)
    t_lower = file_title.lower()
    t_key = t_lower.replace(" ", "_").replace("-", "_")
    if (t_lower.endswith(_IMG_SKIP_EXT)
            or any(t_key.startswith(skip) for skip in _IMG_SKIP_PREFIXES_KEY)
            or any(sub in t_key for sub in _IMG_SKIP_LOWER)):
        return None
    filename = _filename_from_title(file_title)

    def _mk(thumb, orig, lic, author):
        return {"wikimedia_id": file_title, "filename": filename, "thumb_url": thumb,
                "original_url": orig, "license": lic, "license_author": author}

    if filename in cache and "url_orig" in cache[filename]:
        c = cache[filename]
        return _mk(c.get("url_1600") or c["url_orig"], c["url_orig"], c["license"], c["artist"])

    # 2) imageinfo für dieses eine File
    p2 = {"action": "query", "format": "json", "titles": file_title, "prop": "imageinfo",
          "iiprop": "url|thumburl|extmetadata", "iiurlwidth": "1600",
          "iiextmetadatafilter": "Artist|LicenseShortName|License", "maxlag": 5}
    try:
        r = session.get(WIKIPEDIA_API, params=p2, timeout=30)
        _wikimedia_req_count += 1
        if _handle_maxlag(r) > 0:
            return None
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
    except Exception as e:
        log.warning("  fetch_lead_image (info) Fehler bei '%s': %s", file_title, e)
        return None

    for page in pages.values():
        ii = (page.get("imageinfo") or [None])[0]
        if not ii:
            return None
        orig = ii.get("url", "")
        thumb = ii.get("thumburl", "") or orig
        if not orig and not thumb:
            return None
        meta = ii.get("extmetadata", {})
        lic = (meta.get("LicenseShortName", {}).get("value", "")
               or meta.get("License", {}).get("value", ""))
        if not _is_free_license(lic):
            return None
        author = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()[:80]
        cache[filename] = {"url_orig": orig, "url_1600": thumb, "artist": author, "license": lic}
        save_meta_cache()
        return _mk(thumb, orig, lic, author)
    return None


# ── Download: Original + lokale Skalierung (300px + 800px) ──────────────────

def _do_download(session: requests.Session, url: str) -> bytes | None:
    """HTTP-Download mit 429-Retry und 20-MB-Abbruch. Gibt Rohbytes zurueck."""
    for attempt in range(1, 3):
        try:
            resp = session.get(url, timeout=60, stream=True)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After",
                             _DL_RETRY_WAITS[min(attempt - 1, len(_DL_RETRY_WAITS) - 1)]))
                log.warning("  Download 429 (V%d/2) -- warte %ds", attempt, int(wait))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            chunks, total = [], 0
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                total += len(chunk)
                if total > 20 * 1024 * 1024:
                    log.warning("  Download >20 MB abgebrochen: %s", url[:80])
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
        except Exception as e:
            if attempt < 2 and "429" not in str(e):
                time.sleep(5)
                continue
            log.warning("  Download-Fehler: %s", e)
            return None
    return None


def download_image(session: requests.Session, url: str) -> bytes | None:
    """Laedt 1600px-CDN-Thumbnail (via iiurlwidth=1600 aus fetch_image_candidates).
    Skaliert lokal: 800px (Vision, Rueckgabe), 300px (Standard-Tier), 1600px (Max-Tier, raw).
    Misst 600px fuer Speicher-Entscheidung (nicht gecacht).
    Cache: .cache/downloads/{md5(url)}_800.jpg + _300.jpg + _1600.jpg."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_800 = _DL_CACHE_DIR / f"{cache_key}_800.jpg"

    if cache_800.exists():
        return cache_800.read_bytes()

    raw = _do_download(session, url)
    if raw is None:
        return None

    try:
        _DL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        scaled_800 = _scale_image(raw, 800)
        scaled_300 = _scale_image(raw, 300)

        cache_800.write_bytes(scaled_800)
        (_DL_CACHE_DIR / f"{cache_key}_300.jpg").write_bytes(scaled_300)
        (_DL_CACHE_DIR / f"{cache_key}_1600.jpg").write_bytes(raw)   # Max-Tier

        # Speichermessung: 600px messen, nicht cachen (fuer 600-vs-800-Entscheidung)
        scaled_600 = _scale_image(raw, 600)
        url_path = urllib.parse.urlparse(url).path
        fname = Path(url_path).name[:40]
        _download_size_samples.append({
            "filename": fname,
            "sz_300":   len(scaled_300),
            "sz_600":   len(scaled_600),
            "sz_800":   len(scaled_800),
            "sz_1600":  len(raw),
        })
        log.debug("  Tier-KB [%s]: 300=%d 600=%d 800=%d 1600=%d KB",
                  fname[:25],
                  len(scaled_300) // 1024, len(scaled_600) // 1024,
                  len(scaled_800) // 1024, len(raw) // 1024)

        return scaled_800
    except Exception as e:
        log.warning("  Skalierung fehlgeschlagen: %s", e)
        return None


def prefetch_images(
    session: requests.Session,
    candidates: list[dict],
    max_workers: int = 1,  # ignoriert: sequentieller Download
) -> dict[str, bytes | None]:
    """Laedt Bilder sequentiell mit kurzer Pause (max_workers ignoriert)."""
    results: dict[str, bytes | None] = {}
    for i, img in enumerate(candidates):
        results[img["filename"]] = download_image(session, img["thumb_url"])
        if i < len(candidates) - 1:
            time.sleep(_DL_PAUSE)
    return results


# ── Vision-Analyse ───────────────────────────────────────────────────────────

def analyze_with_vision(
    client: genai.Client, image_bytes: bytes, mime_type: str, thema: str,
    model: str | None = None,
) -> tuple[dict | None, dict]:
    """Gibt (result, usage_dict) zurueck. usage_dict kann {} sein.
    Provider aus stage_models["vision"]: 'anthropic' -> Claude (claude_client),
    sonst Gemini (unveraendert). model=None -> Default GEMINI_MODEL."""
    try:
        import stage_models
        _vcfg = stage_models.get_stage_config("vision")
    except Exception:
        _vcfg = {"provider": "gemini", "model": None}
    if _vcfg.get("provider") == "anthropic":
        # Bei Claude den in stage_models konfigurierten Modellnamen nutzen
        # (der uebergebene 'model' ist ggf. ein Gemini-Name aus dem Aufrufer).
        return _analyze_vision_claude(image_bytes, mime_type, thema, _vcfg.get("model"))
    prompt = VISION_PROMPT_TEMPLATE.format(thema=thema)
    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=model or GEMINI_MODEL,
                contents=[
                    types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes)),
                    types.Part(text=prompt),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=VISION_SYSTEM_PROMPT,
                    temperature=0.1,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            um = getattr(response, "usage_metadata", None)
            usage: dict = {}
            if um:
                usage = {
                    "input_tok":  int(getattr(um, "prompt_token_count", 0) or 0),
                    "output_tok": int(getattr(um, "candidates_token_count", 0) or 0),
                    "cached_tok": int(getattr(um, "cached_content_token_count", 0) or 0),
                    "thoughts_tok": 0,
                }
            text = response.text
            if text is None:
                parts = []
                for cand in getattr(response, "candidates", []):
                    for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                        if not getattr(part, "thought", False) and getattr(part, "text", None):
                            parts.append(part.text)
                text = "".join(parts) or ""
            text = text.strip()
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
            return json.loads(text), usage
        except json.JSONDecodeError as e:
            log.warning("  JSON-Parse-Fehler: %s", e)
            return None, {}
        except Exception as e:
            err = str(e)
            e_low = err.lower()
            is_transient = (
                "503" in err or "429" in err or "unavailable" in e_low or "overloaded" in e_low
                or "timeout" in e_low or "timed out" in e_low or "deadline" in e_low
                or "connection" in e_low or "reset" in e_low
            )
            if attempt < 2 and is_transient:
                log.warning("  Vision transient (Versuch 1/2): %s -- warte 30s ...", err[:80])
                time.sleep(30)
                continue
            log.warning("  Vision-Fehler: %s", e)
            return None, {}
    return None, {}


OPUS_RECHECK_SYSTEM = (
    "Du bist ein strenger Bildprüfer für eine Kinder-Wissens-App (4–12 Jahre). "
    "Antworte ausschließlich mit gültigem JSON ohne Markdown-Blöcke."
)

OPUS_RECHECK_PROMPT = """Prüfe dieses Bild für Wissensfreund (Thema: "{thema}") nach der Altersfreigabe-Skala:

  ab_stufe=1  → eindeutig für ALLE (auch 4–6 J.): freundliche Tierfotos, Landschaften, Objekte;
                auch Museumspräparate/Fossilien prähistorischer Tiere (Dino-Skelette, Ammoniten,
                Mammuts) → Lern-/Ausstellungsobjekte → ab_stufe=1 (sofern kein grenzfall=true)
  ab_stufe=2  → ab 7 J.: Knochen/Skelette OHNE Museumskontext, leichte historische Darstellungen
  ab_stufe=3  → ab 10 J.: Organe, detaillierte Anatomie, wissenschaftlich/historisch ernst
  ab_stufe=0  → GESPERRT: Blut, Gewalt, Nacktheit in Fotos/expliziten Darstellungen, Kriegsfotos, verstörende Inhalte

AUSNAHME: Berühmte klassische Kunstwerke (Gemälde/Zeichnungen/Skulpturen der Kunstgeschichte,
inkl. künstlerischer Aktdarstellungen alter Meister, z. B. der Vitruvianische Mensch) sind wie
Museumsexponate für ALLE geeignet → ab_stufe=1 (bei ernstem Motiv 2), NICHT sperren/hochstufen.

Sei STRENGER als ein durchschnittlicher Prüfer. Im Zweifel höhere Stufe vergeben.

Antworte NUR mit JSON:
{{"ab_stufe": 1, "beschreibung": "..."}}"""


def load_cached_image_bytes(url: str) -> bytes | None:
    """Laedt 800px-Version aus dem lokalen Download-Cache (kein Netz-Request)."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_800 = _DL_CACHE_DIR / f"{cache_key}_800.jpg"
    return cache_800.read_bytes() if cache_800.exists() else None


def opus_recheck(
    api_key: str,
    image_bytes: bytes,
    thema: str,
    model: str = "claude-opus-4-8",
) -> tuple[int | None, str, dict]:
    """Zweitprüfung mit einem Anthropic-Vision-Modell (strenger Vision-Prompt).

    model: Anthropic-Modellname (default claude-opus-4-8; via
    stage_models.image_recheck_model gesteuert).
    Gibt (ab_stufe, beschreibung, usage_dict) zurück.
    ab_stufe=None bei Fehler (Gemini-Urteil beibehalten).
    """
    try:
        import anthropic
    except ImportError:
        log.warning("opus_recheck: 'anthropic'-Paket fehlt — Recheck uebersprungen")
        return None, "", {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = OPUS_RECHECK_PROMPT.format(thema=thema)
        response = client.messages.create(
            model=model,
            max_tokens=256,
            system=OPUS_RECHECK_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        usage = {
            "input_tok":  response.usage.input_tokens,
            "output_tok": response.usage.output_tokens,
        }
        text = response.content[0].text.strip()
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        result = json.loads(text)
        return int(result.get("ab_stufe", 0)), result.get("beschreibung", ""), usage
    except Exception as e:
        log.warning("opus_recheck Fehler: %s", e)
        return None, "", {}


# ── Haupt-Lauf ───────────────────────────────────────────────────────────────

def run(thema: str, wikipedia_title: str, max_images: int = 30) -> None:
    load_dotenv(_DOTENV_PATH)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    print(f"\n=== Bild-Filter: {thema} (Wikipedia: \"{wikipedia_title}\") ===\n")

    session = requests.Session()
    session.headers["User-Agent"] = (
        "WissensfreundImageFilter/1.0 (az@expansionssupport.de; Kinderwissens-App)"
    )
    client = genai.Client(api_key=api_key)

    req_before = get_request_count()

    # 1. Kandidaten laden (1 Generator-API-Request)
    log.info("Lade Bild-Kandidaten via generator=images ...")
    candidates = fetch_image_candidates(session, wikipedia_title, max_candidates=50)
    req_after_meta = get_request_count()
    print(f"Kandidaten nach Dateiname- + Lizenz-Filter: {len(candidates)}")
    print(f"Wikimedia-API-Requests (Metadaten): {req_after_meta - req_before}")

    if not candidates:
        print("Keine Bilder gefunden.")
        return

    to_check = candidates[:max_images]
    print(f"-> {len(to_check)} Bilder fuer Vision-Check (sequentiell, {_DL_PAUSE}s Pause)\n")

    # 2+3. Download + Vision-Check sequentiell (integrierte Schleife)
    accepted: list[dict] = []
    rejected: list[dict] = []
    dl_fresh = 0

    for i, img in enumerate(to_check, 1):
        fname = img["filename"]
        print(f"  [{i}/{len(to_check)}] {fname[:60]}")

        cache_key = hashlib.md5(img["thumb_url"].encode()).hexdigest()
        was_cached = (_DL_CACHE_DIR / f"{cache_key}_800.jpg").exists()

        image_bytes = download_image(session, img["thumb_url"])
        if not was_cached:
            dl_fresh += 1
            if i < len(to_check):
                time.sleep(_DL_PAUSE)

        if image_bytes is None:
            rejected.append({**img, "reason": "Download fehlgeschlagen",
                             "ablehnungsgrund": "Download fehlgeschlagen"})
            print("    [X] Download fehlgeschlagen")
            continue

        result, _vision_usage = analyze_with_vision(client, image_bytes, "image/jpeg", thema)

        if result is None:
            rejected.append({**img, "reason": "Vision-Fehler", "ablehnungsgrund": "Vision-API-Fehler"})
            print("    [X] Vision-Fehler")
        else:
            ab_stufe      = result.get("ab_stufe", 0)
            grenzfall     = result.get("grenzfall", False)
            grenzfall_grund = result.get("grenzfall_grund", "")
            confidence    = result.get("confidence", "hoch")
            relevanz      = result.get("relevanz", 0)
            bildqualitaet = result.get("bildqualitaet", 5)
            beschreibung  = result.get("beschreibung", "")
            hero          = result.get("hero_candidate", False)

            # grenzfall=true verhindert ab_stufe=1
            if grenzfall and ab_stufe == 1:
                ab_stufe = 2

            if ab_stufe == 0:
                rejected.append({**img, "reason": f"gesperrt: {beschreibung}",
                                 "ablehnungsgrund": beschreibung})
                print(f"    [0] GESPERRT: {beschreibung[:80]}")
            else:
                accepted.append({**img, "ab_stufe": ab_stufe,
                                 "grenzfall": grenzfall, "grenzfall_grund": grenzfall_grund,
                                 "confidence": confidence, "relevanz": relevanz,
                                 "bildqualitaet": bildqualitaet,
                                 "hero_candidate": hero, "beschreibung": beschreibung})
                gz_marker   = " [GZ]" if grenzfall else ""
                conf_marker = f" conf={confidence}" if confidence != "hoch" else ""
                hero_marker = " [HERO]" if hero else ""
                print(f"    [S{ab_stufe}]{gz_marker}{conf_marker} [{relevanz}] {beschreibung[:70]}{hero_marker}")

    # 4. Sortieren + Hero bestimmen
    accepted.sort(key=lambda x: (-x["relevanz"], -int(x.get("hero_candidate", False))))
    for rank, a in enumerate(accepted, 1):
        a["rank"] = rank

    hero_img = next((a for a in accepted if a.get("hero_candidate", False)), accepted[0] if accepted else None)

    # 5. Zusammenfassung
    total_req = get_request_count() - req_before
    dl_total = len(to_check)
    dl_cached = dl_total - dl_fresh
    print(f"\n{'='*60}")
    print(f"Ergebnis: {len(accepted)} akzeptiert / {len(rejected)} abgelehnt")
    print(f"Downloads: {dl_total} gesamt ({dl_cached} aus Cache, {dl_fresh} frisch)")
    print(f"Wikimedia-API-Requests gesamt: {total_req}")
    if hero_img:
        print(f"Hero-Bild: {hero_img['filename']} (Relevanz: {hero_img['relevanz']})")
    print()

    if accepted:
        print("Relevanz-Ranking:")
        for a in accepted:
            hero_marker = " [H]" if a.get("hero_candidate", False) else ""
            print(f"  {a['rank']:2}. [S{a['ab_stufe']}][{a['relevanz']}]{hero_marker} {a['filename'][:50]}")
            print(f"      {a['beschreibung'][:90]}")

    if rejected:
        print(f"\nAbgelehnt ({len(rejected)}):")
        for r in rejected:
            print(f"  [X] {r['filename'][:50]}")
            print(f"    Grund: {r.get('ablehnungsgrund') or r.get('reason', '')}")

    # 6. JSON speichern
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{thema}_images.json"

    output = {
        "thema": thema,
        "wikipedia_title": wikipedia_title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "candidates_in":       len(candidates),
            "vision_checked":      len(to_check),
            "accepted":            len(accepted),
            "rejected":            len(rejected),
            "wikimedia_api_requests": total_req,
            "downloads_fresh":     dl_fresh,
            "downloads_cached":    dl_cached,
        },
        "hero": {
            "filename":    hero_img["filename"],
            "relevanz":    hero_img["relevanz"],
            "beschreibung": hero_img["beschreibung"],
            "thumb_url":   hero_img["thumb_url"],
        } if hero_img else None,
        "accepted": [
            {
                "rank":            a["rank"],
                "filename":        a["filename"],
                "ab_stufe":        a["ab_stufe"],
                "grenzfall":       a.get("grenzfall", False),
                "grenzfall_grund": a.get("grenzfall_grund", ""),
                "relevanz":        a["relevanz"],
                "hero_candidate":  a.get("hero_candidate", False),
                "beschreibung":    a["beschreibung"],
                "license":         a["license"],
                "license_author":  a["license_author"],
                "thumb_url":       a["thumb_url"],
                "wikimedia_id":    a["wikimedia_id"],
            }
            for a in accepted
        ],
        "rejected": [
            {
                "filename":       r["filename"],
                "reason":         r.get("reason", ""),
                "ablehnungsgrund": r.get("ablehnungsgrund", ""),
                "wikimedia_id":   r.get("wikimedia_id", ""),
            }
            for r in rejected
        ],
    }

    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGespeichert: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vision-basierter Bild-Filter fuer Wissensfreund")
    parser.add_argument("--thema", required=True, help="Slug des Themas (z.B. biene)")
    parser.add_argument("--wikipedia", required=True, help="Exakter Wikipedia-Artikeltitel (z.B. 'Biene')")
    parser.add_argument("--max", type=int, default=30, help="Max. Bilder fuer Vision-Check (default: 30)")
    args = parser.parse_args()
    run(args.thema, args.wikipedia, args.max)
