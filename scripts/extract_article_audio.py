#!/usr/bin/env python3
"""
Scans Klexikon ZIM article HTML for Wikimedia audio links
(href="...wpDestFile=FILENAME.ogg"), extracts captions,
writes article_audio_refs.json.

Run locally:
  ZIM_FILE=klexikon.zim python scripts/extract_article_audio.py
  ZIM_FILE=klexikon.zim MAX_ARTICLES=10 python scripts/extract_article_audio.py

Requires: pip install libzim
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    from libzim.reader import Archive
except ImportError:
    print("ERROR: pip install libzim", file=sys.stderr)
    sys.exit(1)

ZIM_FILE     = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE  = Path("article_audio_refs.json")
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "0"))   # 0 = alle Artikel

# Matches:  href="...?wpDestFile=Ludwig_van_Beethoven_...ogg"
# Also:     href="...&wpDestFile=...ogg"
AUDIO_LINK_RE = re.compile(
    r'href="[^"]*[?&]wpDestFile=([^"&]+\.(?:ogg|oga|mp3|opus|wav|flac))',
    re.IGNORECASE,
)


def extract_caption(html: str, match_start: int) -> str | None:
    """
    Returns the text fragment immediately before the audio link.
    Looks back up to 500 chars, strips HTML tags, returns the last clause.
    """
    window = html[max(0, match_start - 500): match_start]
    text = re.sub(r"<[^>]+>", " ", window)         # strip HTML tags
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)   # strip HTML entities
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    # Prefer the last clause that ends with ': ' or a sentence end
    for sep in (":", ".", "!", "?"):
        idx = text.rfind(sep)
        if idx >= 0:
            candidate = text[idx + 1:].strip()
            if 5 <= len(candidate) <= 200:
                return candidate
    tail = text[-150:].strip()
    return tail if len(tail) >= 5 else None


def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Opening {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    archive = Archive(str(zim_path))
    total_entries = archive.entry_count
    print(f"Total ZIM entries: {total_entries}")
    if MAX_ARTICLES:
        print(f"Test mode: scanning at most {MAX_ARTICLES} HTML articles")

    results: dict[str, list] = {}
    html_count = 0

    for i in range(total_entries):
        try:
            entry = archive[i]
        except Exception:
            continue
        if entry.is_redirect:
            continue

        try:
            item = entry.get_item()
        except Exception:
            continue
        if "html" not in item.mimetype.lower():
            continue

        html_count += 1
        if MAX_ARTICLES and html_count > MAX_ARTICLES:
            break

        try:
            html = bytes(item.content).decode("utf-8", errors="replace")
        except Exception:
            continue

        refs = []
        for m in AUDIO_LINK_RE.finditer(html):
            refs.append({
                "filename": unquote(m.group(1)),
                "caption":  extract_caption(html, m.start()),
                "position": m.start(),
            })

        if refs:
            title = entry.title or entry.path.rsplit("/", 1)[-1]
            results[title] = refs

        if html_count % 500 == 0:
            print(f"  {html_count} articles scanned, {len(results)} with audio...")

    OUTPUT_FILE.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    total_refs = sum(len(v) for v in results.values())
    print(
        f"\nDone: {html_count} articles scanned, "
        f"{total_refs} audio refs in {len(results)} articles → {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
