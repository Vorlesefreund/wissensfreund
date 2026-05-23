#!/usr/bin/env python3
"""
Reads article_audio_refs.json, queries Wikimedia Commons for license + download URL,
downloads allowed files (max 5 MB each, max 50 MB total),
writes audio_index.json and wissensfreund_audio.zip.

Run locally:
  python scripts/download_audio.py
  ZIM_VERSION=klexikon_de_all_maxi_2026-05 python scripts/download_audio.py

Requires: pip install requests
"""
import json
import os
import re
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

REFS_FILE       = Path(os.environ.get("REFS_FILE", "article_audio_refs.json"))
OUTPUT_INDEX    = Path("audio_index.json")
OUTPUT_ZIP      = Path("wissensfreund_audio.zip")
ZIM_VERSION     = os.environ.get("ZIM_VERSION", "unknown")

MAX_FILE_BYTES  = 5 * 1024 * 1024    # 5 MB per file
MAX_TOTAL_BYTES = 50 * 1024 * 1024   # 50 MB total package
BATCH_SIZE      = 50
REQUEST_DELAY   = 0.5

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA          = "WissensfreundApp/1.0 (audio-downloader; github.com/Vorlesefreund/wissensfreund)"


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def is_permitted(lic: str) -> bool:
    if not lic:
        return False
    l = lic.strip().upper()
    if l == "CC0":
        return True
    if not l.startswith("CC BY"):
        return False
    return "-NC" not in l and "-ND" not in l


def query_commons(filenames: list[str]) -> dict:
    r = requests.get(
        COMMONS_API,
        params={
            "action": "query",
            "titles": "|".join(f"File:{f}" for f in filenames),
            "prop":   "imageinfo",
            "iiprop": "extmetadata|url",
            "format": "json",
        },
        timeout=30,
        headers={"User-Agent": UA},
    )
    r.raise_for_status()
    return r.json().get("query", {}).get("pages", {})


def main() -> None:
    if not REFS_FILE.exists():
        print(f"ERROR: {REFS_FILE} not found — run extract_article_audio.py first", file=sys.stderr)
        sys.exit(1)

    refs: dict[str, list] = json.loads(REFS_FILE.read_text(encoding="utf-8"))

    # Collect unique filenames while remembering which articles use them
    unique_files: dict[str, list] = {}   # filename → [(article, caption, position)]
    for article, items in refs.items():
        for item in items:
            fn = item["filename"]
            unique_files.setdefault(fn, []).append(
                (article, item.get("caption"), item.get("position", 0))
            )

    filenames = list(unique_files.keys())
    print(f"Querying {len(filenames)} unique audio files from Wikimedia Commons...")

    # License + URL query in batches
    file_info: dict[str, dict] = {}
    batches = [filenames[i: i + BATCH_SIZE] for i in range(0, len(filenames), BATCH_SIZE)]
    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} files)...", end=" ", flush=True)
        try:
            pages = query_commons(batch)
            for page in pages.values():
                title     = page.get("title", "").removeprefix("File:")
                info_list = page.get("imageinfo") or []
                if not info_list:
                    # Not found on Commons → block (audio must be explicitly licensed)
                    file_info[title] = {"allowed": False, "reason": "not_on_commons"}
                    continue
                info    = info_list[0]
                meta    = info.get("extmetadata") or {}
                lic     = meta.get("LicenseShortName", {}).get("value", "")
                auth    = strip_html(meta.get("Artist", {}).get("value", ""))
                lic_url = meta.get("LicenseUrl",       {}).get("value", "")
                dl_url  = info.get("url", "")
                file_info[title] = {
                    "allowed":      is_permitted(lic),
                    "license":      lic     or None,
                    "author":       auth    or None,
                    "license_url":  lic_url or None,
                    "download_url": dl_url  or None,
                }
            print("ok")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(REQUEST_DELAY)

    # Download allowed files
    allowed = [
        (fn, info) for fn, info in file_info.items()
        if info.get("allowed") and info.get("download_url")
    ]
    print(f"\nAllowed: {len(allowed)} / {len(filenames)} files. Downloading...")

    download_dir = Path("audio_downloads")
    download_dir.mkdir(exist_ok=True)

    downloaded: dict[str, Path] = {}
    total_bytes = 0
    rate_limited = 0

    for fn, info in allowed:
        if total_bytes >= MAX_TOTAL_BYTES:
            print(f"  50 MB total limit reached — stopping downloads")
            break

        out_path = download_dir / fn
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {fn}...", end=" ", flush=True)

        try:
            r = requests.get(
                info["download_url"], timeout=60, stream=True,
                headers={"User-Agent": UA},
            )
            if r.status_code == 429:
                # Rate-Limit noch aktiv — einmal 60 s warten und nochmal versuchen
                print(f"429 — warte 60 s...", end=" ", flush=True)
                time.sleep(60)
                r = requests.get(
                    info["download_url"], timeout=60, stream=True,
                    headers={"User-Agent": UA},
                )
            if r.status_code == 429:
                # Rate-Limit hält an — alle weiteren Downloads sind ebenfalls betroffen.
                # Sofort abbrechen statt pro Datei 60 s zu warten (verhindert Timeout).
                print("SKIP (429) — Rate-Limit aktiv, breche alle Downloads ab")
                file_info[fn]["allowed"] = False
                file_info[fn]["reason"]  = "rate_limited"
                rate_limited += 1
                break
            r.raise_for_status()

            buf  = bytearray()
            size = 0
            too_large = False
            for chunk in r.iter_content(65536):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    too_large = True
                    break
                buf.extend(chunk)

            if too_large:
                print(f"SKIP (>{MAX_FILE_BYTES // 1_048_576} MB)")
                file_info[fn]["allowed"] = False
                file_info[fn]["reason"]  = "too_large"
                continue

            out_path.write_bytes(bytes(buf))
            total_bytes += size
            downloaded[fn] = out_path
            print(f"ok ({size // 1024} KB, total {total_bytes // 1_048_576} MB)")

        except Exception as e:
            print(f"ERROR: {e}")
            file_info[fn]["allowed"] = False
            file_info[fn]["reason"]  = str(e)

        time.sleep(REQUEST_DELAY)

    if rate_limited:
        print(f"  {rate_limited} Dateien wegen Rate-Limit übersprungen")

    print(f"\nDownloaded: {len(downloaded)} files, {total_bytes // 1_048_576} MB total")

    # Build audio_index.json — only articles that actually have downloaded files
    index_audio: dict[str, list] = {}
    for article, items in refs.items():
        entries = []
        for item in sorted(items, key=lambda x: x.get("position", 0)):
            fn = item["filename"]
            if fn in downloaded:
                entries.append({
                    "filename":   fn,
                    "caption":    item.get("caption"),
                    "local_path": f"audio/{fn}",
                    "position":   item.get("position", 0),
                })
        if entries:
            index_audio[article] = entries

    audio_index = {
        "generated":   date.today().isoformat(),
        "zim_version": ZIM_VERSION,
        "audio":       index_audio,
    }
    OUTPUT_INDEX.write_text(
        json.dumps(audio_index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Written {OUTPUT_INDEX} ({len(index_audio)} articles with audio)")

    # Pack into ZIP
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn, local_path in downloaded.items():
            zf.write(local_path, f"audio/{fn}")
    zip_kb = OUTPUT_ZIP.stat().st_size // 1024
    print(f"Written {OUTPUT_ZIP} ({zip_kb} KB, {len(downloaded)} files)")


if __name__ == "__main__":
    main()
