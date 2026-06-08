#!/usr/bin/env python3
"""
upload_articles.py
Wissensfreund Artikel-Pipeline — Schritt 3

Liest fertige Artikel-JSONs aus articles/, baut pro Kategorie und
Altersgruppe einen schlanken Index (für die Flutter-App-Navigation),
und lädt alles zu Cloudflare R2.

Verwendung:
    python upload_articles.py \
        --articles-dir  articles/ \
        --topic-tree    wissensfreund_topic_tree.json \
        --out-dir       upload_staging/ \
        --dry-run

    # Mit R2-Upload (Umgebungsvariablen setzen):
    CF_R2_ACCESS_KEY_ID=... CF_R2_SECRET_ACCESS_KEY=... \
    CF_ACCOUNT_ID=... \
    python upload_articles.py --articles-dir articles/ --topic-tree ...

Ausgabe in upload_staging/:
    articles/{article_id}.json         — Einzelartikel
    index/global.json                  — Alle Artikel, alle Stufen
    index/level_{1|2|3}.json           — Pro Altersgruppe
    index/cat_{category_id}.json       — Pro Top-Kategorie
    index/sub_{subcategory_id}.json    — Pro Subkategorie
    index/new.json                     — Die 50 neuesten Artikel
    index/review_queue.json            — Artikel mit review_flag
    meta/pipeline_run.json             — Run-Metadaten
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

INDEX_FIELDS = [
    "id", "title", "subtitle", "emoji",
    "age_level", "pattern", "theme_color",
    "word_count", "generated_at", "review_flag",
]


# ─────────────────────────────────────────────
# Artikel einlesen
# ─────────────────────────────────────────────

def load_articles(articles_dir: Path, include_errors: bool = False) -> list[dict]:
    """
    Liest alle Artikel-JSONs ein.
    Artikel in _errors/ werden nur geladen wenn include_errors=True.
    """
    articles = []
    skipped = 0

    for path in sorted(articles_dir.rglob("*.json")):
        if "_errors" in path.parts and not include_errors:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Minimale Sanity-Check
            if not data.get("meta", {}).get("id"):
                log.warning("  Übersprungen (keine meta.id): %s", path.name)
                skipped += 1
                continue
            # Pfad als Quelle speichern
            data["_source_path"] = str(path)
            articles.append(data)
        except json.JSONDecodeError as e:
            log.warning("  JSON-Fehler in %s: %s", path.name, e)
            skipped += 1

    log.info("Artikel geladen: %d OK, %d übersprungen", len(articles), skipped)
    return articles


# ─────────────────────────────────────────────
# Index-Einträge
# ─────────────────────────────────────────────

def make_index_entry(article: dict) -> dict:
    """Schlanker Index-Eintrag — nur was die App für die Listenansicht braucht."""
    meta = article.get("meta", {})
    entry = {k: meta.get(k) for k in INDEX_FIELDS}

    # Erstes Bild als Thumbnail-Referenz
    images = article.get("images", [])
    if images:
        hero = images[0]
        entry["thumb_url"]    = hero.get("thumb_url", "")
        entry["hero_filename"] = hero.get("filename", "")

    # Kategorie-Info aus Job-Metadaten (falls vorhanden)
    entry["category_top"] = meta.get("category_top", "")
    entry["category_sub"] = meta.get("category_sub", "")

    return entry


# ─────────────────────────────────────────────
# Topic-Tree anreichern
# ─────────────────────────────────────────────

def load_topic_tree(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def enrich_topic_tree(tree: dict, articles: list[dict]) -> dict:
    """
    Fügt jedem Subtopic die tatsächliche Artikel-Anzahl pro Stufe hinzu.
    Die App zeigt das als "42 Artikel · Stufe 2+3".
    """
    # Lookup: sub_id → {level: count}
    counts: dict[str, dict[str, int]] = {}
    for a in articles:
        meta = a.get("meta", {})
        sub  = meta.get("category_sub", "")
        lvl  = str(meta.get("age_level", ""))
        if sub and lvl:
            counts.setdefault(sub, {}).setdefault(lvl, 0)
            counts[sub][lvl] += 1

    for topic in tree.get("topics", []):
        for sub in topic.get("subtopics", []):
            sub_counts = counts.get(sub["id"], {})
            sub["article_counts"] = {
                "level_1": sub_counts.get("1", 0),
                "level_2": sub_counts.get("2", 0),
                "level_3": sub_counts.get("3", 0),
                "total":   sum(sub_counts.values()),
            }

    tree["last_updated"] = datetime.now(timezone.utc).isoformat()
    return tree


# ─────────────────────────────────────────────
# Index-Dateien bauen
# ─────────────────────────────────────────────

def build_indices(articles: list[dict], out_dir: Path) -> dict[str, Path]:
    """
    Baut alle Index-JSONs und schreibt sie nach out_dir/index/.
    Gibt ein Dict {index_name: path} zurück.
    """
    index_dir = out_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    entries = [make_index_entry(a) for a in articles]

    # Nach generated_at sortieren (neueste zuerst)
    entries.sort(key=lambda e: e.get("generated_at") or "", reverse=True)

    written: dict[str, Path] = {}

    def write_index(name: str, data: list[dict], subdir: str = "") -> Path:
        target_dir = index_dir / subdir if subdir else index_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{name}.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count":        len(data),
            "articles":     data,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        log.info("  Index geschrieben: %s (%d Einträge)", path.relative_to(out_dir), len(data))
        written[name] = path
        return path

    # Global
    write_index("global", entries)

    # Pro Altersgruppe
    for level in [1, 2, 3]:
        filtered = [e for e in entries if e.get("age_level") == level]
        write_index(f"level_{level}", filtered)

    # Pro Top-Kategorie
    top_cats: dict[str, list] = {}
    for e in entries:
        cat = e.get("category_top", "unbekannt")
        top_cats.setdefault(cat, []).append(e)
    for cat_id, cat_entries in top_cats.items():
        write_index(f"cat_{cat_id}", cat_entries, subdir="categories")

    # Pro Subkategorie
    sub_cats: dict[str, list] = {}
    for e in entries:
        sub = e.get("category_sub", "unbekannt")
        sub_cats.setdefault(sub, []).append(e)
    for sub_id, sub_entries in sub_cats.items():
        write_index(f"sub_{sub_id}", sub_entries, subdir="subcategories")

    # Neueste 50 (für "Neu diese Woche"-Kachel)
    write_index("new", entries[:50])

    # Review-Queue
    flagged = [e for e in entries if e.get("review_flag")]
    if flagged:
        write_index("review_queue", flagged)
        log.info("  Review-Queue: %d Artikel", len(flagged))

    return written


# ─────────────────────────────────────────────
# Artikel-Dateien ins Staging kopieren
# ─────────────────────────────────────────────

def stage_articles(articles: list[dict], out_dir: Path) -> int:
    """Kopiert Artikel-JSONs (ohne _source_path) nach out_dir/articles/."""
    articles_out = out_dir / "articles"
    articles_out.mkdir(parents=True, exist_ok=True)
    copied = 0
    for article in articles:
        source_path = Path(article.pop("_source_path"))
        article_id  = article["meta"]["id"]
        dest        = articles_out / f"{article_id}.json"
        # Neu schreiben (ohne _source_path)
        dest.write_text(
            json.dumps(article, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        copied += 1
    log.info("Artikel in Staging: %d Dateien", copied)
    return copied


# ─────────────────────────────────────────────
# Run-Metadaten
# ─────────────────────────────────────────────

def write_pipeline_meta(out_dir: Path, articles: list[dict], indices: dict) -> Path:
    meta_dir = out_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    path = meta_dir / "pipeline_run.json"

    level_counts = {str(l): sum(1 for a in articles if a["meta"].get("age_level") == l) for l in [1, 2, 3]}
    pattern_counts: dict[str, int] = {}
    for a in articles:
        p = a["meta"].get("pattern", "unknown")
        pattern_counts[p] = pattern_counts.get(p, 0) + 1

    payload = {
        "run_at":           datetime.now(timezone.utc).isoformat(),
        "schema_version":   "1.0",
        "total_articles":   len(articles),
        "by_age_level":     level_counts,
        "by_pattern":       pattern_counts,
        "review_flagged":   sum(1 for a in articles if a["meta"].get("review_flag")),
        "index_files":      [str(p.name) for p in indices.values()],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Pipeline-Meta: %s", path)
    return path


# ─────────────────────────────────────────────
# R2 Upload via rclone
# ─────────────────────────────────────────────

def upload_to_r2(staging_dir: Path, bucket: str, endpoint: str,
                 access_key: str, secret_key: str) -> bool:
    """
    Lädt den kompletten staging_dir nach R2.
    Nutzt rclone mit env-basierten Credentials (kein Config-File nötig).
    """
    env = os.environ.copy()
    env.update({
        "RCLONE_CONFIG_R2_TYPE":              "s3",
        "RCLONE_CONFIG_R2_PROVIDER":          "Cloudflare",
        "RCLONE_CONFIG_R2_ACCESS_KEY_ID":     access_key,
        "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": secret_key,
        "RCLONE_CONFIG_R2_ENDPOINT":          endpoint,
    })

    cmd = [
        _find_rclone(), "copy",
        str(staging_dir),
        f"r2:{bucket}/",
        "--transfers", "20",
        "--checkers", "40",
        "--progress",
        "--stats", "30s",
        "--log-level", "INFO",
    ]

    log.info("rclone copy → r2:%s/", bucket)
    result = subprocess.run(cmd, env=env)

    if result.returncode != 0:
        log.error("rclone fehlgeschlagen (exit %d)", result.returncode)
        return False

    log.info("R2-Upload erfolgreich")
    return True


_RCLONE_WINGET = (
    Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
)

def _find_rclone() -> str:
    """Returns 'rclone' if in PATH, otherwise searches WinGet packages."""
    import shutil
    if shutil.which("rclone"):
        return "rclone"
    # WinGet install location on Windows
    if _RCLONE_WINGET.exists():
        for exe in _RCLONE_WINGET.rglob("rclone.exe"):
            return str(exe)
    return "rclone"


def check_rclone() -> bool:
    try:
        subprocess.run([_find_rclone(), "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Wissensfreund Artikel-Pipeline — Schritt 3: upload_articles")
    p.add_argument("--articles-dir",  required=True,          type=Path)
    p.add_argument("--topic-tree",    required=True,          type=Path)
    p.add_argument("--out-dir",       default="upload_staging", type=Path)
    p.add_argument("--bucket",        default="wissensfreund-articles")
    p.add_argument("--include-errors", action="store_true",
                   help="Auch Artikel aus _errors/ in den Index aufnehmen")
    p.add_argument("--dry-run",       action="store_true",
                   help="Staging aufbauen, aber kein R2-Upload")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # R2-Credentials aus Umgebung
    access_key = os.environ.get("CF_R2_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
    account_id = os.environ.get("CF_ACCOUNT_ID", "")
    endpoint   = f"https://{account_id}.r2.cloudflarestorage.com" if account_id else ""

    if not args.dry_run:
        missing = [k for k, v in [
            ("CF_R2_ACCESS_KEY_ID",     access_key),
            ("CF_R2_SECRET_ACCESS_KEY", secret_key),
            ("CF_ACCOUNT_ID",           account_id),
        ] if not v]
        if missing:
            raise SystemExit(f"Fehlende Umgebungsvariablen: {', '.join(missing)}")
        if not check_rclone():
            raise SystemExit("rclone nicht gefunden — bitte installieren")

    # Staging aufräumen
    if args.out_dir.exists():
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir(parents=True)

    # 1. Artikel laden
    articles = load_articles(args.articles_dir, include_errors=args.include_errors)
    if not articles:
        raise SystemExit(f"Keine Artikel in {args.articles_dir} gefunden")

    # Plausibilitätsprüfung
    if len(articles) > 100_000:
        raise SystemExit(f"Unplausibel: {len(articles)} Artikel — abgebrochen")

    # 2. Artikel ins Staging kopieren
    stage_articles(articles, args.out_dir)

    # 3. Topic-Tree anreichern + schreiben
    tree = load_topic_tree(args.topic_tree)
    enriched_tree = enrich_topic_tree(tree, articles)
    tree_path = args.out_dir / "index" / "topic_tree.json"
    tree_path.parent.mkdir(parents=True, exist_ok=True)
    tree_path.write_text(
        json.dumps(enriched_tree, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Topic-Tree (angereichert): %s", tree_path)

    # 4. Indices bauen
    indices = build_indices(articles, args.out_dir)

    # 5. Pipeline-Meta
    write_pipeline_meta(args.out_dir, articles, indices)

    # Zusammenfassung
    total = len(articles)
    flagged = sum(1 for a in articles if a["meta"].get("review_flag"))
    log.info("Staging fertig: %d Artikel, %d mit review_flag", total, flagged)
    log.info("Staging-Verzeichnis: %s", args.out_dir)

    if args.dry_run:
        log.info("DRY-RUN: kein R2-Upload")
        _print_staging_summary(args.out_dir)
        return

    # 6. R2 Upload
    ok = upload_to_r2(args.out_dir, args.bucket, endpoint, access_key, secret_key)
    if not ok:
        sys.exit(1)

    log.info("Pipeline Schritt 3 abgeschlossen ✓")


def _print_staging_summary(out_dir: Path) -> None:
    print("\nStaging-Inhalt:")
    for path in sorted(out_dir.rglob("*.json")):
        size_kb = path.stat().st_size / 1024
        print(f"  {str(path.relative_to(out_dir)):<55} {size_kb:6.1f} KB")


if __name__ == "__main__":
    main()
