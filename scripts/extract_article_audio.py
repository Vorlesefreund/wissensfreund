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

# href="...?wpDestFile=Ludwig_van_Beethoven_...ogg"
# href="...&wpDestFile=...ogg"
AUDIO_LINK_RE = re.compile(
    r'href="[^"]*[?&]wpDestFile=([^"&]+\.(?:ogg|oga|mp3|opus|wav|flac))',
    re.IGNORECASE,
)


def extract_caption(html: str, match_start: int) -> str | None:
    window = html[max(0, match_start - 500): match_start]
    text = re.sub(r"<[^>]+>", " ", window)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    for sep in (":", ".", "!", "?"):
        idx = text.rfind(sep)
        if idx >= 0:
            candidate = text[idx + 1:].strip()
            if 5 <= len(candidate) <= 200:
                return candidate
    tail = text[-150:].strip()
    return tail if len(tail) >= 5 else None


def _is_html_item(item) -> bool:
    """Return True if item appears to be an HTML article."""
    try:
        mt = (item.mimetype or "").lower()
    except Exception:
        mt = ""
    if "html" in mt:
        return True
    if not mt:
        # Content-sniff: check first 20 bytes
        try:
            snip = bytes(item.content[:20]).lower()
            return b"<!doctype" in snip or b"<html" in snip
        except Exception:
            pass
    return False


def _diag_entry(n: int, entry, archive) -> None:
    """Print diagnostics for one entry (first few only)."""
    try:
        path = getattr(entry, 'path', '?')
        is_redir = getattr(entry, 'is_redirect', '?')
        print(f"  [dbg{n}] path={path!r} is_redirect={is_redir}", flush=True)
    except Exception as e:
        print(f"  [dbg{n}] path/is_redirect failed: {type(e).__name__}: {e}", flush=True)
    try:
        item = entry.get_item()
        mt = getattr(item, 'mimetype', None)
        print(f"  [dbg{n}] get_item() ok, mimetype={mt!r} (type={type(mt).__name__})", flush=True)
        try:
            snip = bytes(item.content[:30])
            print(f"  [dbg{n}] content[:30]={snip!r}", flush=True)
        except Exception as e2:
            print(f"  [dbg{n}] content failed: {e2}", flush=True)
    except Exception as e:
        print(f"  [dbg{n}] get_item() -> {type(e).__name__}: {e}", flush=True)


def iter_entries(archive):
    """
    Yield all HTML content entries from archive.
    Robust to libzim API differences (1.x/2.x/3.x) and ZIM format versions.
    """
    n_tried = 0
    n_ok = 0
    n_err = 0
    iterated = False

    # Strategy 1: direct iteration (libzim 2.x / 3.x)
    try:
        for entry in archive:
            iterated = True
            n_tried += 1
            if n_tried <= 5:
                _diag_entry(n_tried, entry, archive)
            try:
                item = entry.get_item()
                n_ok += 1
                if _is_html_item(item):
                    yield entry, item
            except Exception:
                n_err += 1
                continue
        if n_tried > 0:
            print(f"  [dbg] Strategy1: {n_tried} entries, {n_ok} get_item ok, {n_err} errors", flush=True)
        if iterated:
            return  # ran to completion (even if n_ok==0)
    except TypeError:
        pass  # Archive not iterable — fall through

    # Strategy 2: index-based access (libzim 1.x)
    print(f"  [dbg] Trying Strategy2: archive.get_entry_by_id()", flush=True)
    n2 = 0
    for i in range(min(archive.entry_count, 5)):
        try:
            entry = archive.get_entry_by_id(i)
            item = entry.get_item()
            print(f"  [dbg2] id={i} path={getattr(entry,'path','?')!r} mime={getattr(item,'mimetype','?')!r}", flush=True)
            n2 += 1
        except Exception as e:
            print(f"  [dbg2] id={i} failed: {type(e).__name__}: {e}", flush=True)
    for i in range(archive.entry_count):
        try:
            entry = archive.get_entry_by_id(i)
            item = entry.get_item()
            if _is_html_item(item):
                yield entry, item
        except Exception:
            continue


def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Opening {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    archive = Archive(str(zim_path))
    print(f"Total ZIM entries: {archive.entry_count}")
    if MAX_ARTICLES:
        print(f"Test mode: scanning at most {MAX_ARTICLES} HTML articles")

    results: dict[str, list] = {}
    html_count = 0

    for entry, item in iter_entries(archive):
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
            print(f"  [{html_count}] {title}: {len(refs)} audio ref(s)")

        if html_count % 500 == 0:
            print(f"  {html_count} articles scanned, {len(results)} with audio...")

    OUTPUT_FILE.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    total_refs = sum(len(v) for v in results.values())
    print(
        f"\nDone: {html_count} articles scanned, "
        f"{total_refs} audio refs in {len(results)} articles -> {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
