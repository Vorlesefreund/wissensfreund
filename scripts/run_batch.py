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
    VISION_SYSTEM_PROMPT,
    VISION_PROMPT_TEMPLATE,
    OPUS_RECHECK_SYSTEM,
    OPUS_RECHECK_PROMPT,
)
from lektorat_common import (  # noqa: E402
    LEKTORAT_SYSTEM,
    LEKTORAT_MODEL,
    COMPANION_CHAR_CAP,
    build_lektorat_parts,
    parse_lektorat_json,
    annotate_article_lektorat,
    build_grounded_sources_block,
)
import gemini_client  # noqa: E402

# ── Konstanten ────────────────────────────────────────────────────────────────

VISION_MODEL         = "gemini-2.5-flash"
VISION_CHUNK_SIZE    = 500   # Max InlinedRequests pro Vision-Batch-Job
POLL_SECS_GEMINI     = 30
POLL_SECS_ANTHROPIC  = 30
GEMINI_TIMEOUT_H     = 48.0
ANTHROPIC_TIMEOUT_H  = 24.0

DONE_STATES    = {
    "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED",
    "JOB_STATE_PARTIALLY_SUCCEEDED", "JOB_STATE_EXPIRED",
}
SUCCESS_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}

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
        print(f"Vision-Batch: ~{len(wp_data) * MAX_VISION_CHECKS} Requests (max {MAX_VISION_CHECKS}/Thema)")
        print(f"Opus-Recheck: nur confidence=niedrig Bilder bei {n_sens} sensiblen Themen")
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
        valid_companions, _ = validate_and_resolve_companions(
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
    log.info("\n=== Stage 1 / Step 4: Image Download ===")
    vision_reqs:       list[types.InlinedRequest] = []
    img_meta_by_key:   dict[str, dict] = {}
    topic_img_keys:    dict[str, list[str]] = defaultdict(list)

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

        # Herunterladen + Vision-Request aufbauen (3s pre-download, Wikimedia-konform)
        for i, img in enumerate(to_check):
            if i > 0:
                time.sleep(3.0)
            img_bytes = download_image(session, img["thumb_url"])
            if img_bytes is None:
                log.debug("    Download fehlgeschlagen: %s", img["filename"][:40])
                continue

            prompt  = VISION_PROMPT_TEMPLATE.format(thema=thema)
            # Schlüssel: thema + filename (sanitiert)
            safe_t  = re.sub(r"[^\w]", "_", thema)[:30]
            safe_fn = re.sub(r"[^\w.-]", "_", img["filename"])[:50]
            key     = f"{safe_t}___{safe_fn}"

            vision_reqs.append(types.InlinedRequest(
                contents=types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ],
                ),
                config=types.GenerateContentConfig(
                    system_instruction=VISION_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
                metadata={"key": key, "thema": thema},
            ))
            img_meta_by_key[key] = {**img, "thema": thema}
            topic_img_keys[thema].append(key)

        data["_img_candidates"] = unique

    log.info("Vision-Batch: %d Requests gesamt", len(vision_reqs))

    # ── Step 5: Vision-Batch(es) (Gemini) ─────────────────────────────────────
    log.info("\n=== Stage 1 / Step 5: Vision-Batch ===")
    all_vision_results: dict[str, dict] = {}  # key → {ab_stufe, confidence, ...}

    for chunk_start in range(0, max(len(vision_reqs), 1), VISION_CHUNK_SIZE):
        chunk    = vision_reqs[chunk_start : chunk_start + VISION_CHUNK_SIZE]
        chunk_nr = chunk_start // VISION_CHUNK_SIZE + 1
        if not chunk:
            break
        log.info("  Vision-Chunk %d: %d Requests", chunk_nr, len(chunk))

        try:
            batch_v = client.batches.create(model=VISION_MODEL, src=chunk)
            log.info("  Vision-Batch %d eingereicht: %s", chunk_nr, batch_v.name)
        except Exception as e:
            log.error("  Vision-Batch %d Einreichung fehlgeschlagen: %s", chunk_nr, e)
            continue

        batch_v_done = poll_gemini_batch(client, batch_v.name)
        if _state_str(batch_v_done) not in SUCCESS_STATES:
            log.error("  Vision-Batch %d fehlgeschlagen: %s", chunk_nr, _state_str(batch_v_done))
            continue

        for resp in _get_inlined_responses(batch_v_done):
            key       = (resp.metadata or {}).get("key", "")
            thema_key = (resp.metadata or {}).get("thema", "")
            if not key:
                continue
            if resp.error:
                log.warning("  Vision '%s': %s", key[:40], resp.error)
                continue
            text = _strip_md(_extract_text(resp.response))
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                log.warning("  Vision JSON-Fehler: %r", text[:60])
                continue
            u = _extract_usage(resp.response)
            if u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema_key, stufe="S0",
                                   schritt="vision", modell=VISION_MODEL,
                                   input_tok=u["input_tok"], output_tok=u["output_tok"])
            all_vision_results[key] = result

    # ── Step 6: Conservative Upgrade + Bildpool aufbauen ──────────────────────
    log.info("\n=== Stage 1 / Step 6: Vision-Ergebnisse verarbeiten ===")
    opus_kandidaten: list[dict] = []

    for thema, data in wp_data.items():
        accepted: list[dict] = []
        n_rejected = 0

        for key in topic_img_keys.get(thema, []):
            img_meta = img_meta_by_key.get(key, {})
            result   = all_vision_results.get(key)
            if result is None:
                n_rejected += 1
                continue

            ab_stufe    = result.get("ab_stufe", 0)
            confidence  = result.get("confidence", "hoch")
            beschreibung = result.get("beschreibung", "")
            relevanz    = result.get("relevanz", 0)
            hero        = result.get("hero_candidate", False)

            # Conservative Upgrade
            if confidence == "niedrig" and ab_stufe == 1:
                ab_stufe = 2
                log.info("    confidence=niedrig: '%s' → ab_stufe 1→2",
                         img_meta.get("filename", "")[:40])

            if ab_stufe == 0 or relevanz < 4:
                n_rejected += 1
                continue

            entry = {
                **img_meta,
                "ab_stufe":       ab_stufe,
                "confidence":     confidence,
                "relevanz":       relevanz,
                "hero_candidate": hero,
                "beschreibung":   beschreibung,
            }
            accepted.append(entry)

            if data["sensibel"] and confidence == "niedrig" and anthropic_key:
                opus_kandidaten.append({"thema": thema, "key": key, "img": entry})

        accepted.sort(key=lambda x: (-x["relevanz"], -int(x.get("hero_candidate", False))))
        data["images"] = accepted
        log.info("  '%s': %d akzeptiert, %d verworfen", thema, len(accepted), n_rejected)

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
                custom_id = cand["key"]
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


# ── Stage 2: GENERIERUNG (Gerüst) ─────────────────────────────────────────────

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

    TODO: Implementierung ausstehend.

    Schritte:
    1. system_prompt = SYSTEM_PROMPT_PATH.read_text()
    2. Für jedes Thema:
       a. stable_prefix, _ = _split_grounded_user_message(
              job_s1, primary_text, companion_texts, valid_companions,
              images)  # Bild-Liste noch NICHT stufen-gefiltert
       b. cache_name = try_create_gemini_cache(client, GEN_MODEL,
              system_prompt, stable_prefix)
    3. Für jedes Thema × Stufe:
       a. images_stufe = select_images_for_stufe(images, stufe, appeal)
       b. job = {thema, age_level=stufe, resolved_appeal=appeal, ...}
       c. variable = _variable_suffix(job, wortziel_for(thema, stufe)[1])
       d. InlinedRequest(contents=variable, config=...(cached_content=cache_name),
              metadata={"key": article_id})
       e. Fallback ohne Cache: contents = build_grounded_user_message(...)
    4. client.batches.create(model=GEN_MODEL, src=requests)
    5. poll_gemini_batch()
    6. Für jede Batch-Antwort (synchron, lokal):
       a. parse_article_json(raw)
       b. validate_article()
       c. Wortzahl-Check → _trim_article_to_cap() falls > cap
       d. _box_lint() → _box_repair_pass() falls Clusterung
       e. Metadaten setzen, Artikel speichern als {article_id}.json
    7. _save_cp(out_dir, 2, {"status": "done", "articles": {aid: path}})
    """
    cp = _load_cp(out_dir, 2)
    if cp:
        return cp.get("articles", {})

    if dry_run:
        total = sum(len(stufen) for _ in themen)
        print(f"\n=== DRY-RUN Stage 2 ===")
        print(f"Artikel-Batch: {total} Requests ({len(themen)} Themen × {len(stufen)} Stufen)")
        print(f"  Gemini Context Cache: 1 Cache je Thema (stable prefix)")
        print(f"  Variable Suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL")
        print(f"  Post-Processing: Wortzahl-Guard + Box-Guard (synchron)")
        return {}

    log.warning("Stage 2 (Generierung): TODO — noch nicht implementiert")
    return {}


# ── Stage 3: LEKTORAT (Gerüst) ────────────────────────────────────────────────

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
    Stage 3: Anthropic Message Batches — Lektorat (2 Pässe).

    TODO: Implementierung ausstehend.

    Pass 1 (schlank):
      - Wenn Artikel source_passages[] enthält (von Flash extrahiert):
        sources_block aus source_passages statt Companion-Volltexten
      - Sonst: volles build_grounded_sources_block() als Fallback
      - System-Prompt mit cache_control: ephemeral
      - Sonnet gibt zurück: Verdikt-Liste + passagen_ausreichend: bool
    Pass 2 (Nachschlag-Batch):
      - Nur Artikel mit passagen_ausreichend=false
      - Volle Companion-Volltexte
      - Separater Anthropic Batch
    Annotierung:
      - annotate_article_lektorat(article, verdicts, primary_text)
      - Artikel neu speichern
    """
    cp = _load_cp(out_dir, 3)
    if cp:
        return cp.get("lektorat_results", {})

    if dry_run:
        total = len(articles)
        print(f"\n=== DRY-RUN Stage 3 ===")
        print(f"Lektorat Pass 1: {total} Requests (System-Prompt gecached)")
        print(f"  Pass 2: Nachschlag-Batch für passagen_ausreichend=false Artikel")
        return {}

    log.warning("Stage 3 (Lektorat): TODO — noch nicht implementiert")
    return {}


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
