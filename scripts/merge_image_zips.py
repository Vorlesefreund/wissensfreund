#!/usr/bin/env python3
"""
merge_image_zips.py — Shard-ZIPs zusammenführen + build_summary aggregieren

Erwartet:
  shard-0/images_thumb.zip, shard-0/images_standard.zip, shard-0/build_summary.json
  shard-1/...
  shard-2/...

Schreibt:
  images_thumb.zip
  images_standard.zip
  build_summary.json (aggregiert)

Env:
  SHARD_COUNT   Anzahl Shards (default: 3)
"""

import json
import os
import sys
import zipfile
from pathlib import Path

SHARD_COUNT = int(os.environ.get("SHARD_COUNT", "3"))
TIERS = ["thumb", "standard"]


def main() -> None:
    summaries: list[dict] = []

    for tier in TIERS:
        out_path = f"images_{tier}.zip"
        print(f"Merge → {out_path}")
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as out_zip:
            for s in range(SHARD_COUNT):
                src = Path(f"shard-{s}/images_{tier}.zip")
                if not src.exists():
                    print(f"  WARN: {src} nicht gefunden", file=sys.stderr)
                    continue
                with zipfile.ZipFile(src, "r") as in_zip:
                    count = 0
                    for item in in_zip.infolist():
                        out_zip.writestr(item, in_zip.read(item.filename))
                        count += 1
                    print(f"  shard-{s}: {count} Bilder")
        size_mb = Path(out_path).stat().st_size // 1_048_576
        print(f"  Gesamt: {size_mb} MB → {out_path}")

    # Summaries aggregieren
    for s in range(SHARD_COUNT):
        p = Path(f"shard-{s}/build_summary.json")
        if p.exists():
            summaries.append(json.loads(p.read_text(encoding="utf-8")))

    if summaries:
        agg = {
            "total_pairs":         sum(x.get("total_pairs", 0)         for x in summaries),
            "downloaded_thumb":    sum(x.get("downloaded_thumb", 0)    for x in summaries),
            "downloaded_standard": sum(x.get("downloaded_standard", 0) for x in summaries),
            "skipped_format":      sum(x.get("skipped_format", 0)      for x in summaries),
            "skipped_download":    sum(x.get("skipped_download", 0)    for x in summaries),
            "shard_count":         SHARD_COUNT,
        }
        total = agg["total_pairs"]
        agg["success_pct_thumb"]     = agg["downloaded_thumb"]    * 100 // max(total, 1)
        agg["success_pct_standard"]  = agg["downloaded_standard"] * 100 // max(total, 1)
        agg["plausibility"] = (
            "OK" if all(x.get("plausibility") == "OK" for x in summaries) else "FAIL"
        )
        Path("build_summary.json").write_text(
            json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nAggregierte Summary:")
        for k, v in agg.items():
            print(f"  {k}: {v}")

        if agg["plausibility"] != "OK":
            print("\n⚠️  PLAUSIBILITÄT FEHLGESCHLAGEN — Upload abgebrochen!")
            sys.exit(1)

    print("\n✓ Merge abgeschlossen")


if __name__ == "__main__":
    main()
