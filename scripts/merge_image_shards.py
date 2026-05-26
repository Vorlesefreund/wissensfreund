#!/usr/bin/env python3
"""
Merges sharded image ZIPs and manifests into final output files.

Each shard job produced its output in a subdirectory shard-N/.
This script reads from shard-0/, shard-1/, ... and writes:
  images_thumb.zip            images_thumb_manifest.json
  images_standard.zip         images_standard_manifest.json
  images_pro.zip              images_pro_manifest.json

Run:
  SHARD_COUNT=3 ZIM_VERSION=klexikon_de_all_maxi_2026-05 python scripts/merge_image_shards.py
"""

import json
import os
import zipfile
from datetime import date
from pathlib import Path

SHARD_COUNT = int(os.environ.get("SHARD_COUNT", "3"))
ZIM_VERSION = os.environ.get("ZIM_VERSION", "unknown")
TIERS       = ["thumb", "standard", "pro"]


def main() -> None:
    for tier in TIERS:
        out_zip_path = Path(f"images_{tier}.zip")
        merged_images: dict = {}

        with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_STORED) as z_out:
            for shard in range(SHARD_COUNT):
                zip_path      = Path(f"shard-{shard}") / f"images_{tier}.zip"
                manifest_path = Path(f"shard-{shard}") / f"images_{tier}_manifest.json"

                if zip_path.exists():
                    with zipfile.ZipFile(zip_path) as z_in:
                        for name in z_in.namelist():
                            z_out.writestr(name, z_in.read(name))
                    print(f"  Merged {zip_path} ({zip_path.stat().st_size // 1_048_576} MB)")
                else:
                    print(f"  WARN: {zip_path} not found — skipping")

                if manifest_path.exists():
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    merged_images.update(data.get("images", {}))

        manifest = {
            "generated":   date.today().isoformat(),
            "zim_version": ZIM_VERSION,
            "tier":        tier,
            "images":      merged_images,
        }
        Path(f"images_{tier}_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        zip_mb = out_zip_path.stat().st_size // 1_048_576
        print(f"  → images_{tier}.zip: {len(merged_images)} images, {zip_mb} MB")

    print("\nMerge done.")


if __name__ == "__main__":
    main()
