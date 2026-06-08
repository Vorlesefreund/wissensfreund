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
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).parent.parent
_DOTENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "articles" / "test_5topics" / "_images"

_CACHE_DIR = ROOT / ".cache"
_META_CACHE_PATH = _CACHE_DIR / "image_meta_cache.json"
_DL_CACHE_DIR = _CACHE_DIR / "downloads"

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

Beantworte folgende Punkte:

1. kindgerecht (bool): Ist das Bild für Kinder (4–12 Jahre) geeignet?
   NICHT kindgerecht: Blut, Gewalt, tote Tiere, Nacktheit, detaillierte Anatomie (Organe, Skelette),
   Kriegsfotos, grafische Verletzungen, beängstigende Inhalte.
   Abstrakte Diagramme, reine Texttafeln, leere Karten → ebenfalls NICHT geeignet.

2. ablehnungsgrund (string): Wenn kindgerecht=false, kurze Begründung (1 Satz). Sonst leer "".

3. beschreibung (string): Was ist auf dem Bild zu sehen? (1–2 Sätze, sachlich, für Redakteure)

4. relevanz (int 0–10): Wie gut passt das Bild zum Thema "{thema}" in einer Kinder-Wissens-App?
   10 = perfekt (zeigt Thema klar, schön, begeisternd für Kinder)
   7–9 = sehr gut geeignet
   5–6 = passabel
   0–4 = kaum relevant

5. hero_tauglich (bool): Wäre das Bild als erstes Bild (Hero) geeignet?
   Kriterien: klar erkennbares Motiv, attraktiv, repräsentativ für das Thema, gute Bildqualität.

Antworte NUR mit diesem JSON (kein Markdown, kein Text davor/danach):
{{
  "kindgerecht": true,
  "ablehnungsgrund": "",
  "beschreibung": "...",
  "relevanz": 7,
  "hero_tauglich": false
}}"""

# ── Request-Zaehler (Modul-Global, fuer Tests) ──────────────────────────────
_wikimedia_req_count: int = 0

def reset_request_count() -> None:
    global _wikimedia_req_count
    _wikimedia_req_count = 0

def get_request_count() -> int:
    return _wikimedia_req_count


# ── Metadaten-Cache (persistent, filename -> {url_800, artist, license}) ────
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


def _mime_from_url(url: str) -> str:
    lower = url.lower().split("?")[0]
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _handle_maxlag(resp: requests.Response) -> float:
    """Prueft auf maxlag-Fehler. Gibt Wartezeit zurueck (0 = kein maxlag)."""
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


# ── Metadaten holen: EINE Generator-API-Anfrage pro Artikel ─────────────────

def fetch_image_candidates(
    session: requests.Session,
    wikipedia_title: str,
    max_candidates: int = 50,
) -> list[dict]:
    """Laedt Bild-Metadaten via generator=images (1 Request statt 2)."""
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
        "iiurlwidth": 800,
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

        # Cache-Treffer: Metadaten bereits bekannt
        if filename in cache:
            cached = cache[filename]
            images.append({
                "wikimedia_id": title,
                "filename": filename,
                "thumb_url": cached["url_800"],
                "license": cached["license"],
                "license_author": cached["artist"],
            })
            continue

        ii_list = page.get("imageinfo", [])
        if not ii_list:
            continue
        ii = ii_list[0]
        thumb_url = ii.get("thumburl") or ii.get("url", "")
        if not thumb_url:
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

        cache[filename] = {"url_800": thumb_url, "artist": clean_author, "license": license_str}
        _meta_cache_dirty = True

        images.append({
            "wikimedia_id": title,
            "filename": filename,
            "thumb_url": thumb_url,
            "license": license_str,
            "license_author": clean_author,
        })

    save_meta_cache()
    return images


# ── Download mit lokaler Datei-Cache ────────────────────────────────────────

_DL_RETRY_WAITS = [30, 60, 120]


def download_image(session: requests.Session, url: str) -> bytes | None:
    """Laedt Bild herunter — lokaler Cache unter .cache/downloads/{md5}{ext}."""
    url_path = urllib.parse.urlparse(url).path
    ext = Path(url_path).suffix or ".jpg"
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_file = _DL_CACHE_DIR / f"{cache_key}{ext}"

    if cache_file.exists():
        return cache_file.read_bytes()

    for attempt in range(1, 4):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After",
                             _DL_RETRY_WAITS[min(attempt - 1, len(_DL_RETRY_WAITS) - 1)]))
                log.warning("  Download 429 (V%d/3) -- warte %ds", attempt, int(wait))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            if len(resp.content) > 18 * 1024 * 1024:
                log.warning("  Bild >18 MB, uebersprungen: %s", url)
                return None
            _DL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(resp.content)
            return resp.content
        except Exception as e:
            if attempt < 3 and "429" not in str(e):
                time.sleep(5)
                continue
            log.warning("  Download-Fehler: %s", e)
            return None
    return None


def _prefetch_images(session: requests.Session, candidates: list[dict], max_workers: int = 2) -> dict[str, bytes | None]:
    """Laedt bis zu max_workers Bilder parallel (nutzt Cache)."""
    results: dict[str, bytes | None] = {}

    def _fetch(img: dict) -> tuple[str, bytes | None]:
        data = download_image(session, img["thumb_url"])
        return img["filename"], data

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch, img): img for img in candidates}
        for fut in as_completed(futures):
            fname, data = fut.result()
            results[fname] = data
    return results


# ── Vision-Analyse ───────────────────────────────────────────────────────────

def analyze_with_vision(client: genai.Client, image_bytes: bytes, mime_type: str, thema: str) -> dict | None:
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
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.warning("  JSON-Parse-Fehler: %s", e)
            return None
        except Exception as e:
            err = str(e)
            if attempt < 2 and ("503" in err or "unavailable" in err.lower()):
                log.warning("  Vision 503 (Versuch 1/2) -- warte 30s ...")
                time.sleep(30)
                continue
            log.warning("  Vision-Fehler: %s", e)
            return None
    return None


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

    # 1. Kandidaten laden (1 Generator-API-Request statt 2)
    log.info("Lade Bild-Kandidaten via generator=images ...")
    candidates = fetch_image_candidates(session, wikipedia_title, max_candidates=50)
    req_after_meta = get_request_count()
    print(f"Kandidaten nach Dateiname- + Lizenz-Filter: {len(candidates)}")
    print(f"Wikimedia-API-Requests (Metadaten): {req_after_meta - req_before}")

    if not candidates:
        print("Keine Bilder gefunden.")
        return

    to_check = candidates[:max_images]
    print(f"-> {len(to_check)} Bilder fuer Vision-Check")

    # 2. Bilder parallel vorladen (2 Workers, Cache-First)
    print("   Lade Bilder (max. 2 parallel, lokaler Cache) ...")
    image_cache = _prefetch_images(session, to_check, max_workers=2)
    req_after_dl = get_request_count()
    cached_count = sum(1 for img in to_check
                       if (_DL_CACHE_DIR / f"{hashlib.md5(img['thumb_url'].encode()).hexdigest()}{Path(urllib.parse.urlparse(img['thumb_url']).path).suffix or '.jpg'}").exists())
    print(f"   Wikimedia-Downloads: {sum(1 for v in image_cache.values() if v is not None)} "
          f"(davon aus Cache: {cached_count})\n")

    # 3. Vision-Check pro Bild
    accepted = []
    rejected = []

    for i, img in enumerate(to_check, 1):
        fname = img["filename"]
        print(f"  [{i}/{len(to_check)}] {fname[:60]}")

        image_bytes = image_cache.get(fname)
        if image_bytes is None:
            rejected.append({**img, "reason": "Download fehlgeschlagen", "ablehnungsgrund": "Download fehlgeschlagen"})
            print("    [X] Download fehlgeschlagen")
            continue

        mime = _mime_from_url(img["thumb_url"])
        result = analyze_with_vision(client, image_bytes, mime, thema)

        if result is None:
            rejected.append({**img, "reason": "Vision-Fehler", "ablehnungsgrund": "Vision-API-Fehler"})
            print("    [X] Vision-Fehler")
            continue

        if not result.get("kindgerecht", False):
            grund = result.get("ablehnungsgrund", "")
            rejected.append({**img, "reason": f"kindgerecht=false: {grund}", "ablehnungsgrund": grund})
            print(f"    [X] ABGELEHNT: {grund}")
            continue

        relevanz = result.get("relevanz", 0)
        hero = result.get("hero_tauglich", False)
        beschreibung = result.get("beschreibung", "")
        accepted.append({
            **img,
            "relevanz": relevanz,
            "hero_tauglich": hero,
            "beschreibung": beschreibung,
        })
        hero_marker = " [HERO]" if hero else ""
        print(f"    [OK] [{relevanz}] {beschreibung[:80]}{hero_marker}")

    # 4. Sortieren + Hero bestimmen
    accepted.sort(key=lambda x: (-x["relevanz"], -int(x["hero_tauglich"])))
    for rank, a in enumerate(accepted, 1):
        a["rank"] = rank

    hero_img = next((a for a in accepted if a["hero_tauglich"]), accepted[0] if accepted else None)

    # 5. Zusammenfassung
    total_req = get_request_count() - req_before
    print(f"\n{'='*60}")
    print(f"Ergebnis: {len(accepted)} akzeptiert / {len(rejected)} abgelehnt")
    print(f"Wikimedia-API-Requests gesamt: {total_req}")
    if hero_img:
        print(f"Hero-Bild: {hero_img['filename']} (Relevanz: {hero_img['relevanz']})")
    print()

    if accepted:
        print("Relevanz-Ranking:")
        for a in accepted:
            hero_marker = " [H]" if a["hero_tauglich"] else ""
            print(f"  {a['rank']:2}. [{a['relevanz']}]{hero_marker} {a['filename'][:50]}")
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
            "candidates_in": len(candidates),
            "vision_checked": len(to_check),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "wikimedia_api_requests": total_req,
        },
        "hero": {
            "filename": hero_img["filename"],
            "relevanz": hero_img["relevanz"],
            "beschreibung": hero_img["beschreibung"],
            "thumb_url": hero_img["thumb_url"],
        } if hero_img else None,
        "accepted": [
            {
                "rank": a["rank"],
                "filename": a["filename"],
                "relevanz": a["relevanz"],
                "hero_tauglich": a["hero_tauglich"],
                "beschreibung": a["beschreibung"],
                "license": a["license"],
                "license_author": a["license_author"],
                "thumb_url": a["thumb_url"],
                "wikimedia_id": a["wikimedia_id"],
            }
            for a in accepted
        ],
        "rejected": [
            {
                "filename": r["filename"],
                "reason": r.get("reason", ""),
                "ablehnungsgrund": r.get("ablehnungsgrund", ""),
                "wikimedia_id": r.get("wikimedia_id", ""),
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
