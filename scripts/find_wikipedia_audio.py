#!/usr/bin/env python3
"""
Findet Wikipedia-Audio-Dateien (Tierlaute, Musik, Naturgeräusche, Aussprachen)
für alle Klexikon-Artikel über die Wikipedia-API.

Pipeline:
  1. Artikel-Titel aus ZIM lesen (kein Cluster-Dekomprimieren nötig)
  2. Pro Titel Wikipedia prop=images abfragen, auf Audio-Formate filtern
  3. Gesprochene Artikel-Versionen ausschließen ("gesprochen", "spoken")
  4. Wikimedia Commons: Lizenzprüfung für gefundene Dateien (gebatcht)
  5. media_licenses.json audio-Sektion erweitern
  6. wikipedia_audio_refs.json schreiben (Input für download_audio.py)

Umgebungsvariablen:
  ZIM_FILE      — Pfad zur ZIM-Datei        (Standard: klexikon.zim)
  ZIM_VERSION   — Versions-String           (Standard: klexikon_de_all_maxi_2026-05)
  MAX_ARTICLES  — Nur die ersten N Artikel  (0 = alle; Standard: 0)
  LICENSES_FILE — Pfad zu media_licenses.json (Standard: media_licenses.json)

Run:
  ZIM_FILE=klexikon.zim python scripts/find_wikipedia_audio.py
  ZIM_FILE=klexikon.zim MAX_ARTICLES=20 python scripts/find_wikipedia_audio.py

Requires: pip install requests
"""

import json
import os
import re
import struct
import sys
import time
from pathlib import Path
from urllib.parse import unquote

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

ZIM_FILE      = os.environ.get("ZIM_FILE",      "klexikon.zim")
ZIM_VERSION   = os.environ.get("ZIM_VERSION",   "klexikon_de_all_maxi_2026-05")
MAX_ARTICLES  = int(os.environ.get("MAX_ARTICLES", "0"))
LICENSES_FILE = Path(os.environ.get("LICENSES_FILE", "media_licenses.json"))
OUTPUT_FILE   = Path("wikipedia_audio_refs.json")

WIKIPEDIA_API_DE = "https://de.wikipedia.org/w/api.php"
WIKIPEDIA_API_EN = "https://en.wikipedia.org/w/api.php"
COMMONS_API      = "https://commons.wikimedia.org/w/api.php"
UA               = "Wissensfreund/1.0 (https://github.com/Vorlesefreund/wissensfreund)"

AUDIO_EXTS = {".ogg", ".oga", ".mp3", ".opus", ".wav", ".flac"}
EXCLUDE_KW = {"gesprochen", "spoken"}

# Aussprache-Dateien: beginnen mit Sprachkürzel + Bindestrich (De-, En-, Da-, Roh-, …)
# oder mit Lingua-Libre-Präfix (LL-Q). Nur Tierlaute/Musik/Naturgeräusche sind erwünscht.
PRONUNCIATION_RE = re.compile(r'^[A-Za-z]{2,5}-|^LL-Q', re.IGNORECASE)

BATCH_SIZE    = 50
WP_DELAY      = 0.5   # Sekunden zwischen Wikipedia-API-Anfragen
COMMONS_DELAY = 1.5   # Sekunden zwischen Commons-Batches

ZIM_MAGIC = 0x044d495a


# ── ZIM-Titel lesen (ohne Cluster-Dekomprimierung) ───────────────────────────

def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        buf.extend(b)
    return buf.decode("utf-8", errors="replace")


def _read_mime_types(f, pos: int) -> list[str]:
    f.seek(pos)
    types: list[str] = []
    while True:
        mt = _read_cstr(f)
        if not mt:
            break
        types.append(mt)
    return types


def read_article_titles(zim_path: Path) -> list[str]:
    """
    Liest alle HTML-Artikel-Titel aus dem ZIM.
    Nutzt nur den URL-Pointer-Table und Entry-Header — kein Cluster-Dekomprimieren.
    """
    titles: list[str] = []
    with open(zim_path, "rb") as f:
        header = f.read(80)
        if len(header) < 80:
            print("ERROR: ZIM zu klein", file=sys.stderr)
            sys.exit(1)

        magic, = struct.unpack_from("<I", header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: kein ZIM (magic={hex(magic)})", file=sys.stderr)
            sys.exit(1)

        entry_count,   = struct.unpack_from("<I", header, 24)
        url_ptr_pos,   = struct.unpack_from("<Q", header, 32)
        mime_list_pos, = struct.unpack_from("<Q", header, 56)

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if "html" in mt.lower()}

        if not html_idxs:
            print("ERROR: kein text/html MIME-Typ in ZIM", file=sys.stderr)
            sys.exit(1)

        print(f"ZIM: {entry_count} Einträge, HTML-MIME-Indizes: {html_idxs}")

        for i in range(entry_count):
            f.seek(url_ptr_pos + i * 8)
            raw = f.read(8)
            if len(raw) < 8:
                break
            ptr, = struct.unpack_from("<Q", raw)

            f.seek(ptr)
            hdr = f.read(4)
            if len(hdr) < 4:
                continue
            mime_idx, _param, _ns = struct.unpack_from("<HBc", hdr)

            if mime_idx == 0xffff:
                continue  # Redirect
            if mime_idx not in html_idxs:
                continue  # Kein HTML (nächste Iteration seekt neu)

            f.read(4)   # revision
            f.read(8)   # cluster_num + blob_num
            url   = _read_cstr(f)
            title = _read_cstr(f)

            if not title:
                title = unquote(url).rsplit("/", 1)[-1]
            if title:
                titles.append(title)

    return titles


# ── Wikipedia API ─────────────────────────────────────────────────────────────

def _is_audio(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO_EXTS:
        return False
    name_lower = filename.lower()
    if any(kw in name_lower for kw in EXCLUDE_KW):
        return False
    if PRONUNCIATION_RE.match(filename):
        return False   # Aussprache-Datei → kein Mehrwert für Kinder
    return True


def _query_wp_api(api_url: str, title: str, session: requests.Session) -> list[str]:
    """Fragt einen Wikipedia-API-Endpunkt ab und gibt Audio-Dateinamen zurück."""
    try:
        resp = session.get(
            api_url,
            params={
                "action":    "query",
                "titles":    title,
                "prop":      "images",
                "imlimit":   "50",
                "format":    "json",
                "redirects": "1",
            },
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        audio_files: list[str] = []
        for page in pages.values():
            if "missing" in page:
                return []
            for img in page.get("images", []):
                raw_title = img.get("title", "")
                # "Datei:Foo.ogg" oder "File:Foo.ogg" → "Foo.ogg"
                filename = raw_title.split(":", 1)[-1] if ":" in raw_title else raw_title
                if _is_audio(filename):
                    audio_files.append(filename)
        return audio_files
    except Exception as e:
        print(f"  WARNING Wikipedia API '{title}': {e}")
        return []


def query_wikipedia_images(title: str, session: requests.Session) -> list[str]:
    """
    Sucht Audio-Dateien auf Deutsch-Wikipedia, fällt auf Englisch-Wikipedia zurück
    wenn keine gefunden (z.B. Beethoven: de.wp hat kein Audio, en.wp hat OGG-Aufnahmen).
    """
    audio = _query_wp_api(WIKIPEDIA_API_DE, title, session)
    if audio:
        return audio
    # Fallback: Englisch-Wikipedia (extra Delay einhalten)
    time.sleep(WP_DELAY)
    audio = _query_wp_api(WIKIPEDIA_API_EN, title, session)
    if audio:
        print(f"  (EN-Fallback für '{title}')")
    return audio


# ── Wikimedia Commons Lizenzprüfung ──────────────────────────────────────────

def _is_permitted(lic: str) -> bool:
    if not lic:
        return False
    l = lic.strip().upper()
    if l == "CC0":
        return True
    if not l.startswith("CC BY"):
        return False
    return "-NC" not in l and "-ND" not in l


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def check_commons_licenses(
    filenames: list[str], session: requests.Session
) -> dict[str, dict]:
    """
    Prüft Lizenzen gebatcht auf Wikimedia Commons.
    Rückgabe: {filename: {allowed, license, author, license_url}}
    Audio ohne Commons-Eintrag → blocked (kein implizites Vertrauen wie bei Bildern).
    """
    results: dict[str, dict] = {}
    batches = [filenames[i : i + BATCH_SIZE] for i in range(0, len(filenames), BATCH_SIZE)]

    for bi, batch in enumerate(batches, 1):
        print(f"  Commons-Batch {bi}/{len(batches)} ({len(batch)} Dateien)...", end=" ", flush=True)
        try:
            resp = session.get(
                COMMONS_API,
                params={
                    "action": "query",
                    "titles": "|".join(f"File:{fn}" for fn in batch),
                    "prop":   "imageinfo",
                    "iiprop": "extmetadata",
                    "format": "json",
                },
                timeout=30,
            )
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                fname     = page.get("title", "").removeprefix("File:")
                info_list = page.get("imageinfo") or []
                if not info_list:
                    # Nicht auf Commons → Audio blockieren
                    results[fname] = {
                        "allowed": False, "license": None,
                        "author": None, "license_url": None,
                    }
                    continue
                meta    = info_list[0].get("extmetadata") or {}
                lic     = meta.get("LicenseShortName", {}).get("value", "")
                auth    = _strip_html(meta.get("Artist",   {}).get("value", ""))
                lic_url = meta.get("LicenseUrl",      {}).get("value", "")
                results[fname] = {
                    "allowed":     _is_permitted(lic),
                    "license":     lic     or None,
                    "author":      auth    or None,
                    "license_url": lic_url or None,
                }
            print("ok")
        except Exception as e:
            print(f"FEHLER: {e}")
        time.sleep(COMMONS_DELAY)

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM nicht gefunden: {zim_path}", file=sys.stderr)
        sys.exit(1)

    # ── Schritt 1: Artikel-Titel aus ZIM ────────────────────────────────────
    print(f"Lese Artikel-Titel aus {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    all_titles = read_article_titles(zim_path)
    print(f"{len(all_titles)} HTML-Artikel gefunden")

    titles = all_titles[:MAX_ARTICLES] if MAX_ARTICLES else all_titles
    if MAX_ARTICLES:
        print(f"Test-Modus: nur die ersten {MAX_ARTICLES} Artikel")

    session = requests.Session()
    session.headers["User-Agent"] = UA

    # ── Schritt 2: Wikipedia-API abfragen ────────────────────────────────────
    print(f"\nSchritt 2: Wikipedia-API für {len(titles)} Artikel abfragen...")
    article_audio: dict[str, list[str]] = {}  # article → [filename, ...]

    for i, title in enumerate(titles, 1):
        audio_files = query_wikipedia_images(title, session)
        if audio_files:
            article_audio[title] = audio_files
            print(f"  [{i}/{len(titles)}] {title}: {audio_files}")
        elif i % 200 == 0:
            print(f"  [{i}/{len(titles)}] ...")
        time.sleep(WP_DELAY)

    total_raw = sum(len(v) for v in article_audio.values())
    print(f"\nGefunden: {total_raw} Audio-Refs in {len(article_audio)} Artikeln")

    # Immer ausgeben — auch wenn leer, damit download_audio.py nicht scheitert
    if not article_audio:
        print("Keine Audio-Dateien gefunden.")
        OUTPUT_FILE.write_text(json.dumps({}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Leere Refs geschrieben → {OUTPUT_FILE}")
        return

    # ── Schritt 3: Wikimedia Commons Lizenzprüfung ───────────────────────────
    print("\nSchritt 3: Wikimedia Commons Lizenzprüfung...")
    unique_files = list({fn for files in article_audio.values() for fn in files})
    print(f"{len(unique_files)} eindeutige Dateien prüfen...")
    license_info = check_commons_licenses(unique_files, session)

    allowed_count = sum(1 for v in license_info.values() if v["allowed"])
    print(f"Lizenz-Ergebnis: {allowed_count} erlaubt / {len(unique_files)} geprüft")

    # ── Schritt 4: media_licenses.json aktualisieren ─────────────────────────
    print(f"\nSchritt 4: {LICENSES_FILE} aktualisieren...")
    if LICENSES_FILE.exists():
        media_licenses = json.loads(LICENSES_FILE.read_text(encoding="utf-8"))
    else:
        print(f"  {LICENSES_FILE} nicht gefunden — erstelle neu")
        media_licenses = {"images": {}, "audio": {}}

    audio_section = media_licenses.setdefault("audio", {})
    new_entries = 0
    for article, files in article_audio.items():
        for fn in files:
            info = license_info.get(fn, {"allowed": False})
            audio_section[fn] = {
                "allowed":     info.get("allowed", False),
                "license":     info.get("license"),
                "author":      info.get("author"),
                "license_url": info.get("license_url"),
                "caption":     "",
                "article":     article,
            }
            new_entries += 1

    LICENSES_FILE.write_text(
        json.dumps(media_licenses, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  {new_entries} Audio-Einträge in {LICENSES_FILE} geschrieben")

    # ── Schritt 5: wikipedia_audio_refs.json (nur erlaubte Dateien) ───────────
    print(f"\nSchritt 5: {OUTPUT_FILE} schreiben...")
    refs: dict[str, list] = {}
    for article, files in article_audio.items():
        entries = [
            {"filename": fn, "caption": "", "position": 0}
            for fn in files
            if license_info.get(fn, {}).get("allowed")
        ]
        if entries:
            refs[article] = entries

    OUTPUT_FILE.write_text(
        json.dumps(refs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    allowed_articles = len(refs)
    allowed_files    = sum(len(v) for v in refs.values())
    print(f"  {allowed_files} erlaubte Dateien in {allowed_articles} Artikeln → {OUTPUT_FILE}")
    print("\nFertig.")


if __name__ == "__main__":
    main()
