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

_MAX_ORIG_BYTES = 15 * 1024 * 1024  # 15 MB: über dieser Grenze → 1280px-Fallback
_DL_PAUSE = 0.4                      # Pause zwischen sequentiellen Downloads (s)
_DL_RETRY_WAITS = [15, 30]           # 429-Wartezeiten; Originale selten gedrosselt

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
    "diagram", "schema", "chart",
)
_IMG_SKIP_EXT = (".webm", ".ogv", ".ogg", ".svg", ".gif")

VISION_SYSTEM_PROMPT = """Du bist ein Bildredakteur für eine Kinder-Wissensapp (Zielgruppe 4–12 Jahre).
Antworte ausschließlich mit gültigem JSON ohne Markdown-Code-Blöcke oder Erklärungen."""

VISION_PROMPT_TEMPLATE = """Analysiere dieses Bild für den Wissensfreund-Artikel zum Thema "{thema}".

Wissensfreund ist eine Kinder-Wissens-App mit drei Altersstufen:
  Stufe 1 = 4–6 Jahre | Stufe 2 = 7–9 Jahre | Stufe 3 = 10–12 Jahre

Vergib eine ALTERSFREIGABE (ab_stufe):

  ab_stufe=1  → für ALLE geeignet (auch 4–6 J.): freundliche Tierfotos, Landschaften,
                Alltagsobjekte, lebendige Tiere, fröhliche Szenen
  ab_stufe=2  → ab 7 J.: Skelette oder Fossilien mit Lehrcharakter, leichte historische
                Darstellungen, mäßig komplexe Diagramme mit klarem Bezug zum Thema
  ab_stufe=3  → ab 10 J.: detaillierte Anatomie (Organe, Muskeln), komplexe
                wissenschaftliche Darstellungen, historisch ernste Motive
  ab_stufe=0  → GESPERRT (keine Stufe geeignet): Blut, offene Verletzungen, tote Tiere,
                Nacktheit, Kriegsfotos, grafische Gewalt, beängstigende Inhalte

WICHTIG — Strenge für ab_stufe=1 (4–6 Jahre):
NUR freundliche, klare, nicht verstörende Bilder. Skelette, Fossilien, anatomische
Darstellungen, ernste historische Motive → mindestens ab_stufe=2 oder 3.
Im Zweifel IMMER die höhere Stufe wählen.

Abstrakte Diagramme ohne erkennbares Motiv, reine Texttafeln, leere Karten → ab_stufe=0.

Beantworte außerdem:

  relevanz (0–10): Wie gut passt das Bild zum Thema "{thema}"?
    10=perfekt, 7–9=sehr gut, 5–6=passabel, 0–4=kaum relevant

  confidence ("hoch" | "mittel" | "niedrig"): Wie sicher bist du in der ab_stufe-Einschätzung?
    "hoch"    = klarer Fall, kein Zweifel
    "mittel"  = Grenzfall, Einschätzung aber vertretbar
    "niedrig" = echte Unsicherheit ob das Bild für die gewählte Stufe geeignet ist
    Im Zweifel auf "niedrig" setzen — das System stuft dann konservativ hoch.

  beschreibung (string): Was ist auf dem Bild zu sehen? (1–2 Sätze, sachlich)
    Bei ab_stufe=0: kurze Begründung für die Sperrung.

  hero_candidate (bool): Wäre das Bild als erstes Bild (Hero) geeignet?
    Kriterien: klar erkennbares Motiv, attraktiv, repräsentativ für das Thema, gute Bildqualität.

Antworte NUR mit diesem JSON (kein Markdown, kein Text davor/danach):
{{
  "ab_stufe": 1,
  "kindgerecht": true,
  "confidence": "hoch",
  "relevanz": 7,
  "beschreibung": "...",
  "hero_candidate": false
}}"""

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
    if img.mode not in ("RGB", "L"):
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
        "iiprop": "url|extmetadata",
        # KEIN iiurlwidth: Original-URL verwenden, kein serverseitiger Thumbnail-Generator
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

        if t_lower.endswith(_IMG_SKIP_EXT):
            continue
        if any(title.startswith(skip) for skip in _IMG_SKIP_PREFIXES):
            continue
        if any(sub in t_lower for sub in _IMG_SKIP_LOWER):
            continue

        filename = _filename_from_title(title)

        # Cache-Treffer: nur neue url_orig-Eintraege verwenden (url_800-Eintraege neu laden)
        if filename in cache and "url_orig" in cache[filename]:
            cached = cache[filename]
            images.append({
                "wikimedia_id": title,
                "filename":     filename,
                "thumb_url":    cached["url_orig"],
                "license":      cached["license"],
                "license_author": cached["artist"],
            })
            continue

        ii_list = page.get("imageinfo", [])
        if not ii_list:
            continue
        ii = ii_list[0]
        orig_url = ii.get("url", "")
        if not orig_url:
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

        cache[filename] = {"url_orig": orig_url, "artist": clean_author, "license": license_str}
        _meta_cache_dirty = True

        images.append({
            "wikimedia_id": title,
            "filename":     filename,
            "thumb_url":    orig_url,
            "license":      license_str,
            "license_author": clean_author,
        })

    save_meta_cache()
    return images


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
    """Laedt Original-Bild, skaliert lokal auf 800px + 300px (LANCZOS).
    Gibt 800px-JPEG-Bytes zurueck (fuer Vision-Analyse).
    Cache: .cache/downloads/{md5(url)}_800.jpg + _300.jpg."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_800 = _DL_CACHE_DIR / f"{cache_key}_800.jpg"

    if cache_800.exists():
        return cache_800.read_bytes()

    # TIF/SVG: kein Riesen-Original — 1280px-Thumb via konstruierter URL
    url_path = urllib.parse.urlparse(url).path
    filename_part = Path(url_path).name
    ext_lower = Path(url_path).suffix.lower()

    use_fallback = ext_lower in (".tif", ".tiff", ".svg")
    download_url = _wikimedia_thumb_url(filename_part, 1280) if use_fallback else url

    raw = _do_download(session, download_url)
    if raw is None:
        return None

    # Groessen-Schutz: Original >15 MB → 1280px-Fallback
    if len(raw) > _MAX_ORIG_BYTES and not use_fallback:
        log.warning("  Original %.1f MB > Limit → 1280px-Fallback: %s",
                    len(raw) / (1024 * 1024), filename_part)
        raw = _do_download(session, _wikimedia_thumb_url(filename_part, 1280))
        if raw is None:
            return None

    try:
        _DL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        scaled_800 = _scale_image(raw, 800)
        scaled_300 = _scale_image(raw, 300)
        cache_800.write_bytes(scaled_800)
        (_DL_CACHE_DIR / f"{cache_key}_300.jpg").write_bytes(scaled_300)
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
    client: genai.Client, image_bytes: bytes, mime_type: str, thema: str
) -> tuple[dict | None, dict]:
    """Gibt (result, usage_dict) zurueck. usage_dict kann {} sein."""
    prompt = VISION_PROMPT_TEMPLATE.format(thema=thema)
    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
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
            if attempt < 2 and ("503" in err or "unavailable" in err.lower()):
                log.warning("  Vision 503 (Versuch 1/2) -- warte 30s ...")
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

  ab_stufe=1  → eindeutig für ALLE (auch 4–6 J.): freundliche Tierfotos, Landschaften, Objekte
  ab_stufe=2  → ab 7 J.: Skelette/Fossilien lehrreich, leichte historische Darstellungen
  ab_stufe=3  → ab 10 J.: Organe, detaillierte Anatomie, wissenschaftlich/historisch ernst
  ab_stufe=0  → GESPERRT: Blut, Gewalt, Nacktheit, Kriegsfotos, verstörende Inhalte

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
) -> tuple[int | None, str, dict]:
    """Zweitprüfung mit claude-opus-4-8 (strenger Vision-Prompt).

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
            model="claude-opus-4-8",
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
            ab_stufe = result.get("ab_stufe", 0)
            confidence = result.get("confidence", "hoch")
            relevanz = result.get("relevanz", 0)
            beschreibung = result.get("beschreibung", "")
            hero = result.get("hero_candidate", False)
            if ab_stufe == 0:
                rejected.append({**img, "reason": f"gesperrt: {beschreibung}",
                                 "ablehnungsgrund": beschreibung})
                print(f"    [0] GESPERRT: {beschreibung[:80]}")
            else:
                accepted.append({**img, "ab_stufe": ab_stufe, "confidence": confidence,
                                 "relevanz": relevanz, "hero_candidate": hero,
                                 "beschreibung": beschreibung})
                conf_marker = f" conf={confidence}" if confidence != "hoch" else ""
                hero_marker = " [HERO]" if hero else ""
                print(f"    [S{ab_stufe}]{conf_marker} [{relevanz}] {beschreibung[:70]}{hero_marker}")

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
                "rank":           a["rank"],
                "filename":       a["filename"],
                "ab_stufe":       a["ab_stufe"],
                "relevanz":       a["relevanz"],
                "hero_candidate": a.get("hero_candidate", False),
                "beschreibung":   a["beschreibung"],
                "license":        a["license"],
                "license_author": a["license_author"],
                "thumb_url":      a["thumb_url"],
                "wikimedia_id":   a["wikimedia_id"],
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
