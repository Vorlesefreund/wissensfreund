#!/usr/bin/env python3
"""
enrich_image_metadata_v1.py
Wissensfreund Bild-Pipeline — Metadaten-Anreicherung

Liest die bestehende image_index.json (hash → filename)
und reichert sie mit Metadaten von der Wikimedia Commons API an:
  - source_url  (Link zur Commons-Seite)
  - author      (Urheber, HTML-bereinigt)
  - license     (Kurzname, z.B. "CC BY-SA 4.0")

Wird als einmaliger Nachträglicher Lauf ausgeführt — kein neuer Vollscrape.
Danach ersetzt die angereicherte JSON die alte in R2.

Verwendung:
  python enrich_image_metadata_v1.py \
    --input  image_index.json \
    --output image_index_v2.json \
    --batch-size 50 \
    --delay 0.5

Fortsetzen bei Abbruch:
  python enrich_image_metadata_v1.py \
    --input  image_index.json \
    --output image_index_v2.json \
    --resume                        ← überspringt bereits verarbeitete Einträge
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Wikimedia Commons API
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "WissensfreundBot/1.0 (https://wissensfreund.app; contact@wissensfreund.app)"
})


# ─────────────────────────────────────────────────────────
# HTML-Bereinigung für Artist-Feld
# ─────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """
    Entfernt HTML-Tags und dekodiert häufige HTML-Entities.
    Wikimedia sendet im Artist-Feld oft Links wie:
      <a href="...">Fotografname</a>
    Wir wollen nur: "Fotografname"
    """
    if not text:
        return ""
    # HTML-Tags entfernen
    clean = re.sub(r"<[^>]+>", "", text)
    # Häufige HTML-Entities dekodieren
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#039;": "'", "&nbsp;": " ",
    }
    for entity, char in entities.items():
        clean = clean.replace(entity, char)
    # Mehrfache Leerzeichen normalisieren
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


# ─────────────────────────────────────────────────────────
# Wikimedia Commons API — Batch-Abfrage
# ─────────────────────────────────────────────────────────

def fetch_metadata_batch(filenames: list[str]) -> dict[str, dict]:
    """
    Holt Metadaten für bis zu 50 Dateien in einer API-Anfrage.

    Gibt dict {filename: {source_url, author, license}} zurück.
    Fehlende oder fehlerhafte Einträge erhalten leere Strings.
    """
    # Wikimedia erwartet "File:Dateiname" als Titel
    titles = "|".join(f"File:{fn}" for fn in filenames)

    params = {
        "action": "query",
        "titles": titles,
        "prop": "imageinfo",
        "iiprop": "url|descriptionurl|extmetadata",
        "iiextmetadatafilter": "Artist|LicenseShortName",
        "iimetadatalanguage": "de",   # bevorzugt deutschsprachige Metadaten
        "format": "json",
        "formatversion": "2",
    }

    try:
        r = SESSION.get(COMMONS_API, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("API-Fehler für Batch: %s", e)
        return {}

    results: dict[str, dict] = {}

    for page in data.get("query", {}).get("pages", []):
        # Originaldateinamen aus dem Titel extrahieren ("File:X.jpg" → "X.jpg")
        title = page.get("title", "")
        filename = title.removeprefix("File:") if title.startswith("File:") else title

        if page.get("missing") or "imageinfo" not in page:
            results[filename] = {"source_url": "", "author": "", "license": ""}
            continue

        info = page["imageinfo"][0] if page["imageinfo"] else {}
        extmeta = info.get("extmetadata", {})

        source_url = info.get("descriptionurl", "")
        author_raw = extmeta.get("Artist", {}).get("value", "")
        license_raw = extmeta.get("LicenseShortName", {}).get("value", "")

        results[filename] = {
            "source_url": source_url,
            "author": strip_html(author_raw),
            "license": license_raw,
        }

    return results


# ─────────────────────────────────────────────────────────
# Hauptprogramm
# ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Reichert image_index.json mit Commons-Metadaten an"
    )
    parser.add_argument("--input",      default="image_index.json",
                        help="Bestehende image_index.json (hash → filename)")
    parser.add_argument("--output",     default="image_index_v2.json",
                        help="Angereicherte Ausgabedatei")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Dateien pro API-Anfrage (max. 50)")
    parser.add_argument("--delay",      type=float, default=0.5,
                        help="Pause zwischen API-Anfragen in Sekunden")
    parser.add_argument("--resume",     action="store_true",
                        help="Bestehende Ausgabedatei weiterschreiben")
    args = parser.parse_args()

    # Eingabe laden
    input_path = Path(args.input)
    if not input_path.exists():
        log.error("Eingabedatei nicht gefunden: %s", input_path)
        return

    index: dict[str, str] = json.loads(input_path.read_text(encoding="utf-8"))
    log.info("Einträge geladen: %d", len(index))

    # Ausgabe initialisieren (ggf. fortsetzen)
    output_path = Path(args.output)
    output: dict[str, dict] = {}

    if args.resume and output_path.exists():
        output = json.loads(output_path.read_text(encoding="utf-8"))
        log.info("Fortsetzen — bereits verarbeitet: %d", len(output))

    # Eindeutige Dateinamen sammeln (mehrere Hashes können auf
    # dieselbe Datei zeigen — deduplizieren spart API-Anfragen)
    all_filenames = list({v for v in index.values() if v})
    todo = [fn for fn in all_filenames if fn not in
            {entry.get("filename") for entry in output.values()}]

    log.info("Zu verarbeiten: %d Dateinamen", len(todo))

    # Batch-Verarbeitung
    total = len(todo)
    processed = 0
    errors = 0

    for i in range(0, total, args.batch_size):
        batch = todo[i : i + args.batch_size]
        meta = fetch_metadata_batch(batch)

        for fn in batch:
            m = meta.get(fn, {"source_url": "", "author": "", "license": ""})
            # Speichern unter Dateiname als Schlüssel
            output[fn] = {
                "filename":   fn,
                "source_url": m["source_url"],
                "author":     m["author"],
                "license":    m["license"],
            }
            if not m["source_url"]:
                errors += 1

        processed += len(batch)
        pct = round(processed / total * 100)
        log.info("[%3d%%] %d / %d  (Fehler: %d)", pct, processed, total, errors)

        # Checkpoint: nach jedem Batch speichern (Resume-Sicherheit)
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        if i + args.batch_size < total:
            time.sleep(args.delay)

    # Finales Index-Format: hash → erweiterter Eintrag
    # Bisherige Struktur: {"abc123": "Datei.jpg"}
    # Neue Struktur:      {"abc123": {"filename": "Datei.jpg",
    #                                 "source_url": "...",
    #                                 "author": "...",
    #                                 "license": "..."}}
    enriched_index: dict[str, dict] = {}
    for hash_key, filename in index.items():
        if filename and filename in output:
            enriched_index[hash_key] = output[filename]
        else:
            enriched_index[hash_key] = {
                "filename": filename or "",
                "source_url": "",
                "author": "",
                "license": "",
            }

    output_path.write_text(
        json.dumps(enriched_index, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    log.info("Fertig. Ausgabe: %s (%d Einträge, %d ohne Metadaten)",
             output_path, len(enriched_index), errors)
    log.info("")
    log.info("Nächste Schritte:")
    log.info("  1. Stichproben prüfen: python -c \""
             "import json; d=json.load(open('%s')); "
             "[print(k,v) for k,v in list(d.items())[:5]]\"", output_path)
    log.info("  2. Nach R2 hochladen: rclone copyto %s r2:wissensfreund/image_index.json",
             output_path)


if __name__ == "__main__":
    main()
