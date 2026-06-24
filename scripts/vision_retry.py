#!/usr/bin/env python3
"""vision_retry.py — Vision-Nachlauf für Bilder ohne Verdict aus Stage 1.

Liest <output_dir>/stage1_checkpoint.json, sammelt alle images_vision_failed[]
über alle Topics und ruft analyze_with_vision (aus image_vision_filter) erneut auf.
Erfolgreiche Bilder werden mit derselben Akzeptanz-Logik wie run_batch.py geprüft
und ggf. zu topic["images"] hinzugefügt; dauerhaft fehlschlagende landen in
topic["images_vision_permanently_failed"]. Checkpoint wird atomar zurückgeschrieben.

  usage: python scripts/vision_retry.py <output_dir> [--max-retries 3] [--wait 60]

Exit 0, wenn images_vision_failed[] überall leer ist; Exit 1, wenn Einträge bleiben.
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).parent))

import requests  # noqa: E402
from image_vision_filter import (  # noqa: E402
    analyze_with_vision,
    download_image,
)
from generate_articles import USER_AGENT  # noqa: E402

VISION_MODEL = "gemini-2.5-flash"   # identisch zu run_batch.py

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vision_retry")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _accept(img_meta: dict, result: dict) -> dict | None:
    """Akzeptanz-Logik aus run_batch.py (Phase A, Conservative Upgrade).
    Gibt approved-Eintrag zurück oder None (verworfen)."""
    ab_stufe        = result.get("ab_stufe", 0)
    grenzfall       = result.get("grenzfall", False)
    grenzfall_grund = result.get("grenzfall_grund", "")
    confidence      = result.get("confidence", "hoch")
    beschreibung    = result.get("beschreibung", "")
    relevanz        = result.get("relevanz", 0)
    hero            = result.get("hero_candidate", False)
    if grenzfall and ab_stufe == 1:
        ab_stufe = 2
    if ab_stufe == 0 or relevanz < 4:
        return None
    base = {k: v for k, v in img_meta.items() if k != "vision_fail_reason"}
    return {
        **base,
        "ab_stufe":        ab_stufe,
        "grenzfall":       grenzfall,
        "grenzfall_grund": grenzfall_grund,
        "confidence":      confidence,
        "relevanz":        relevanz,
        "hero_candidate":  hero,
        "beschreibung":    beschreibung,
    }


def _retry_one(client, session, thema_vision, img_meta, max_retries, wait):
    """Mehrfacher Vision-Versuch für ein Bild. Gibt result-dict oder None."""
    url = img_meta.get("thumb_url") or img_meta.get("original_url")
    if not url:
        log.warning("    kein thumb_url/original_url: %s", img_meta.get("filename", "?"))
        return None
    for attempt in range(1, max_retries + 1):
        img_bytes = download_image(session, url)
        if img_bytes is None:
            log.warning("    Download fehlgeschlagen (V%d/%d): %s",
                        attempt, max_retries, img_meta.get("filename", "?")[:40])
        else:
            result, _ = analyze_with_vision(
                client, img_bytes, "image/jpeg", thema_vision, model=VISION_MODEL
            )
            if result is not None:
                return result
            log.warning("    Vision kein Ergebnis (V%d/%d): %s",
                        attempt, max_retries, img_meta.get("filename", "?")[:40])
        if attempt < max_retries:
            log.info("    warte %ds vor nächstem Versuch ...", wait)
            time.sleep(wait)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Vision-Nachlauf für Stage-1-Bilder ohne Verdict")
    ap.add_argument("output_dir", help="Stage-1-Ausgabeverzeichnis (enthält stage1_checkpoint.json)")
    ap.add_argument("--max-retries", type=int, default=3, help="Versuche pro Bild (Default 3)")
    ap.add_argument("--wait", type=int, default=60, help="Sekunden Pause zwischen Versuchen (Default 60)")
    args = ap.parse_args()

    out_dir = Path(args.output_dir).resolve()
    cp_path = out_dir / "stage1_checkpoint.json"
    if not cp_path.exists():
        log.error("Checkpoint nicht gefunden: %s", cp_path)
        return 1

    cp = json.loads(cp_path.read_text(encoding="utf-8"))
    topics = cp.get("topics", {})

    total_failed = sum(len(v.get("images_vision_failed", [])) for v in topics.values())
    if total_failed == 0:
        log.info("Keine images_vision_failed — nichts zu tun.")
        return 0

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        return 1
    client = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    log.info("Vision-Retry: %d Bild(er) über %d Topic(s) | max-retries=%d wait=%ds",
             total_failed, len(topics), args.max_retries, args.wait)

    remaining_total = 0
    for thema, entry in topics.items():
        failed = entry.get("images_vision_failed", [])
        if not failed:
            continue
        resolved_title = entry.get("resolved_title", thema)
        images          = entry.setdefault("images", [])
        perm_failed     = entry.setdefault("images_vision_permanently_failed", [])
        still_failed: list[dict] = []
        n_approved = 0
        log.info("Thema '%s': %d Bild(er) zu wiederholen", thema, len(failed))

        for img_meta in failed:
            source = img_meta.get("_source", "")
            if source and source != resolved_title:
                thema_vision = f"{thema} (Bild aus Begleitartikel: {source})"
            else:
                thema_vision = thema
            result = _retry_one(client, session, thema_vision, img_meta,
                                args.max_retries, args.wait)
            if result is None:
                perm_failed.append({**img_meta, "vision_fail_reason": "permanent_after_retries"})
                continue
            approved = _accept(img_meta, result)
            if approved is not None:
                images.append(approved)
                n_approved += 1
                log.info("    approved [S%d][rel=%d]: %s",
                         approved["ab_stufe"], approved["relevanz"],
                         img_meta.get("filename", "?")[:40])
            else:
                log.info("    Verdict erhalten, aber verworfen (ab_stufe/relevanz): %s",
                         img_meta.get("filename", "?")[:40])

        # neu sortieren (relevanz desc, hero desc) — konsistent zu run_batch Phase A
        images.sort(key=lambda x: (-x.get("relevanz", 0), -int(x.get("hero_candidate", False))))
        entry["images"]                          = images
        entry["images_vision_failed"]            = still_failed
        entry["images_vision_permanently_failed"] = perm_failed
        n_perm = len([p for p in perm_failed if p.get("vision_fail_reason") == "permanent_after_retries"])
        remaining_total += len(still_failed)
        log.info("  → %s: %d neu approved, %d permanent failed, %d images_vision_failed verbleibend",
                 thema, n_approved, len(perm_failed), len(still_failed))

    # atomar zurückschreiben
    tmp = cp_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cp, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, cp_path)
    log.info("Checkpoint aktualisiert: %s", cp_path.name)

    if remaining_total == 0:
        log.info("Alle images_vision_failed[] geleert.")
        return 0
    log.error("%d Bild(er) bleiben in images_vision_failed[].", remaining_total)
    return 1


if __name__ == "__main__":
    sys.exit(main())
