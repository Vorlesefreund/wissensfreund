#!/usr/bin/env python3
"""
generate_image_index.py — image_index.json aus article_image_map.json erzeugen

Input:  article_image_map.json  (Env: INPUT, default: article_image_map.json)
Output: image_index.json        (Env: OUTPUT, default: image_index.json)

Format: {"<hash>.jpg": "Commons Dateiname.jpg", ...}
Nur Einträge mit hash != null UND filename != null.
"""

import json
import os
import sys
from pathlib import Path

INPUT  = Path(os.environ.get("INPUT",  "article_image_map.json"))
OUTPUT = Path(os.environ.get("OUTPUT", "image_index.json"))


def main() -> None:
    if not INPUT.exists():
        print(f"FEHLER: {INPUT} nicht gefunden", file=sys.stderr)
        sys.exit(1)

    data = json.loads(INPUT.read_text(encoding="utf-8"))

    index: dict[str, str] = {}
    total = skipped = dupes = 0

    for article in data:
        for img in article.get("data", []):
            total += 1
            h  = img.get("hash")
            fn = img.get("filename")
            if not h or not fn:
                skipped += 1
                continue
            if h in index:
                dupes += 1
                continue
            index[h] = fn

    OUTPUT.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"Einträge:  {len(index):6d}")
    print(f"Übersprungen (kein hash/filename): {skipped}")
    print(f"Duplikate (hash bereits gesehen):  {dupes}")
    print(f"-> {OUTPUT}  ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
