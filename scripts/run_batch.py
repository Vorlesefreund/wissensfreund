#!/usr/bin/env python3
"""
run_batch.py
Batch-Orchestrator — Wissensfreund Vollkatalog-Produktion.

Stage 1 — SOURCING [implementiert]:
  WP-Fetch (sync) → Kompass (Gemini Batch) → Companion-Fetch (sync)
  → Image-Download + Vision (Gemini Batch)
  → Conservative Upgrade (lokal)
  → Opus-Recheck (Anthropic Batch, nur sensibel + confidence=niedrig)

Stage 2 — GENERIERUNG [Gerüst, TODO]:
  Gemini Batch mit Context Cache, select_images_for_stufe, Post-Processing

Stage 3 — LEKTORAT [Gerüst, TODO]:
  Anthropic Message Batches, Pass 1 (source_passages) + Pass 2 (volltexte)

Stage 4 — TTS [Stub]:
  ThreadPool via tts_produce.py (nächster Baustein)

Usage:
  python scripts/run_batch.py --themen "Elefant" "Hund" "Dinosaurier" "Vulkan" "Tabak" --dry-run
  python scripts/run_batch.py --themen "Elefant" "Hund" --stage 1
  python scripts/run_batch.py --catalog-rank 5
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


def _normalize_custom_id(s: str) -> str:
    """Normalize to ^[a-zA-Z0-9_-]{1,64}$ (Anthropic Batch API requirement)."""
    for src, dst in [("ä","ae"),("ö","oe"),("ü","ue"),("Ä","Ae"),("Ö","Oe"),("Ü","Ue"),("ß","ss")]:
        s = s.replace(src, dst)
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", s)
    return s[:64]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import cost_tracker  # noqa: E402
from generate_articles import (  # noqa: E402
    fetch_wikipedia_text,
    resolve_lemma,
    parse_article_json,
    validate_article,
    USER_AGENT,
)
from generate_grounded import (  # noqa: E402
    COMPANION_SYSTEM_PROMPT,
    COMPANION_PROMPT_TMPL,
    COMPANION_CAP,
    SYSTEM_PROMPT_PATH,
    GEMINI_MODEL as GEN_MODEL,
    APPEAL_TARGET,
    MAX_VISION_CHECKS,
    MAX_IMG_PRIMARY,
    MAX_IMG_COMPANION,
    CATALOG_PATH,
    validate_and_resolve_companions,
    select_images_for_stufe,
    build_grounded_user_message,
    _split_grounded_user_message,
    _variable_suffix,
    try_create_gemini_cache,
    wortziel_for,
    appeal_for,
    eignung_for,
    count_article_words,
    _box_lint,
    _trim_article_to_cap,
    _box_repair_pass,
    _make_thinking_config,
    _build_catalog_jobs,
    _load_catalog_rank_jobs,
)
from image_vision_filter import (  # noqa: E402
    fetch_image_candidates,
    download_image,
    load_cached_image_bytes,
    get_download_sizes,
    clear_download_sizes,
    analyze_with_vision,
    OPUS_RECHECK_SYSTEM,
    OPUS_RECHECK_PROMPT,
)
from lektorat_common import (  # noqa: E402
    LEKTORAT_SYSTEM,
    LEKTORAT_MODEL,
    COMPANION_CHAR_CAP,
    build_lektorat_parts,
    parse_lektorat_v2,
    annotate_article_lektorat_v2,
    build_grounded_sources_block,
)
import gemini_client  # noqa: E402

# ── Konstanten ────────────────────────────────────────────────────────────────

VISION_MODEL         = "gemini-2.5-flash"
VISION_CHUNK_SIZE    = 500   # ungenutzt seit Sync-Umbau (war: max InlinedRequests/Batch)
POLL_SECS_GEMINI     = 30
POLL_SECS_ANTHROPIC  = 30
GEMINI_TIMEOUT_H     = 48.0
ANTHROPIC_TIMEOUT_H  = 24.0

DONE_STATES    = {
    "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED",
    "JOB_STATE_PARTIALLY_SUCCEEDED", "JOB_STATE_EXPIRED",
}
SUCCESS_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}

# Opus-Recheck: max Bilder pro Thema (sensibel: top-18 nach Relevanz → Stage 2 zieht NUR daraus)
OPUS_CAP = max(APPEAL_TARGET.values()) + 3  # 18 (high-Ziel 15 + 3 Puffer)

_RUN_ID: str = ""


# ── Checkpoint-Helfer ─────────────────────────────────────────────────────────

def _cp_path(out_dir: Path, stage: int) -> Path:
    return out_dir / f"stage{stage}_checkpoint.json"


def _save_cp(out_dir: Path, stage: int, data: dict) -> None:
    p = _cp_path(out_dir, stage)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Checkpoint gespeichert: %s", p.name)


def _load_cp(out_dir: Path, stage: int) -> dict | None:
    p = _cp_path(out_dir, stage)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("status") == "done":
        log.info("Checkpoint Stage %d vorhanden (status=done) — Stage übersprungen", stage)
        return data
    log.info("Checkpoint Stage %d vorhanden, status=%s — neu ausführen", stage, data.get("status"))
    return None


# ── Poll-Helfer ───────────────────────────────────────────────────────────────

def _state_str(batch_job) -> str:
    s = getattr(batch_job, "state", None)
    if s is None:
        return "unknown"
    return s.value if hasattr(s, "value") else str(s)


def _extract_text(response) -> str:
    if response is None:
        return ""
    text = getattr(response, "text", None)
    if text:
        return text
    for cand in getattr(response, "candidates", []):
        parts = []
        for part in getattr(getattr(cand, "content", None), "parts", []) or []:
            if not getattr(part, "thought", False) and getattr(part, "text", None):
                parts.append(part.text)
        if parts:
            return "".join(parts)
    return ""


def _strip_md(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    return re.sub(r"\n?```$", "", text).strip()


def _extract_usage(response) -> dict:
    um = getattr(response, "usage_metadata", None)
    if um is None:
        return {}
    return {
        "input_tok":    int(getattr(um, "prompt_token_count", 0) or 0),
        "output_tok":   int(getattr(um, "candidates_token_count", 0) or 0),
        "cached_tok":   int(getattr(um, "cached_content_token_count", 0) or 0),
        "thoughts_tok": int(getattr(um, "thoughts_token_count", 0) or 0),
    }


def poll_gemini_batch(
    client: genai.Client,
    batch_name: str,
    poll_secs: int = POLL_SECS_GEMINI,
    timeout_hours: float = GEMINI_TIMEOUT_H,
):
    deadline = time.monotonic() + timeout_hours * 3600
    log.info("Polling Gemini-Batch %s ...", batch_name[-30:])
    while True:
        job   = client.batches.get(name=batch_name)
        state = _state_str(job)
        log.info("  Batch %s → %s", batch_name[-30:], state)
        if state in DONE_STATES:
            return job
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Gemini-Batch {batch_name} nach {timeout_hours}h nicht fertig"
            )
        time.sleep(poll_secs)


def poll_anthropic_batch(anth_client, batch_id: str,
                         poll_secs: int = POLL_SECS_ANTHROPIC,
                         timeout_hours: float = ANTHROPIC_TIMEOUT_H):
    deadline = time.monotonic() + timeout_hours * 3600
    log.info("Polling Anthropic-Batch %s ...", batch_id[:20])
    while True:
        batch = anth_client.messages.batches.retrieve(batch_id)
        c = batch.request_counts
        log.info(
            "  Batch %s … %s (✓%d ✗%d ⌛%d)",
            batch_id[:20], batch.processing_status,
            c.succeeded, c.errored, c.processing,
        )
        if batch.processing_status == "ended":
            return batch
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Anthropic-Batch {batch_id} nach {timeout_hours}h nicht fertig"
            )
        time.sleep(poll_secs)


def _get_inlined_responses(batch_job) -> list:
    return getattr(getattr(batch_job, "dest", None), "inlined_responses", None) or []


# ── Stage 1: SOURCING ─────────────────────────────────────────────────────────

def stage1_sourcing(
    themen: list[str],
    out_dir: Path,
    client: genai.Client,
    session: requests.Session,
    api_key: str,
    anthropic_key: str | None,
    dry_run: bool = False,
) -> dict:
    """
    Stage 1 vollständig:
    WP-Fetch → Kompass-Batch → Companion-Fetch → Image-Download
    → Vision-Batch → Conservative Upgrade → Opus-Recheck-Batch

    Rückgabe: {thema: {primary_text, resolved_title, appeal, sensibel,
                        valid_companions, companion_texts, images}}
    """
    cp = _load_cp(out_dir, 1)
    if cp:
        return cp["topics"]

    # Catalog für sensibel/eignung laden
    catalog_by_thema: dict[str, dict] = {}
    if CATALOG_PATH.exists():
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog_by_thema = {e["thema"].strip().lower(): e for e in catalog}

    # ── Step 1: WP-Fetch + Lemma (sync) ──────────────────────────────────────
    log.info("\n=== Stage 1 / Step 1: WP-Fetch + Lemma (%d Themen) ===", len(themen))
    wp_data: dict[str, dict] = {}

    for thema in themen:
        ev = eignung_for(thema)
        if ev["eignung"] == "exclude":
            log.info("  Eignung EXCLUDE: '%s' — übersprungen", thema)
            continue

        cat_entry = catalog_by_thema.get(thema.strip().lower(), {})
        sensibel  = bool(cat_entry.get("sensibel", False))
        appeal, _ = appeal_for(thema, cat_entry.get("topic_interest"))

        try:
            lr = resolve_lemma(session, thema)
        except Exception as e:
            log.warning("  resolve_lemma('%s') Fehler: %s", thema, e)
            lr = {"resolved_title": None, "flags": []}

        resolved_title = lr.get("resolved_title") or thema
        lemma_flags    = lr.get("flags", [])

        time.sleep(1.0)
        try:
            primary_text = fetch_wikipedia_text(session, resolved_title)
        except Exception as e:
            log.error("  WP-Fetch '%s': %s — übersprungen", resolved_title, e)
            continue

        if len(primary_text) < 300:
            log.error("  WP-Fetch '%s': zu kurz (%d Zeichen) — übersprungen",
                      resolved_title, len(primary_text))
            continue

        log.info("  '%s' → '%s': %d Zeichen | appeal=%s | sensibel=%s",
                 thema, resolved_title, len(primary_text), appeal, sensibel)

        wp_data[thema] = {
            "primary_text":   primary_text,
            "resolved_title": resolved_title,
            "lemma_flags":    lemma_flags,
            "framing_note":   ev.get("framing_note", ""),
            "appeal":         appeal,
            "sensibel":       sensibel,
        }

    if not wp_data:
        raise RuntimeError("Kein Thema WP-fetchbar — Stage 1 abgebrochen")

    if dry_run:
        print(f"\n=== DRY-RUN Stage 1 ===")
        print(f"WP-Fetch OK: {list(wp_data.keys())}")
        print(f"Kompass-Batch: {len(wp_data)} InlinedRequests")
        n_sens = sum(1 for d in wp_data.values() if d["sensibel"])
        print(f"Vision-Check (sync): ~{len(wp_data) * MAX_VISION_CHECKS} Aufrufe (max {MAX_VISION_CHECKS}/Thema)")
        print(f"Opus-Recheck: {n_sens} sensible Themen → top-{OPUS_CAP} Bilder (relevanz-sortiert); sonst → grenzfall=true (max {OPUS_CAP})")
        return {}

    # ── Step 2: Kompass-Batch (Gemini) ────────────────────────────────────────
    log.info("\n=== Stage 1 / Step 2: Kompass-Batch (%d Requests) ===", len(wp_data))
    kompass_reqs: list[types.InlinedRequest] = []
    for thema, data in wp_data.items():
        lead   = data["primary_text"][:1500]
        prompt = COMPANION_PROMPT_TMPL.format(thema=thema, lead=lead)
        kompass_reqs.append(types.InlinedRequest(
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=COMPANION_SYSTEM_PROMPT,
                temperature=0.3,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM),
                response_mime_type="application/json",
            ),
            metadata={"key": thema},
        ))

    batch_k      = client.batches.create(model=GEN_MODEL, src=kompass_reqs)
    log.info("Kompass-Batch eingereicht: %s", batch_k.name)
    batch_k_done = poll_gemini_batch(client, batch_k.name)
    if _state_str(batch_k_done) not in SUCCESS_STATES:
        raise RuntimeError(f"Kompass-Batch fehlgeschlagen: {_state_str(batch_k_done)}")

    raw_companions_by_thema: dict[str, list[str]] = {t: [] for t in wp_data}
    for resp in _get_inlined_responses(batch_k_done):
        thema_key = (resp.metadata or {}).get("key", "")
        if not thema_key or thema_key not in wp_data:
            continue
        if resp.error:
            log.warning("  Kompass '%s': %s", thema_key, resp.error)
            continue
        text = _strip_md(_extract_text(resp.response))
        try:
            raw = [str(c) for c in json.loads(text).get("companions", [])][:10]
        except json.JSONDecodeError:
            log.warning("  Kompass '%s': JSON-Fehler (%r)", thema_key, text[:60])
            raw = []
        u = _extract_usage(resp.response)
        if u:
            cost_tracker.track(run_id=_RUN_ID, thema=thema_key, stufe="S0",
                               schritt="kompass", modell=GEN_MODEL, **u)
        log.info("  Kompass '%s': %d Vorschläge", thema_key, len(raw))
        raw_companions_by_thema[thema_key] = raw

    # ── Step 3: Companion Validate + Fetch (sync) ─────────────────────────────
    log.info("\n=== Stage 1 / Step 3: Companion Validate + Fetch ===")
    for thema, data in wp_data.items():
        companion_cap = COMPANION_CAP.get(data["appeal"], 5)
        valid_companions, _, _ = validate_and_resolve_companions(
            session,
            raw_companions_by_thema.get(thema, []),
            data["resolved_title"],
            cap=companion_cap,
        )
        log.info("  '%s': %d Companions validiert", thema, len(valid_companions))

        companion_texts: dict[str, str] = {}
        for comp in valid_companions:
            time.sleep(0.5)
            try:
                ct = fetch_wikipedia_text(session, comp)
                companion_texts[comp] = ct
                log.info("    '%s': %d Zeichen", comp, len(ct))
            except Exception as e:
                log.warning("    Companion '%s' Fehler: %s", comp, e)

        data["valid_companions"] = valid_companions
        data["companion_texts"]  = companion_texts

    # ── Step 4: Image Candidates + Download (sync, kein 10s-Sleep) ────────────
    log.info("\n=== Stage 1 / Step 4: Image Download + Vision-Check (sync) ===")
    img_meta_by_key:   dict[str, dict] = {}
    topic_img_keys:    dict[str, list[str]] = defaultdict(list)
    all_vision_results: dict[str, dict] = {}  # key → {ab_stufe, confidence, ...}

    for thema, data in wp_data.items():
        primary_wp = data["resolved_title"]
        companions = [c for c in data["valid_companions"] if c in data["companion_texts"]]

        # Kandidaten sammeln
        all_candidates: list[dict] = []
        primary_imgs = fetch_image_candidates(
            session, primary_wp, max_candidates=MAX_IMG_PRIMARY
        )
        for img in primary_imgs:
            img["_source"] = primary_wp
        all_candidates.extend(primary_imgs)

        for comp in companions:
            time.sleep(0.3)
            comp_imgs = fetch_image_candidates(
                session, comp, max_candidates=MAX_IMG_COMPANION
            )
            for img in comp_imgs:
                img["_source"] = comp
            all_candidates.extend(comp_imgs)

        # Deduplizieren
        seen_fn: set[str] = set()
        unique: list[dict] = []
        for img in all_candidates:
            if img["filename"] not in seen_fn:
                seen_fn.add(img["filename"])
                unique.append(img)

        to_check = unique[:MAX_VISION_CHECKS]
        log.info("  '%s': %d Kandidaten, Vision-Check max %d",
                 thema, len(unique), len(to_check))

        # Herunterladen + synchroner Vision-Check (3s pre-download, Wikimedia-konform)
        for i, img in enumerate(to_check):
            if i > 0:
                time.sleep(3.0)
            img_bytes = download_image(session, img["thumb_url"])
            if img_bytes is None:
                log.debug("    Download fehlgeschlagen: %s", img["filename"][:40])
                continue

            # Schlüssel: nur [a-zA-Z0-9_-], max 64 Zeichen (für Opus-custom_id-Lookup)
            safe_t  = re.sub(r"[^a-zA-Z0-9_-]", "_", thema)[:20]
            safe_fn = re.sub(r"[^a-zA-Z0-9_-]", "_", img["filename"])[:41]
            key     = f"{safe_t}__{safe_fn}"
            img_meta_by_key[key] = {**img, "thema": thema}
            topic_img_keys[thema].append(key)

            # Synchroner Einzelaufruf statt Batch (kein 24h-Queue-Risiko)
            result, usage = analyze_with_vision(
                client, img_bytes, "image/jpeg", thema, model=VISION_MODEL
            )
            if result is None:
                log.warning("  Vision '%s': kein Ergebnis", key[:40])
                continue
            all_vision_results[key] = result
            if usage:
                cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                                   schritt="vision", modell=VISION_MODEL,
                                   input_tok=usage["input_tok"], output_tok=usage["output_tok"])

        data["_img_candidates"] = unique

    log.info("Vision-Check (sync): %d Bilder analysiert", len(all_vision_results))

    # ── Step 6: Conservative Upgrade + Bildpool aufbauen ──────────────────────
    log.info("\n=== Stage 1 / Step 6: Vision-Ergebnisse verarbeiten ===")
    opus_kandidaten: list[dict] = []

    for thema, data in wp_data.items():
        accepted: list[dict] = []
        n_rejected = 0
        # Lookup: filename → Batch-Key (für Opus custom_id)
        filename_to_key: dict[str, str] = {}

        for key in topic_img_keys.get(thema, []):
            img_meta = img_meta_by_key.get(key, {})
            result   = all_vision_results.get(key)
            if result is None:
                n_rejected += 1
                continue

            ab_stufe        = result.get("ab_stufe", 0)
            grenzfall       = result.get("grenzfall", False)
            grenzfall_grund = result.get("grenzfall_grund", "")
            confidence      = result.get("confidence", "hoch")
            beschreibung    = result.get("beschreibung", "")
            relevanz        = result.get("relevanz", 0)
            hero            = result.get("hero_candidate", False)

            # Conservative Upgrade: grenzfall=true verhindert ab_stufe=1
            if grenzfall and ab_stufe == 1:
                ab_stufe = 2
                log.info("    grenzfall=true: '%s' → ab_stufe 1→2 (%s)",
                         img_meta.get("filename", "")[:40], grenzfall_grund[:60])

            if ab_stufe == 0 or relevanz < 4:
                n_rejected += 1
                continue

            entry = {
                **img_meta,
                "ab_stufe":        ab_stufe,
                "grenzfall":       grenzfall,
                "grenzfall_grund": grenzfall_grund,
                "confidence":      confidence,
                "relevanz":        relevanz,
                "hero_candidate":  hero,
                "beschreibung":    beschreibung,
            }
            accepted.append(entry)
            filename_to_key[img_meta.get("filename", "")] = key

        accepted.sort(key=lambda x: (-x["relevanz"], -int(x.get("hero_candidate", False))))

        if data["sensibel"]:
            # Sensible Themen: nur top-OPUS_CAP Bilder prüfen lassen;
            # Stage 2 zieht ausschließlich aus diesem geprüften Pool.
            opus_pool = accepted[:OPUS_CAP]
            data["images"] = opus_pool
            if anthropic_key:
                for e in opus_pool:
                    opus_kandidaten.append({
                        "thema": thema,
                        "key":   filename_to_key.get(e.get("filename", ""), ""),
                        "img":   e,
                    })
        else:
            data["images"] = accepted
            # Nicht-sensibel: nur grenzfall=true-Bilder → Opus, auch gecappt
            if anthropic_key:
                gz_pool = [e for e in accepted if e.get("grenzfall", False)][:OPUS_CAP]
                for e in gz_pool:
                    opus_kandidaten.append({
                        "thema": thema,
                        "key":   filename_to_key.get(e.get("filename", ""), ""),
                        "img":   e,
                    })

        n_sensibel_opus = len([c for c in opus_kandidaten if c["thema"] == thema])
        log.info("  '%s': %d akzeptiert, %d verworfen → Opus: %d",
                 thema, len(accepted), n_rejected, n_sensibel_opus)

    # ── Step 7: Opus-Recheck (Anthropic Batch) ────────────────────────────────
    if opus_kandidaten and anthropic_key:
        log.info("\n=== Stage 1 / Step 7: Opus-Recheck (%d Bilder) ===",
                 len(opus_kandidaten))
        try:
            import anthropic as _anthropic
            anth = _anthropic.Anthropic(api_key=anthropic_key)

            opus_reqs = []
            key_to_thema: dict[str, str] = {}
            for cand in opus_kandidaten:
                img_bytes = load_cached_image_bytes(cand["img"]["thumb_url"])
                if img_bytes is None:
                    log.warning("  Opus: Cache fehlt für %s — Gemini-Urteil behalten",
                                cand["img"].get("filename", "")[:40])
                    continue
                prompt = OPUS_RECHECK_PROMPT.format(thema=cand["thema"])
                custom_id = _normalize_custom_id(cand["key"])
                key_to_thema[custom_id] = cand["thema"]
                opus_reqs.append({
                    "custom_id": custom_id,
                    "params": {
                        "model":      "claude-opus-4-8",
                        "max_tokens": 256,
                        "system":     OPUS_RECHECK_SYSTEM,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type":       "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(img_bytes).decode(),
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }],
                    },
                })

            if opus_reqs:
                opus_batch = anth.messages.batches.create(requests=opus_reqs)
                log.info("Opus-Recheck-Batch eingereicht: %s (%d Requests)",
                         opus_batch.id, len(opus_reqs))
                poll_anthropic_batch(anth, opus_batch.id)

                for result in anth.messages.batches.results(opus_batch.id):
                    if result.result.type != "succeeded":
                        continue
                    raw = result.result.message.content[0].text.strip()
                    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
                    raw = re.sub(r"\n?```$", "", raw)
                    try:
                        opus_res = json.loads(raw)
                    except Exception:
                        continue

                    cid      = result.custom_id
                    thema    = key_to_thema.get(cid, "")
                    new_ab   = int(opus_res.get("ab_stufe", 0))
                    new_desc = opus_res.get("beschreibung", "")
                    u        = result.result.message.usage
                    cost_tracker.track(
                        run_id=_RUN_ID, thema=thema, stufe="S0",
                        schritt="vision_recheck", modell="claude-opus-4-8",
                        input_tok=u.input_tokens, output_tok=u.output_tokens,
                    )

                    # Bild in pool aktualisieren
                    if thema and thema in wp_data:
                        imgs = wp_data[thema]["images"]
                        target_fn = img_meta_by_key.get(cid, {}).get("filename", "")
                        for i, img in enumerate(imgs):
                            if img.get("filename") == target_fn:
                                if new_ab == 0:
                                    imgs.pop(i)
                                    log.info("  Opus SPERRT: %s", target_fn[:40])
                                else:
                                    if new_ab != img["ab_stufe"]:
                                        log.info("  Opus: %s %d→%d",
                                                 target_fn[:35], img["ab_stufe"], new_ab)
                                    imgs[i] = {**img, "ab_stufe": new_ab,
                                               "beschreibung": new_desc}
                                break

        except Exception as e:
            log.error("Opus-Recheck-Batch Fehler: %s — Gemini-Urteile behalten", e)

    # ── Ergebnis zusammenbauen + Checkpoint ───────────────────────────────────
    topics_data: dict[str, dict] = {}
    for thema, data in wp_data.items():
        imgs = data.get("images", [])
        topics_data[thema] = {
            "primary_text":    data["primary_text"],
            "resolved_title":  data["resolved_title"],
            "lemma_flags":     data["lemma_flags"],
            "framing_note":    data["framing_note"],
            "appeal":          data["appeal"],
            "sensibel":        data["sensibel"],
            "valid_companions": data["valid_companions"],
            "companion_texts":  data["companion_texts"],
            "images":          imgs,
        }
        s1 = sum(1 for i in imgs if i.get("ab_stufe", 0) == 1)
        s2 = sum(1 for i in imgs if i.get("ab_stufe", 0) == 2)
        s3 = sum(1 for i in imgs if i.get("ab_stufe", 0) == 3)
        log.info("  '%s': Pool %d Bilder (S1=%d S2=%d S3=%d)", thema, len(imgs), s1, s2, s3)

    # Speicher-Tabelle: frische Downloads (nicht aus Cache)
    dl_sizes = get_download_sizes()
    if dl_sizes:
        n = len(dl_sizes)
        avg = {k: sum(s[k] for s in dl_sizes) // n // 1024
               for k in ("sz_300", "sz_600", "sz_800", "sz_1600")}
        log.info("")
        log.info("=== SPEICHER-TABELLE (%d frische Downloads) ===", n)
        log.info("  Tier   | Ø KB/Bild | 10 Bilder | 15 Bilder")
        log.info("  -------+-----------+-----------+----------")
        for tier, key in [("300px", "sz_300"), ("600px", "sz_600"),
                          ("800px", "sz_800"), ("1600px", "sz_1600")]:
            a = avg[key]
            log.info("  %-6s | %9d | %9d | %9d KB", tier, a, a * 10, a * 15)
        log.info("  (600+800: nur Messung — noch nicht gecacht)")
    clear_download_sizes()

    _save_cp(out_dir, 1, {"status": "done", "topics": topics_data})
    return topics_data


# ── Stage 2 Helpers ───────────────────────────────────────────────────────────

def _stage2_job(thema: str, data: dict, slug: str, stufe: int) -> dict:
    """Job-Dict für Stage 2 aus topics_data."""
    return {
        "article_id":        f"{slug}_l{stufe}",
        "thema":             thema,
        "primaer_wikipedia": data.get("resolved_title", thema),
        "title":             thema,
        "age_level":         stufe,
        "topic_interest":    "medium",
        "sensibel":          data.get("sensibel", False),
        "pattern":           "",
        "category_top":      "",
        "category_sub":      "",
        "framing_note":      data.get("framing_note", ""),
        "resolved_appeal":   data.get("appeal", "medium"),
        "lemma_flags":       data.get("lemma_flags", []),
    }


def _gen2_variable_suffix(job: dict, wmax: int) -> str:
    """Variable Suffix für Stage-2-Batch: AGE_LEVEL + WORTZIEL.
    source_passages ist jetzt kanonisches Schema-Feld (System-Prompt) — kein Wrapper mehr nötig."""
    return _variable_suffix(job, wmax)


def _parse_gen2_response(raw: str) -> tuple[dict, list]:
    """Parse Stage-2-Batch-Antwort: Wrapper-JSON {article, source_passages} oder plain Article.
    Gibt (article_dict, source_passages_list) zurück."""
    cleaned = re.sub(r"<planung>.*?</planung>", "", raw or "", flags=re.DOTALL)
    cleaned = _strip_md(cleaned).strip()
    try:
        outer = json.loads(cleaned)
        if isinstance(outer, dict) and "article" in outer:
            art = outer["article"]
            for sec in art.get("sections", []):
                for s in sec.get("sentences", []):
                    if s.get("img_index") is None:
                        s["img_index"] = -1
            return art, outer.get("source_passages", [])
    except (json.JSONDecodeError, ValueError):
        pass
    return parse_article_json(raw), []


def _set_is_hero(article: dict, images_stufe: list[dict], thema: str,
                 primary_wikipedia: str | None = None) -> None:
    """Setzt is_hero=True auf dem besten Hero-Kandidaten, tiers-Pfade auf allen Bildern.

    Hero-Priorität:
    1. Bilder aus dem Primärartikel (_source == primary_wikipedia) mit hero_candidate=True
    2. Fallback: beliebiges Bild mit hero_candidate=True (höchste Relevanz zuerst)
    3. Letzter Fallback: erstes Bild im Pool
    Nur Bilder aus images_stufe (von der Pipeline akzeptiert und altersgerecht).
    """
    thema_slug = thema.lower().replace(" ", "_").replace("/", "_")
    pool = {img["filename"]: img for img in images_stufe}

    # Bevorzuge Hero-Kandidaten aus dem Primärartikel
    if primary_wikipedia:
        primary_heroes = [
            img for img in images_stufe
            if img.get("hero_candidate") and img.get("_source") == primary_wikipedia
        ]
        if primary_heroes:
            hero_fname = primary_heroes[0]["filename"]  # bereits nach relevanz sortiert
        else:
            hero_fname = next(
                (img["filename"] for img in images_stufe if img.get("hero_candidate")),
                images_stufe[0]["filename"] if images_stufe else None,
            )
    else:
        hero_fname = next(
            (img["filename"] for img in images_stufe if img.get("hero_candidate")),
            images_stufe[0]["filename"] if images_stufe else None,
        )
    for art_img in article.get("images", []):
        fname    = art_img.get("filename", "")
        pool_img = pool.get(fname, {})
        art_img["is_hero"]   = (fname == hero_fname)
        art_img["ab_stufe"]  = pool_img.get("ab_stufe", 1)
        art_img["grenzfall"] = pool_img.get("grenzfall", False)
        if not art_img.get("thumb_url") and pool_img.get("thumb_url"):
            art_img["thumb_url"] = pool_img["thumb_url"]
        stem = fname.rsplit(".", 1)[0].replace(" ", "_")
        art_img["tiers"] = {
            "300":  f"bilder/{thema_slug}/{stem}_300.jpg",
            "800":  f"bilder/{thema_slug}/{stem}_800.jpg",
        }


def _limit_images_per_section(article: dict, images_stufe: list[dict]) -> None:
    """Begrenzt Bildwechsel pro Section (greift NACH der Generierung).

    S1 (age_level 1): genau EIN Bild pro Section.
    S2/S3 (age_level 2/3): ein Bild bei <4 Sätzen; bis zu ZWEI ab >=4 Sätzen
      (erste floor(n/2) Sätze Bild A, Rest Bild B).
    Bild-Wahl: häufigster img_index ("Mehrheit"); Tiebreaker = höhere Vision-
    relevanz aus dem Stage-1-Pool (fehlt → 0), dann kleinerer Index.
    Sätze mit img_index=-1 ERBEN das Section-Bild (kein Flackern). Bildlose
    Sections (alle -1) bleiben unverändert. images[] wird NICHT beschnitten.
    """
    images = article.get("images", [])
    if not images:
        return
    age     = article.get("meta", {}).get("age_level", 1)
    relpool = {img.get("filename"): img for img in (images_stufe or [])}

    def relevanz_of(ix: int) -> float:
        if ix < 0 or ix >= len(images):
            return 0
        fn = images[ix].get("filename", "")
        r  = relpool.get(fn, {}).get("relevanz")
        return r if isinstance(r, (int, float)) else 0

    for sec in article.get("sections", []):
        sents = sec.get("sentences", [])
        votes = [s.get("img_index", -1) for s in sents
                 if s.get("img_index", -1) is not None and s.get("img_index", -1) != -1]
        if not votes:
            continue  # bildlose Section unverändert lassen

        counts: dict[int, int] = {}
        for ix in votes:
            counts[ix] = counts.get(ix, 0) + 1
        # häufigster zuerst; Tiebreaker höhere relevanz, dann kleinerer Index
        ranked = sorted(counts, key=lambda ix: (-counts[ix], -relevanz_of(ix), ix))

        n         = len(sents)
        allow_two = age in (2, 3) and n >= 4 and len(ranked) >= 2

        if not allow_two:
            chosen = ranked[0]
            for s in sents:
                s["img_index"] = chosen
        else:
            a, b = ranked[0], ranked[1]
            half = n // 2  # floor(n/2) Sätze → Bild A, Rest → Bild B
            for i, s in enumerate(sents):
                s["img_index"] = a if i < half else b


# ── Stage 2: GENERIERUNG ──────────────────────────────────────────────────────

def stage2_generierung(
    themen: list[str],
    stufen: list[int],
    topics_data: dict,
    out_dir: Path,
    client: genai.Client,
    api_key: str,
    dry_run: bool = False,
) -> dict:
    """
    Stage 2: Gemini Batch — Artikel-Generierung (Themen × Stufen).

    1. Je Thema: Gemini Context Cache (stable Wikipedia-Prefix)
    2. Je Thema × Stufe: InlinedRequest mit variablem Suffix + source_passages-Wrapper
    3. Gemini Batch einreichen + pollen
    4. Post-Processing (synchron): JSON-Parse, Wortzahl-Guard, Box-Guard, is_hero
    """
    cp = _load_cp(out_dir, 2)
    if cp:
        return cp.get("articles", {})

    if not SYSTEM_PROMPT_PATH.exists():
        log.error("System-Prompt fehlt: %s", SYSTEM_PROMPT_PATH)
        return {}
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    thinking_cfg = _make_thinking_config(GEN_MODEL, budget_for_2_5=8192)
    articles_dir = out_dir / "articles"
    articles_dir.mkdir(exist_ok=True)

    if dry_run:
        n = sum(1 for t in themen if t in topics_data)
        total = n * len(stufen)
        print(f"\n=== DRY-RUN Stage 2 ===")
        print(f"Artikel-Batch: {total} Requests ({n} Themen × {len(stufen)} Stufen)")
        print(f"  Gemini Context Cache: 1 Cache je Thema (stable Wikipedia-Prefix)")
        print(f"  Variable Suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL + source_passages-Wrapper")
        print(f"  Post-Processing: Wortzahl-Guard + Box-Guard (synchron)")
        return {}

    # ── Step 1: Context-Caches je Thema ─────────────────────────────────────
    log.info("\n=== Stage 2 / Step 1: Context-Caches (%d Themen) ===", len(themen))
    caches: dict[str, str | None] = {}

    for thema in themen:
        data = topics_data.get(thema)
        if not data:
            log.warning("  '%s' fehlt in topics_data — kein Cache", thema)
            caches[thema] = None
            continue
        slug = thema.lower().replace(" ", "_").replace("/", "_")
        dummy_job = _stage2_job(thema, data, slug, stufe=1)
        stable, _ = _split_grounded_user_message(
            dummy_job,
            data["primary_text"],
            data.get("companion_texts", {}),
            data.get("valid_companions", []),
            data.get("images", []),
        )
        caches[thema] = try_create_gemini_cache(client, GEN_MODEL, system_prompt, stable,
                                                   ttl="3600s")

    # ── Step 2: InlinedRequests aufbauen ────────────────────────────────────
    log.info("\n=== Stage 2 / Step 2: Requests aufbauen ===")
    gen_reqs:  list[types.InlinedRequest] = []
    req_meta:  dict[str, dict]            = {}  # article_id → Metadaten für Post-Processing

    # Bereits gespeicherte Artikel vormerken → Batch überspringt sie
    articles: dict[str, str] = {}
    for _t in themen:
        _slug = _t.lower().replace(" ", "_").replace("/", "_")
        for _s in stufen:
            _aid = f"{_slug}_l{_s}"
            _op  = articles_dir / f"{_aid}.json"
            if _op.exists():
                articles[_aid] = str(_op)
                log.info("  %s: bereits vorhanden — wird nicht neu gebatcht", _aid)

    for thema in themen:
        data = topics_data.get(thema)
        if not data:
            continue
        slug       = thema.lower().replace(" ", "_").replace("/", "_")
        images_all = data.get("images", [])
        appeal     = data.get("appeal", "medium")
        # cached_content in InlinedRequest ist inkompatibel mit Gemini Batch API
        # → immer Fallback (volles System-Prompt + volles Message im Request)
        cache_name = None

        age_floor = int(data.get("age_floor") or 1)

        for stufe in stufen:
            article_id    = f"{slug}_l{stufe}"
            if article_id in articles:
                continue  # bereits gespeichert — kein neuer Batch-Request
            if stufe < age_floor:
                log.info("  age_floor-Gate: '%s' S%d < floor S%d — übersprungen",
                         thema, stufe, age_floor)
                continue
            wmin, wmax, _ = wortziel_for(thema, stufe)
            images_stufe  = select_images_for_stufe(images_all, stufe, appeal)
            job           = _stage2_job(thema, data, slug, stufe)

            if cache_name:
                variable = _gen2_variable_suffix(job, wmax)
                contents = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=variable)],
                )
                cfg = types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=1.0,
                    thinking_config=thinking_cfg,
                    max_output_tokens=32768,
                )
            else:
                stable, _ = _split_grounded_user_message(
                    job, data["primary_text"],
                    data.get("companion_texts", {}),
                    data.get("valid_companions", []),
                    images_all,
                )
                full_msg = stable + "\n" + _gen2_variable_suffix(job, wmax)
                contents = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=full_msg)],
                )
                cfg = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=1.0,
                    thinking_config=thinking_cfg,
                    max_output_tokens=32768,
                )

            req_meta[article_id] = {
                "thema":        thema,
                "stufe":        stufe,
                "job":          job,
                "images_stufe": images_stufe,
                "wmin":         wmin,
                "wmax":         wmax,
            }
            gen_reqs.append(types.InlinedRequest(
                contents=contents,
                config=cfg,
                metadata={"key": article_id},
            ))
            log.info("  %s: S%d | %d Bilder | Wmax=%d | Cache=%s",
                     article_id, stufe, len(images_stufe), wmax,
                     "JA" if cache_name else "NEIN (fallback)")

    if not gen_reqs:
        log.error("Stage 2: keine Requests — abgebrochen")
        return {}

    # ── Step 3: Batch einreichen + pollen ───────────────────────────────────
    log.info("\n=== Stage 2 / Step 3: Generierungs-Batch (%d Requests) ===", len(gen_reqs))
    gen_batch = client.batches.create(model=GEN_MODEL, src=gen_reqs)
    log.info("Batch eingereicht: %s", gen_batch.name)
    gen_batch = poll_gemini_batch(client, gen_batch.name)
    state = _state_str(gen_batch)
    if state not in SUCCESS_STATES:
        log.error("Generierungs-Batch fehlgeschlagen: %s — Artikel fehlen", state)
        return {}

    # ── Step 4: Post-Processing (synchron, lokal) ────────────────────────────
    log.info("\n=== Stage 2 / Step 4: Post-Processing ===")
    # articles wurde in Step 2 vorinitialisiert (bereits gespeicherte Artikel)

    for resp in _get_inlined_responses(gen_batch):
        meta_resp  = getattr(resp, "metadata", {}) or {}
        article_id = meta_resp.get("key", "")
        if not article_id or article_id not in req_meta:
            log.warning("  Unbekannte Response-Key: '%s'", article_id)
            continue

        m         = req_meta[article_id]
        thema     = m["thema"]
        stufe     = m["stufe"]
        job       = m["job"]
        imgs_s    = m["images_stufe"]
        wmin      = m["wmin"]
        wmax      = m["wmax"]
        data      = topics_data[thema]

        raw   = _extract_text(getattr(resp, "response", None))
        usage = _extract_usage(getattr(resp, "response", None))
        if usage:
            cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe=f"S{stufe}",
                               schritt="article_gen", modell=GEN_MODEL, **usage)

        if not raw:
            log.error("  [%s] Leere Batch-Antwort", article_id)
            continue

        # JSON-Parse (Wrapper oder plain)
        try:
            article, source_passages = _parse_gen2_response(raw)
        except Exception as e:
            log.error("  [%s] JSON-Parse: %s", article_id, e)
            err_dir = out_dir / "_errors"
            err_dir.mkdir(exist_ok=True)
            (err_dir / f"{article_id}_raw.txt").write_text(raw or "", encoding="utf-8")
            continue

        # Metadaten
        article.setdefault("meta", {})
        article["meta"]["id"]                   = article_id
        article["meta"]["title"]                = thema
        article["meta"]["generated_at"]         = datetime.now(timezone.utc).isoformat()
        article["meta"]["grounding_companions"] = data.get("valid_companions", [])
        _prompt_version = SYSTEM_PROMPT_PATH.stem.split("_v")[-1].split("_")[0]
        article["meta"]["generation_method"]    = f"{GEN_MODEL}/batch/v{_prompt_version}"
        article["meta"]["generation_temperature"] = 1.0
        article["meta"]["generation_thinking"]    = "MEDIUM"

        # Wortzahl-Guard
        word_count = count_article_words(article)
        cap        = round(wmax * 1.05)
        log.info("  [%s] Wortzahl: %d (Ziel %d–%d, Cap %d)", article_id, word_count, wmin, wmax, cap)

        trims = 0
        orig_box_count = sum(len(s.get("boxes", [])) for s in article.get("sections", []))
        while word_count > cap and trims < 2:
            trims += 1
            log.warning("  [%s] Zu lang (%d > %d) — Trim %d/2", article_id, word_count, cap, trims)
            try:
                trimmed, trimmed_wc = _trim_article_to_cap(article, wmax, GEN_MODEL, thinking_cfg)
                u = getattr(gemini_client, "_last_usage", {})
                if u:
                    cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe=f"S{stufe}",
                                       schritt="trim", modell=GEN_MODEL, **u)
                trimmed_boxes = sum(len(s.get("boxes", [])) for s in trimmed.get("sections", []))
                if trimmed_boxes == 0 and orig_box_count > 0:
                    log.error("  [%s] Trim %d hat ALLE Boxen entfernt — Trim-Ergebnis verworfen,"
                              " review_flag", article_id, trims)
                    article["meta"]["review_flag"] = True
                    article["meta"]["review_reason"] = (
                        (article["meta"].get("review_reason", "") + "; Trim entfernte alle Boxen")
                        .lstrip("; ")
                    )
                    break
                article, word_count = trimmed, trimmed_wc
                log.info("  [%s] Nach Trim %d: %d Wörter (%d Boxen)", article_id, trims,
                         word_count, trimmed_boxes)
            except Exception as e:
                log.error("  [%s] Trim fehlgeschlagen: %s", article_id, e)
                break
        if trims:
            article["meta"]["trim_passes"] = trims
        # Fix 2: review_flag wenn Artikel nach Trim immer noch über Cap liegt
        if word_count > cap:
            log.warning("  [%s] Über Cap (%d > %d) nach Trim — review_flag", article_id,
                        word_count, cap)
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                (article["meta"].get("review_reason", "") + f"; Wortzahl {word_count} > Cap {cap}")
                .lstrip("; ")
            )

        if word_count < wmin:
            log.warning("  [%s] Zu kurz: %d < %d → review_flag", article_id, word_count, wmin)
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = f"Wortzahl {word_count} < {wmin}"
        article["meta"]["word_count"] = word_count

        # Box-Guard
        box_issue = _box_lint(article)
        if box_issue:
            log.warning("  [%s] %s — Box-Repair", article_id, box_issue)
            try:
                repaired = _box_repair_pass(article, GEN_MODEL, thinking_cfg)
                u = getattr(gemini_client, "_last_usage", {})
                if u:
                    cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe=f"S{stufe}",
                                       schritt="box_repair", modell=GEN_MODEL, **u)
                if _box_lint(repaired) is None:
                    article = repaired
                    article["meta"]["box_repaired"] = True
                    log.info("  [%s] Box-Repair OK", article_id)
                else:
                    log.warning("  [%s] Box-Repair ohne Verbesserung → review_flag", article_id)
                    article["meta"]["review_flag"]   = True
                    article["meta"]["review_reason"] = (
                        article["meta"].get("review_reason", "") + f"; {box_issue}").lstrip("; ")
            except Exception as e:
                log.error("  [%s] Box-Repair fehlgeschlagen: %s", article_id, e)
                article["meta"]["review_flag"] = True

        # Validierung
        try:
            val_errors = validate_article(article, job)
        except Exception as _ve:
            log.error("  [%s] validate_article Exception: %s — review_flag", article_id, _ve)
            val_errors = [f"validate_article exception: {_ve}"]
        if val_errors:
            log.warning("  [%s] Validierung: %s", article_id, "; ".join(val_errors[:3]))
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "") + "; " + "; ".join(val_errors[:3])
            ).lstrip("; ")

        # is_hero + tiers setzen (Primary-Artikel-Hero bevorzugt)
        _set_is_hero(article, imgs_s, thema, data.get("resolved_title", thema))

        # Bildwechsel pro Section begrenzen (S1=1 Bild, S2/3 bis 2 ab >=4 Sätzen)
        _limit_images_per_section(article, imgs_s)

        # source_passages einbetten
        if source_passages:
            article["source_passages"] = source_passages
            log.info("  [%s] source_passages: %d Einträge", article_id, len(source_passages))

        # Artikel speichern
        out_path = articles_dir / f"{article_id}.json"
        out_path.write_text(
            json.dumps(article, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        articles[article_id] = str(out_path)
        n_sects = len(article.get("sections", []))
        n_sents = sum(len(s.get("sentences", [])) for s in article.get("sections", []))
        n_boxes = sum(len(s.get("boxes", [])) for s in article.get("sections", []))
        n_quiz  = len(article.get("quiz", []))
        log.info(
            "  [%s] OK: %d Wörter | %d Sects %d Sätze %d Boxen %d Quiz | "
            "%d Bilder | sp=%s",
            article_id, word_count, n_sects, n_sents, n_boxes, n_quiz,
            len(article.get("images", [])), bool(source_passages),
        )

    _save_cp(out_dir, 2, {"status": "done", "articles": articles})
    return articles


# ── Stage 3: LEKTORAT ────────────────────────────────────────────────────────

def stage3_lektorat(
    themen: list[str],
    stufen: list[int],
    articles: dict,
    topics_data: dict,
    out_dir: Path,
    anthropic_key: str,
    dry_run: bool = False,
) -> dict:
    """
    Stage 3: Anthropic Message Batches — Faktenlektorat aller Artikel.

    Architektur:
    - EIN Batch, alle Artikel (themenweise geordnet für Cache-Optimierung)
    - System-Prompt + Quellblock mit cache_control: ephemeral
    - Sonnet prüft alle Fakten gegen Wikipedia-Volltext
    - Ergebnis: pruefbericht in lektorat_{article_id}.json

    batch_id wird sofort in pending_batches.json gesichert (Pflicht).
    """
    import anthropic

    cp = _load_cp(out_dir, 3)
    if cp:
        return cp.get("lektorat_results", {})

    if dry_run:
        total = len(articles)
        print(f"\n=== DRY-RUN Stage 3 ===")
        print(f"Lektorat-Batch: {total} Requests (Anthropic Message Batches)")
        print(f"  Modell: {LEKTORAT_MODEL} | cache_control: ephemeral auf System + Quellblock")
        print(f"  Reihenfolge: themenweise (L1/L2/L3 benachbart) für Cache-Hit-Chance")
        print(f"  Output: out_dir/lektorat/lektorat_{{article_id}}.json")
        return {}

    anth_client = anthropic.Anthropic(api_key=anthropic_key)
    lektorat_dir = out_dir / "lektorat"
    lektorat_dir.mkdir(exist_ok=True)
    pending_path = out_dir / "pending_batches.json"

    # ── Step 1: Requests aufbauen (themenweise geordnet) ─────────────────────
    log.info("\n=== Stage 3 / Step 1: Lektorat-Requests aufbauen ===")

    # Geordnete Liste: [(article_id, sources_prefix, article_task, art_dict, thema)]
    ordered_requests: list[tuple[str, str, str, dict, str]] = []

    for thema in themen:
        data = topics_data.get(thema)
        if not data:
            log.warning("  '%s' fehlt in topics_data — Lektorat übersprungen", thema)
            continue

        slug          = thema.lower().replace(" ", "_").replace("/", "_")
        primary_text  = data.get("primary_text", "")
        companions    = data.get("valid_companions", [])
        comp_texts    = data.get("companion_texts", {})

        sources_block = build_grounded_sources_block(
            thema, primary_text, companions, comp_texts
        )

        for stufe in stufen:
            article_id   = f"{slug}_l{stufe}"
            art_path_str = articles.get(article_id)
            if not art_path_str:
                log.warning("  [%s] kein Artikel-Pfad — übersprungen", article_id)
                continue

            art_path = Path(art_path_str)
            if not art_path.exists():
                log.warning("  [%s] Datei fehlt: %s", article_id, art_path)
                continue

            lekt_out = lektorat_dir / f"lektorat_{article_id}.json"
            if lekt_out.exists():
                log.info("  [%s] bereits lektoriert — übersprungen", article_id)
                continue

            try:
                art = json.loads(art_path.read_text(encoding="utf-8"))
            except Exception as exc:
                log.error("  [%s] Laden fehlgeschlagen: %s", article_id, exc)
                continue

            sources_prefix, article_task = build_lektorat_parts(art, sources_block)
            ordered_requests.append((article_id, sources_prefix, article_task, art, thema))
            log.info("  [%s] OK", article_id)

    if not ordered_requests:
        log.info("Stage 3: keine offenen Artikel — Stage übersprungen")
        _save_cp(out_dir, 3, {"status": "done", "lektorat_results": {}})
        return {}

    # ── Step 2: Anthropic-Batch aufbauen ─────────────────────────────────────
    log.info("\n=== Stage 3 / Step 2: Batch aufbauen (%d Requests) ===",
             len(ordered_requests))

    batch_reqs = []
    norm_to_aid: dict[str, str] = {}   # normalized custom_id → original aid
    for aid, sources_prefix, article_task, _art, _thema in ordered_requests:
        nid = _normalize_custom_id(aid)
        norm_to_aid[nid] = aid
        batch_reqs.append({
            "custom_id": nid,
            "params": {
                "model":      LEKTORAT_MODEL,
                "max_tokens": 16000,
                "system": [
                    {"type": "text", "text": LEKTORAT_SYSTEM,
                     "cache_control": {"type": "ephemeral"}},
                ],
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": sources_prefix,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": article_task},
                ]}],
            },
        })

    # ── Step 3: Batch einreichen + batch_id persistieren ─────────────────────
    log.info("\n=== Stage 3 / Step 3: Batch einreichen ===")
    batch    = anth_client.messages.batches.create(requests=batch_reqs)
    batch_id = batch.id
    log.info("  Batch: %s (%d Requests)", batch_id, len(batch_reqs))

    # batch_id sofort persistieren (vor dem Pollen — Pflicht)
    pending: dict = {}
    if pending_path.exists():
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    pending[f"stage3_{_RUN_ID}"] = {
        "batch_id":   batch_id,
        "stage":      3,
        "run_id":     _RUN_ID,
        "n_requests": len(batch_reqs),
        "submitted":  datetime.now(timezone.utc).isoformat(),
    }
    pending_path.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("  batch_id persistiert → %s", pending_path.name)

    # ── Step 4: Pollen ────────────────────────────────────────────────────────
    log.info("\n=== Stage 3 / Step 4: Pollen ===")
    batch = poll_anthropic_batch(anth_client, batch_id)

    # ── Step 5: Ergebnisse verarbeiten ───────────────────────────────────────
    log.info("\n=== Stage 3 / Step 5: Ergebnisse verarbeiten ===")

    # Art-Dict + Thema schnell nachschlägbar machen
    art_by_id:   dict[str, dict] = {r[0]: r[3] for r in ordered_requests}
    thema_by_id: dict[str, str]  = {r[0]: r[4] for r in ordered_requests}

    lektorat_results: dict[str, str] = {}
    total_in = total_out = total_cache_create = total_cache_read = 0

    for result in anth_client.messages.batches.results(batch_id):
        rid   = norm_to_aid.get(result.custom_id, result.custom_id)
        thema = thema_by_id.get(rid, rid)
        stufe_num = rid.split("_l")[-1] if "_l" in rid else "?"

        if result.result.type != "succeeded":
            log.warning("  [%s] Batch-Fehler: %s — Original behalten", rid,
                        result.result.type)
            continue

        msg = result.result.message
        raw = msg.content[0].text
        u   = msg.usage
        cache_create = getattr(u, "cache_creation_input_tokens", 0) or 0
        cache_read   = getattr(u, "cache_read_input_tokens", 0) or 0
        total_in          += u.input_tokens
        total_out         += u.output_tokens
        total_cache_create += cache_create
        total_cache_read   += cache_read

        log.info(
            "  [%s] in=%d create=%d read=%d out=%d",
            rid, u.input_tokens, cache_create, cache_read, u.output_tokens,
        )

        cost_tracker.track(
            run_id=_RUN_ID, thema=thema, stufe=f"S{stufe_num}",
            schritt="lektorat", modell=LEKTORAT_MODEL,
            input_tok=u.input_tokens,
            output_tok=u.output_tokens,
            cached_tok=cache_read,
        )

        # Lektorat-Ergebnis parsen (V2: SILENT/KORRIGIERT/PRÜFEN)
        try:
            lektorat_result = parse_lektorat_v2(raw)
        except Exception as exc:
            log.warning("  [%s] JSON-Parse fehlgeschlagen: %s — pruefbericht leer", rid, exc)
            lektorat_result = {"corrections": [], "pruefen": []}

        art = art_by_id.get(rid)
        if art is None:
            log.warning("  [%s] Artikel nicht im Speicher", rid)
            continue

        # Korrekturen einbauen + Prüfbericht schreiben
        annotate_article_lektorat_v2(
            art, lektorat_result, thema=thema, stufe=f"S{stufe_num}"
        )

        pb         = art.get("pruefbericht", {})
        n_silent   = pb.get("n_silent", 0)
        n_korr     = pb.get("n_korrigiert", 0)
        n_pr       = pb.get("n_pruefen", 0)
        n_total    = len(lektorat_result.get("corrections", [])) + len(lektorat_result.get("pruefen", []))
        log.info(
            "  [%s] %d Einträge | silent=%d korrigiert=%d prüfen=%d%s",
            rid, n_total, n_silent, n_korr, n_pr,
            " ⚠ review_flag" if n_pr > 0 else "",
        )

        # Als lektorat_{id}.json speichern
        lekt_out = lektorat_dir / f"lektorat_{rid}.json"
        lekt_out.write_text(
            json.dumps(art, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        lektorat_results[rid] = str(lekt_out)

    log.info(
        "\n=== Stage 3 Gesamt-Tokens: in=%d out=%d cache_create=%d cache_read=%d ===",
        total_in, total_out, total_cache_create, total_cache_read,
    )

    _save_cp(out_dir, 3, {"status": "done", "lektorat_results": lektorat_results})
    return lektorat_results


# ── Stage 4: TTS (Stub) ───────────────────────────────────────────────────────

def stage4_tts(
    themen: list[str],
    stufen: list[int],
    out_dir: Path,
    dry_run: bool = False,
) -> None:
    """
    Stage 4: TTS via ThreadPool.

    TODO: tts_produce.py (nächster Baustein) muss existieren.
    Wichtig: tts_audio_sec je Datei an cost_tracker melden.
    """
    if dry_run:
        print(f"\n=== DRY-RUN Stage 4 ===")
        print(f"TTS: {len(themen) * len(stufen)} Slots (ThreadPool)")
        print(f"  Modell: gemini-3.1-flash-tts-preview")
        print(f"  cost_tracker.track(schritt='tts', tts_audio_sec=<echte Laenge>)")
        print("  -> WARTEN auf tts_produce.py")
        return
    log.warning("Stage 4 (TTS): TODO — warte auf tts_produce.py")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Wissensfreund Batch-Orchestrator")
    parser.add_argument(
        "--themen", nargs="+", metavar="THEMA",
        help="Themenliste (z.B. 'Elefant' 'Hund')",
    )
    parser.add_argument(
        "--catalog-rank", type=int, metavar="N",
        help="Top-N nach production_rank aus catalog_full.json",
    )
    parser.add_argument(
        "--stufen", nargs="+", type=int, choices=[1, 2, 3], default=[1, 2, 3],
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run-ID für cost_tracker (default: Zeitstempel)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Ausgabeverzeichnis (default: articles/batch_output)",
    )
    parser.add_argument(
        "--stage", type=int, default=0, metavar="N",
        help="Nur Stage N ausführen (0 = alle)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Zeigt geplante Requests ohne API-Calls",
    )
    args = parser.parse_args()

    global _RUN_ID
    _RUN_ID = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    out_dir = (
        Path(args.output_dir).resolve() if args.output_dir
        else ROOT / "articles" / "batch_output"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_errors").mkdir(exist_ok=True)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        log.warning("ANTHROPIC_API_KEY fehlt — Opus-Recheck + Lektorat übersprungen")

    # Themen bestimmen
    if args.catalog_rank:
        jobs      = _load_catalog_rank_jobs(args.catalog_rank, args.stufen)
        themen_raw = list(dict.fromkeys(j["thema"] for j in jobs))
    elif args.themen:
        try:
            jobs = _build_catalog_jobs(args.themen, args.stufen)
            themen_raw = list(dict.fromkeys(j["thema"] for j in jobs)) if jobs else args.themen
        except FileNotFoundError:
            themen_raw = args.themen
    else:
        parser.error("--themen oder --catalog-rank erforderlich")
        return

    stufen   = args.stufen
    run_all  = args.stage == 0

    log.info("Run-ID: %s | Themen: %d | Stufen: %s | Stage: %s | dry-run: %s",
             _RUN_ID, len(themen_raw), stufen,
             args.stage if args.stage else "alle", args.dry_run)

    client  = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = (
        "WissensfreundPipeline/1.0 (az@expansionssupport.de; Kinderwissens-App)"
    )

    topics_data: dict = {}
    articles:    dict = {}

    # ── Stage 1 ───────────────────────────────────────────────────────────────
    if run_all or args.stage == 1:
        log.info("\n" + "=" * 60)
        log.info("STAGE 1: SOURCING (%d Themen)", len(themen_raw))
        log.info("=" * 60)
        topics_data = stage1_sourcing(
            themen_raw, out_dir, client, session, api_key, anthropic_key,
            dry_run=args.dry_run,
        )
        if not args.dry_run and topics_data:
            print("\n=== Stage 1 Ergebnis ===")
            for thema, data in topics_data.items():
                imgs = data.get("images", [])
                s1 = sum(1 for i in imgs if i.get("ab_stufe") == 1)
                s2 = sum(1 for i in imgs if i.get("ab_stufe") == 2)
                s3 = sum(1 for i in imgs if i.get("ab_stufe") == 3)
                comp_str = ", ".join(data.get("valid_companions", []))
                print(f"  {thema}:")
                print(f"    Companions: {comp_str or '(keine)'}")
                print(f"    Bilder: {len(imgs)} | S1={s1} S2={s2} S3={s3}")
                sens_str = "JA" if data.get("sensibel") else "nein"
                print(f"    sensibel={sens_str} | appeal={data.get('appeal')}")
            print()
        if args.stage == 1:
            return
    else:
        cp1 = _load_cp(out_dir, 1)
        if cp1 is None:
            log.error("Stage 1 Checkpoint fehlt — bitte zuerst Stage 1 ausführen")
            sys.exit(1)
        topics_data = cp1["topics"]

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    if run_all or args.stage == 2:
        log.info("\n" + "=" * 60)
        log.info("STAGE 2: GENERIERUNG (%d Themen × %d Stufen)",
                 len(themen_raw), len(stufen))
        log.info("=" * 60)
        articles = stage2_generierung(
            themen_raw, stufen, topics_data, out_dir, client, api_key,
            dry_run=args.dry_run,
        )
        if args.stage == 2:
            return
    else:
        cp2      = _load_cp(out_dir, 2)
        articles = (cp2 or {}).get("articles", {})

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    if (run_all or args.stage == 3) and anthropic_key:
        log.info("\n" + "=" * 60)
        log.info("STAGE 3: LEKTORAT")
        log.info("=" * 60)
        stage3_lektorat(
            themen_raw, stufen, articles, topics_data, out_dir, anthropic_key,
            dry_run=args.dry_run,
        )
        if args.stage == 3:
            return

    # ── Stage 4 ───────────────────────────────────────────────────────────────
    if run_all or args.stage == 4:
        log.info("\n" + "=" * 60)
        log.info("STAGE 4: TTS")
        log.info("=" * 60)
        stage4_tts(themen_raw, stufen, out_dir, dry_run=args.dry_run)

    log.info("\n=== Batch-Run abgeschlossen (Run-ID: %s) ===", _RUN_ID)


if __name__ == "__main__":
    main()
