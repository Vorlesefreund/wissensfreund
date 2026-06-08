"""
image_vision_filter.py
Vision-basierter Bild-Filter: prüft Wikipedia-Bilder mit Gemini Flash auf Kindgerechtheit + Relevanz.

Usage:
  python scripts/image_vision_filter.py --thema biene --wikipedia "Biene"
  python scripts/image_vision_filter.py --thema demokratie --wikipedia "Demokratie" --max 20

Output:
  articles/test_5topics/_images/{thema}_images.json
  Konsole: Kandidaten → Vision-Analyse → Hero + Ranking
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).parent.parent
_DOTENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "articles" / "test_5topics" / "_images"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

WIKIPEDIA_API = "https://de.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
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


def fetch_image_candidates(session: requests.Session, wikipedia_title: str, max_candidates: int = 50) -> list[dict]:
    """Lädt Bild-Metadaten von Wikipedia + Wikimedia Commons."""
    params = {
        "action": "query", "format": "json",
        "titles": wikipedia_title, "redirects": "1",
        "prop": "images", "imlimit": 50,
    }
    resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})

    raw_titles = []
    for page in pages.values():
        for img in page.get("images", []):
            t = _normalize_file_title(img.get("title", ""))
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

    time.sleep(0.5)
    params2 = {
        "action": "query", "format": "json",
        "titles": "|".join(raw_titles[:max_candidates]),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 800,
    }
    resp2 = session.get(COMMONS_API, params=params2, timeout=30)
    if resp2.status_code == 429:
        time.sleep(5)
        resp2 = session.get(COMMONS_API, params=params2, timeout=30)
    resp2.raise_for_status()
    cpages = resp2.json().get("query", {}).get("pages", {})

    images = []
    for cpage in cpages.values():
        ii_list = cpage.get("imageinfo", [])
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
        title = cpage.get("title", "")
        raw_author = (meta.get("Artist", {}).get("value", "")
                      or meta.get("Credit", {}).get("value", ""))
        clean_author = re.sub(r"<[^>]+>", "", raw_author).strip()[:80]
        images.append({
            "wikimedia_id": title,
            "filename": _filename_from_title(title),
            "thumb_url": thumb_url,
            "license": license_str,
            "license_author": clean_author,
        })

    return images


_DOWNLOAD_WAIT = [10, 30, 60]  # Exponentielles Backoff bei 429 (Wikimedia-Rate-Limit)

def download_image(session: requests.Session, url: str) -> bytes | None:
    for attempt in range(1, 5):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 429:
                wait = _DOWNLOAD_WAIT[min(attempt - 1, len(_DOWNLOAD_WAIT) - 1)]
                log.warning("  Download 429 (Versuch %d/4) -- warte %ds", attempt, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            if len(resp.content) > 18 * 1024 * 1024:
                log.warning("  Bild >18 MB, uebersprungen: %s", url)
                return None
            return resp.content
        except Exception as e:
            if attempt < 4 and "429" not in str(e):
                time.sleep(5)
                continue
            log.warning("  Download-Fehler: %s -- %s", url, e)
            return None
    return None


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


def run(thema: str, wikipedia_title: str, max_images: int = 30) -> None:
    load_dotenv(_DOTENV_PATH)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    print(f"\n=== Bild-Filter: {thema} (Wikipedia: \"{wikipedia_title}\") ===\n")

    session = requests.Session()
    # Wikimedia verlangt User-Agent mit Kontaktangabe (https://meta.wikimedia.org/wiki/User-Agent_policy)
    session.headers["User-Agent"] = "WissensfreundImageFilter/1.0 (az@expansionssupport.de; Kinderwissens-App)"
    client = genai.Client(api_key=api_key)

    # 1. Kandidaten laden
    log.info("Lade Bild-Kandidaten von Wikipedia + Commons ...")
    candidates = fetch_image_candidates(session, wikipedia_title, max_candidates=50)
    print(f"Kandidaten nach Dateiname- + Lizenz-Filter: {len(candidates)}")

    if not candidates:
        print("Keine Bilder gefunden.")
        return

    # 2. Vision-Check pro Bild
    print(f"-> {min(len(candidates), max_images)} Bilder fuer Vision-Check\n")

    accepted = []
    rejected = []

    for i, img in enumerate(candidates[:max_images], 1):
        fname = img["filename"]
        print(f"  [{i}/{min(len(candidates), max_images)}] {fname[:60]}")

        image_bytes = download_image(session, img["thumb_url"])
        if image_bytes is None:
            rejected.append({**img, "reason": "Download fehlgeschlagen", "ablehnungsgrund": "Download fehlgeschlagen"})
            print("    [X] Download fehlgeschlagen")
            time.sleep(2.0)
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

        time.sleep(2.0)

    # 3. Sortieren + Hero bestimmen
    accepted.sort(key=lambda x: (-x["relevanz"], -int(x["hero_tauglich"])))
    for rank, a in enumerate(accepted, 1):
        a["rank"] = rank

    hero_img = next((a for a in accepted if a["hero_tauglich"]), accepted[0] if accepted else None)

    # 4. Konsolen-Zusammenfassung
    print(f"\n{'='*60}")
    print(f"Ergebnis: {len(accepted)} akzeptiert / {len(rejected)} abgelehnt")
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

    # 5. JSON speichern
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{thema}_images.json"

    output = {
        "thema": thema,
        "wikipedia_title": wikipedia_title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "candidates_in": len(candidates),
            "vision_checked": min(len(candidates), max_images),
            "accepted": len(accepted),
            "rejected": len(rejected),
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
    parser = argparse.ArgumentParser(description="Vision-basierter Bild-Filter für Wissensfreund")
    parser.add_argument("--thema", required=True, help="Slug des Themas (z.B. biene)")
    parser.add_argument("--wikipedia", required=True, help="Exakter Wikipedia-Artikeltitel (z.B. 'Biene')")
    parser.add_argument("--max", type=int, default=30, help="Max. Bilder für Vision-Check (default: 30)")
    args = parser.parse_args()
    run(args.thema, args.wikipedia, args.max)
