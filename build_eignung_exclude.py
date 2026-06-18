# build_eignung_exclude.py — Positiv-Exclude-Liste aus dem XLSX (Safety-Backstop)
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

REPO = Path(r"C:\Users\Andreas\wissensfreund_repo")
df = pd.read_excel(REPO/"catalog_review_master.xlsx", dtype=str)
excl = sorted({str(r["thema"]).strip().lower() for _, r in df.iterrows()
               if str(r["eignung"]).strip().lower() == "exclude"})
out = {"_meta": {"source": "catalog_review_master.xlsx",
                 "built": datetime.now(timezone.utc).isoformat(),
                 "count": len(excl),
                 "note": "Positive Exclude-Liste (normalisierte Lemmata) als Safety-Backstop"},
       "exclude": excl}
json.dump(out, open(REPO/"eignung_exclude.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"Geschrieben: {len(excl)} Excludes -> eignung_exclude.json")
print(excl[:10])
