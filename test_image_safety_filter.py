#!/usr/bin/env python3
"""
test_image_safety_filter.py
Kalibrierungs-Harness fuer den Wissensfreund Bild-Kinderschutzfilter.

NICHT in die Pipeline eingehaengt — nur fuer manuelle Kalibrierung.

Drei Ebenen pro Bild:
  1. Lizenz    — Commons API LicenseShortName -> CC0/CC-BY/CC-BY-SA-Whitelist
  2. Kategorie — Commons API prop=categories  -> Blacklist-Match
  3. Vision    — Bild-Download -> base64 -> claude-opus-4-8 (echtes Bild, kein Dateiname)

Eingabe: JSON mit block_A_echte_artikelbilder + block_B_grenzfaelle_stufen_abstufung
         (Format: elefant_bildkandidaten.json)
Ausgabe: Tabelle (stdout) + CSV (--csv)

Verwendung:
    python test_image_safety_filter.py elefant_bildkandidaten.json
    python test_image_safety_filter.py elefant_bildkandidaten.json --csv out.csv
    python test_image_safety_filter.py elefant_bildkandidaten.json --no-vision
"""

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

COMMONS_API         = "https://commons.wikimedia.org/w/api.php"
CLAUDE_API_URL      = "https://api.anthropic.com/v1/messages"
CLAUDE_VISION_MODEL = "claude-opus-4-8"
THUMB_WIDTH         = 800   # px fuer Download
RATE_PAUSE          = 0.5   # Sekunden zwischen Commons-API-Calls

# Lizenz-Whitelist — Logik direkt aus _is_free_license() in generate_articles.py
LICENSE_KEYWORDS = ("CC0", "CC BY", "PUBLIC DOMAIN", "PD", "FAL", "LAL", "FREE ART", "ART LIBRE")

# Kategorie-Blacklist:
#   - global_exclusions.topics aus wissensfreund_categories_whitelist.json (normalisiert)
#   - + zusaetzliche Bild-Blacklist laut Aufgabenstellung
CATEGORY_BLACKLIST = [
    # aus global_exclusions.topics
    "pornograph", "pornografi",
    "sexualit",                  # matcht sexuality, sexualität, sexual content
    "suicide", "suizid",
    "terrorism", "terrorismus",
    "drug use", "drogenkonsum",
    # zusaetzliche Bild-spezifische Blocks (Aufgabenstellung)
    "human sexuality",
    "nudity",
    "nude",
    "war photograph",
    "medical imaging",
    "death",
    "dying",
    "injuries",
    "injury",
]

# Altersregeln — direkt aus AI_PROMPT (ALTERSSTUFEN-HINWEISE) in patch_article_images_v1.py
AGE_RULES = {
    1: (
        "Stufe 1 (4-6 J.): Nur lebende Tiere, bunte Natur, freundliche Bilder. "
        "Keine Skelette, Fossilien, Anatomie, tote Tiere, Jagdszenen, verstoerende Inhalte."
    ),
    2: (
        "Stufe 2 (7-9 J.): Wie Stufe 1, aber Skelette und anatomische Darstellungen "
        "sind ok wenn sie lehrreich sind. Keine Fossilien ausgestorbener Arten als Hauptthema."
    ),
    3: (
        "Stufe 3 (10-12 J.): Alle sachlich korrekten Bilder erlaubt, "
        "auch Fossilien, Vergleichsanatomie, historische Darstellungen."
    ),
}
AGE_LABELS = {1: "4-6 Jahre", 2: "7-9 Jahre", 3: "10-12 Jahre"}

COLUMNS = [
    "image", "ziel_stufe", "erwartet_mensch",
    "license", "license_ok", "matched_categories",
    "vision_verdict", "vision_reason", "final",
]


# ─── Lizenz (Ebene 1) ────────────────────────────────────────────────────────

def _is_free_license(s: str) -> bool:
    """Direkt aus generate_articles.py uebernommen."""
    s = s.upper()
    if "-NC" in s or "-ND" in s:
        return False
    return any(k in s for k in LICENSE_KEYWORDS)


def fetch_commons_info(filename: str, session: requests.Session) -> dict:
    """LicenseShortName + thumb_url in einem Commons-API-Call."""
    r = session.get(COMMONS_API, params={
        "action":              "query",
        "titles":              f"File:{filename}",
        "prop":                "imageinfo",
        "iiprop":              "extmetadata|url",
        "iiurlwidth":          str(THUMB_WIDTH),
        "iiextmetadatafilter": "LicenseShortName",
        "format":              "json",
        "formatversion":       "2",
    }, timeout=20)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return {"license": "FILE_NOT_FOUND", "license_ok": False, "thumb_url": ""}
    info = pages[0].get("imageinfo", [{}])[0]
    lic  = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "UNKNOWN")
    return {
        "license":    lic,
        "license_ok": _is_free_license(lic),
        "thumb_url":  info.get("thumburl", ""),
    }


# ─── Kategorie (Ebene 2) ─────────────────────────────────────────────────────

def fetch_matched_categories(filename: str, session: requests.Session) -> list[str]:
    """Commons prop=categories -> gegen CATEGORY_BLACKLIST matchen."""
    r = session.get(COMMONS_API, params={
        "action":        "query",
        "titles":        f"File:{filename}",
        "prop":          "categories",
        "cllimit":       "50",
        "format":        "json",
        "formatversion": "2",
    }, timeout=20)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return []
    cats = [
        c.get("title", "").removeprefix("Category:").lower().replace("_", " ")
        for c in pages[0].get("categories", [])
    ]
    return [c for c in cats if any(term in c for term in CATEGORY_BLACKLIST)]


# ─── Vision (Ebene 3) ────────────────────────────────────────────────────────

def check_vision(
    thumb_url: str,
    ziel_stufe: int,
    api_key: str,
    session: requests.Session,
) -> dict:
    """Bild herunterladen, base64-kodieren, an claude-opus-4-8 senden."""
    img_resp = session.get(thumb_url, timeout=30)
    img_resp.raise_for_status()

    ct = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if ct not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        ct = "image/jpeg"

    img_b64 = base64.b64encode(img_resp.content).decode()
    rule     = AGE_RULES[ziel_stufe]
    label    = AGE_LABELS[ziel_stufe]

    prompt = (
        f"Du bist Kinderschutz-Redakteur fuer das Kinderlexikon Wissensfreund "
        f"(Zielgruppe: {label}).\n\n"
        f"Altersregel: {rule}\n\n"
        "Beurteile anhand des BILDINHALTS (nicht des Dateinamens): "
        "Ist dieses Bild fuer Kinder der genannten Altersstufe geeignet?\n\n"
        "Antworte AUSSCHLIESSLICH mit validem JSON, kein Text davor oder danach:\n"
        '{"verdict": "keep", "reason": "Ein kurzer Satz"}\n'
        "oder\n"
        '{"verdict": "reject", "reason": "Ein kurzer Satz"}'
    )

    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      CLAUDE_VISION_MODEL,
        "max_tokens": 150,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": ct, "data": img_b64}},
                {"type": "text",  "text":   prompt},
            ],
        }],
    }

    resp = requests.post(CLAUDE_API_URL, headers=headers, json=body, timeout=90)
    resp.raise_for_status()
    raw     = resp.json()["content"][0]["text"].strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    parsed  = json.loads(cleaned)
    return {"verdict": parsed.get("verdict", "error"), "reason": parsed.get("reason", "")}


# ─── Hauptverarbeitung ────────────────────────────────────────────────────────

def process_image(
    entry: dict,
    api_key: str | None,
    session: requests.Session,
    skip_vision: bool,
) -> dict:
    filename   = entry["datei"]
    ziel_stufe = int(entry["ziel_stufe"])
    erwartet   = entry.get("erwartet_mensch", "?")

    row: dict = {
        "image":              filename,
        "ziel_stufe":         ziel_stufe,
        "erwartet_mensch":    erwartet,
        "license":            "error",
        "license_ok":         "error",
        "matched_categories": "",
        "vision_verdict":     "skip",
        "vision_reason":      "",
        "final":              "error",
    }

    try:
        # Ebene 1 — Lizenz
        info = fetch_commons_info(filename, session)
        row["license"]    = info["license"]
        row["license_ok"] = "yes" if info["license_ok"] else "no"
        thumb_url         = info["thumb_url"]
        time.sleep(RATE_PAUSE)

        # Ebene 2 — Kategorie
        matched = fetch_matched_categories(filename, session)
        row["matched_categories"] = "; ".join(matched) if matched else ""
        time.sleep(RATE_PAUSE)

        # Ebene 3 — Vision
        if api_key and not skip_vision:
            if thumb_url:
                v = check_vision(thumb_url, ziel_stufe, api_key, session)
                row["vision_verdict"] = v["verdict"]
                row["vision_reason"]  = v["reason"]
                time.sleep(RATE_PAUSE)
            else:
                row["vision_verdict"] = "skip"
                row["vision_reason"]  = "kein thumb_url"

        # final: reject wenn Lizenz nicht ok ODER Kategorie geblockt ODER vision=reject
        rejected = (
            row["license_ok"] == "no"
            or bool(matched)
            or row["vision_verdict"] == "reject"
        )
        row["final"] = "reject" if rejected else "keep"

    except Exception as exc:
        row["final"]         = "error"
        row["vision_reason"] = f"ERROR: {exc}"

    return row


# ─── Ausgabe ─────────────────────────────────────────────────────────────────

# Max-Breite pro Spalte fuer stdout-Tabelle (laengere Werte werden gekuerzt)
_TRUNC = {
    "image":              52,
    "license":            20,
    "matched_categories": 40,
    "vision_reason":      50,
}


def print_table(rows: list[dict]) -> None:
    widths = {col: len(col) for col in COLUMNS}
    display: list[dict] = []
    for row in rows:
        dr: dict = {}
        for col in COLUMNS:
            v = str(row.get(col, ""))
            lim = _TRUNC.get(col, 0)
            if lim and len(v) > lim:
                v = v[: lim - 1] + "…"
            dr[col] = v
            widths[col] = max(widths[col], len(v))
        display.append(dr)

    sep    = "+" + "+".join("-" * (widths[c] + 2) for c in COLUMNS) + "+"
    header = "|" + "|".join(f" {c:<{widths[c]}} " for c in COLUMNS) + "|"
    print(sep)
    print(header)
    print(sep)
    for dr in display:
        print("|" + "|".join(f" {dr[c]:<{widths[c]}} " for c in COLUMNS) + "|")
    print(sep)


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV -> {path}")


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Wissensfreund Bild-Kinderschutzfilter — Kalibrierungs-Harness"
    )
    p.add_argument("input_json",  type=Path, help="JSON mit block_A + block_B")
    p.add_argument("--csv",       type=Path, metavar="PATH", help="CSV-Ausgabepfad")
    p.add_argument("--no-vision", action="store_true", help="Vision-Ebene ueberspringen")
    args = p.parse_args()

    if not args.input_json.exists():
        sys.exit(f"Nicht gefunden: {args.input_json}")

    data    = json.loads(args.input_json.read_text(encoding="utf-8"))
    entries = (
        data.get("block_A_echte_artikelbilder", [])
        + data.get("block_B_grenzfaelle_stufen_abstufung", [])
    )
    if not entries:
        sys.exit("Keine Eintraege in block_A oder block_B gefunden")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.no_vision:
        print(
            "WARNUNG: ANTHROPIC_API_KEY nicht gesetzt — Vision-Ebene wird uebersprungen",
            file=sys.stderr,
        )

    session = requests.Session()
    session.headers["User-Agent"] = "Wissensfreund-Test/1.0 (az@expansionssupport.de)"

    rows: list[dict] = []
    total = len(entries)
    for i, entry in enumerate(entries, 1):
        fn    = entry.get("datei", "?")
        stufe = entry.get("ziel_stufe", "?")
        print(f"[{i}/{total}] {fn}  (Stufe {stufe})", flush=True)
        row = process_image(entry, api_key, session, args.no_vision)
        rows.append(row)
        icon = {"keep": "OK", "reject": "NO", "error": "!!"}.get(row["final"], "?")
        print(
            f"  {icon} final={row['final']}"
            f"  lic={row['license_ok']}"
            f"  cats={'none' if not row['matched_categories'] else row['matched_categories'][:40]}"
            f"  vision={row['vision_verdict']}"
        )

    print()
    print_table(rows)

    if args.csv:
        write_csv(rows, args.csv)

    keeps   = sum(1 for r in rows if r["final"] == "keep")
    rejects = sum(1 for r in rows if r["final"] == "reject")
    errors  = sum(1 for r in rows if r["final"] == "error")
    print(f"\nSummary: {keeps} keep / {rejects} reject / {errors} error  (total: {total})")


if __name__ == "__main__":
    main()
