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
import stage_models  # noqa: E402
from generate_articles import (  # noqa: E402
    fetch_wikipedia_text,
    resolve_lemma,
    parse_article_json,
    validate_article,
    USER_AGENT,
)
import generate_grounded  # noqa: E402  (Modul-Objekt für Live-Usage-Globals _last_trim_usage/_last_box_usage)
from generate_grounded import (  # noqa: E402
    select_companions_raw,
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
    fetch_lead_image,
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

VISION_MODEL         = stage_models.get_stage_config("vision")["model"]  # config-getrieben
VISION_CHUNK_SIZE    = 500   # ungenutzt seit Sync-Umbau (war: max InlinedRequests/Batch)
POLL_SECS_GEMINI     = 30
POLL_SECS_ANTHROPIC  = 30
# Stall-Timeout für den Gemini-Generierungs-Batch (unbeaufsichtigter Betrieb):
# nach GEMINI_BATCH_TIMEOUT_MIN Minuten wird der hängende Batch serverseitig
# gecancelt und der Lauf mit TimeoutError beendet. Env-überschreibbar.
GEMINI_BATCH_TIMEOUT_MIN = float(os.environ.get("GEMINI_BATCH_TIMEOUT_MIN", "30"))
ANTHROPIC_TIMEOUT_H  = 24.0   # Lektorat (Phase B, entkoppelt) — bewusst unverändert

# Circuit Breaker — Stage 1 Kompass
CB_THRESHOLD = 3          # aufeinanderfolgende API-Ausfälle bis zur Pause
CB_WAIT_MIN  = 15         # Wartezeit in Minuten

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


def _load_cp_raw(out_dir: Path, stage: int) -> dict | None:
    """Checkpoint-Daten bei status=='done' liefern — OHNE Skip-Log.
    Skip-Entscheidung + Logging trifft die Aufrufstelle (z.B. Stage-1-Resume,
    der companions_failed-Topics neu durchlaufen statt überspringen muss)."""
    p = _cp_path(out_dir, stage)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if data.get("status") == "done" else None


def _partial_path(out_dir: Path) -> Path:
    return out_dir / "stage1_partial.json"


def _save_partial(out_dir: Path, topics: dict) -> None:
    """Atomar (temp + os.replace) den bisherigen Stage-1-Stand wegschreiben."""
    p   = _partial_path(out_dir)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"topics": topics}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, p)


def _load_partial(out_dir: Path) -> dict:
    """Bereits verarbeitete Topics aus stage1_partial.json laden (oder {})."""
    p = _partial_path(out_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("topics", {})
    except (json.JSONDecodeError, OSError):
        return {}


# ── Run-Status (zentrale, append-only Statusdatei für unbeaufsichtigten Betrieb) ─
RUN_STATUS_PATH = ROOT / "run_status.jsonl"

def _run_status(thema: str, stufe, status: str, grund: str = "", detail: str = "") -> None:
    """Hängt EINE JSON-Zeile an run_status.jsonl an (append-only, abbruch-robust).

    status: "OK" | "FAILED". grund (nur bei FAILED, maschinenlesbare Kategorie):
    timeout | retry_exhausted_503 | degraded_output | empty_output | other.
    """
    rec = {
        "ts":     datetime.now(timezone.utc).isoformat(),
        "run_id": _RUN_ID,
        "thema":  thema,
        "stage":  "stage2",
        "stufe":  stufe,
        "status": status,
    }
    if status == "FAILED":
        rec["grund"]  = grund or "other"
        rec["detail"] = detail[:300]
    try:
        with open(RUN_STATUS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("run_status.jsonl nicht schreibbar (ignoriert): %s", e)


def _thema_stufe_from_aid(aid: str, req_meta: dict) -> tuple[str, object]:
    """article_id → (thema, stufe) via req_meta, mit Fallback aufs aid-Suffix."""
    m = req_meta.get(aid, {})
    if m:
        return m.get("thema", aid), m.get("stufe", "")
    # Fallback: '<slug>_l<n>'
    if "_l" in aid:
        base, _, lv = aid.rpartition("_l")
        return base, (int(lv) if lv.isdigit() else lv)
    return aid, ""


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
    timeout_min: float = GEMINI_BATCH_TIMEOUT_MIN,
):
    deadline = time.monotonic() + timeout_min * 60
    log.info("Polling Gemini-Batch %s ... (Timeout %.0f min)", batch_name[-30:], timeout_min)
    while True:
        job   = client.batches.get(name=batch_name)
        state = _state_str(job)
        log.info("  Batch %s → %s", batch_name[-30:], state)
        if state in DONE_STATES:
            return job
        if time.monotonic() > deadline:
            # Stall: hängenden Batch serverseitig canceln (keine weiterlaufenden Kosten),
            # dann terminieren. Cancel-Fehler dürfen den Abbruch NICHT verhindern.
            log.error("Gemini-Batch %s nach %.0f min nicht fertig — canceln + abbrechen",
                      batch_name[-30:], timeout_min)
            try:
                client.batches.cancel(name=batch_name)
                log.info("  Batch %s serverseitig gecancelt", batch_name[-30:])
            except Exception as _ce:
                log.warning("  Batch-Cancel fehlgeschlagen (ignoriert): %s", _ce)
            raise TimeoutError(
                f"Gemini-Batch {batch_name} nach {timeout_min}min nicht fertig (gecancelt)"
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

def _img_key(thema: str, filename: str) -> str:
    """Deterministischer Bild-Key (= Opus-custom_id-Basis), nur [a-zA-Z0-9_-], max 64 Zeichen."""
    safe_t  = re.sub(r"[^a-zA-Z0-9_-]", "_", thema)[:20]
    safe_fn = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)[:41]
    return f"{safe_t}__{safe_fn}"


def _opus_recheck(anthropic_key: str, kandidaten: list[dict], topics_data: dict,
                  model: str = "claude-opus-4-8") -> None:
    """Cross-Topic Recheck-Batch über alle Kandidaten; aktualisiert images[] in
    topics_data in place. Resume-fest: keys werden deterministisch neu berechnet,
    Bild-Bytes aus .cache/downloads (graceful bei Cache-Miss). model: Anthropic-Modell
    (via stage_models.image_recheck_model gesteuert)."""
    try:
        import anthropic as _anthropic
        anth = _anthropic.Anthropic(api_key=anthropic_key)

        opus_reqs = []
        cid_target: dict[str, tuple[str, str]] = {}  # custom_id → (thema, filename)
        for cand in kandidaten:
            img   = cand["img"]
            thema = cand["thema"]
            fn    = img.get("filename", "")
            img_bytes = load_cached_image_bytes(img.get("thumb_url", ""))
            if img_bytes is None:
                log.warning("  Opus: Cache fehlt für %s — Gemini-Urteil behalten", fn[:40])
                continue
            custom_id = _normalize_custom_id(_img_key(thema, fn))
            cid_target[custom_id] = (thema, fn)
            opus_reqs.append({
                "custom_id": custom_id,
                "params": {
                    "model":      model,
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
                            {"type": "text", "text": OPUS_RECHECK_PROMPT.format(thema=thema)},
                        ],
                    }],
                },
            })

        if not opus_reqs:
            return
        opus_batch = anth.messages.batches.create(requests=opus_reqs)
        log.info("Opus-Recheck-Batch eingereicht: %s (%d Requests)", opus_batch.id, len(opus_reqs))
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

            thema, target_fn = cid_target.get(result.custom_id, ("", ""))
            new_ab   = int(opus_res.get("ab_stufe", 0))
            new_desc = opus_res.get("beschreibung", "")
            u        = result.result.message.usage
            cost_tracker.track(
                run_id=_RUN_ID, thema=thema, stufe="S0",
                schritt="vision_recheck", modell="claude-opus-4-8",
                input_tok=u.input_tokens, output_tok=u.output_tokens,
            )

            if thema and thema in topics_data:
                imgs = topics_data[thema]["images"]
                for i, img in enumerate(imgs):
                    if img.get("filename") == target_fn:
                        if new_ab == 0:
                            imgs.pop(i)
                            log.info("  Opus SPERRT: %s", target_fn[:40])
                        else:
                            if new_ab != img["ab_stufe"]:
                                log.info("  Opus: %s %d→%d", target_fn[:35], img["ab_stufe"], new_ab)
                            imgs[i] = {**img, "ab_stufe": new_ab, "beschreibung": new_desc}
                        break
    except Exception as e:
        log.error("Opus-Recheck-Batch Fehler: %s — Gemini-Urteile behalten", e)


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
    WP-Fetch → Kompass (sync) → Companion-Fetch → Image-Download
    → Vision-Check (sync) → Conservative Upgrade → Opus-Recheck-Batch

    Rückgabe: {thema: {primary_text, resolved_title, appeal, sensibel,
                        valid_companions, companion_texts, images}}
    """
    # Checkpoint-Resume: alle Topics sauber → ganze Stage überspringen (Schnellpfad,
    # kein Regress). Mind. ein companions_failed-Topic → Checkpoint wird Resume-Quelle,
    # Fall-through in Phase A; der done_topics-Filter überspringt nur die sauberen.
    cp = _load_cp_raw(out_dir, 1)
    cp_resume: dict | None = None
    if cp:
        cp_topics = cp.get("topics", {})
        n_failed = sum(1 for e in cp_topics.values() if e.get("companions_failed"))
        if n_failed == 0:
            log.info("Checkpoint Stage 1 (status=done, alle Topics sauber) — Stage übersprungen")
            return cp_topics
        log.warning(
            "Checkpoint Stage 1 enthält %d companions_failed-Topic(s) — Resume: "
            "gescheiterte neu durchlaufen, saubere übersprungen", n_failed
        )
        cp_resume = cp_topics

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
        print(f"Kompass-Auswahl (sync): {len(wp_data)} Aufrufe")
        n_sens = sum(1 for d in wp_data.values() if d["sensibel"])
        print(f"Vision-Check (sync): ~{len(wp_data) * MAX_VISION_CHECKS} Aufrufe (max {MAX_VISION_CHECKS}/Thema)")
        print(f"Opus-Recheck: {n_sens} sensible Themen → top-{OPUS_CAP} Bilder (relevanz-sortiert); sonst → grenzfall=true (max {OPUS_CAP})")
        return {}

    # ── Resume: saubere Topics übernehmen — EINE Quelle (Partial > Checkpoint) ─
    # Existiert ein Partial, war der letzte Lauf mitten in Phase A → aktuellster Stand.
    # Sonst die companions_failed-Checkpoint-Topics (cp_resume). EIN Filter für beide.
    partial_topics = _load_partial(out_dir)
    if partial_topics:
        resume_src, resume_origin = partial_topics, "stage1_partial.json"
    else:
        resume_src, resume_origin = (cp_resume or {}), "stage1_checkpoint.json"
    done_topics = {
        t: e for t, e in resume_src.items()
        if t in wp_data and not e.get("companions_failed", False)
    }
    if done_topics:
        log.info("Resume aus %s: %d saubere Topics übernommen — %s",
                 resume_origin, len(done_topics), list(done_topics.keys()))

    # ── Phase A: Pro-Topic-Loop (Kompass → Companion → Bild+Vision → Pool) ────
    log.info("\n=== Stage 1 / Phase A: Pro-Topic-Verarbeitung (%d Themen) ===", len(wp_data))
    topics_data: dict[str, dict] = dict(done_topics)
    failed_topics: list[str] = []
    cb_consecutive_failures = 0   # Circuit-Breaker-Zähler

    for thema, data in wp_data.items():
        if thema in done_topics:
            log.info("  '%s': Resume — übersprungen (bereits verarbeitet)", thema)
            continue

        # — Kompass (sync) — companions_failed-Marker bei 0 Companions (Fix 1) —
        companions_raw, usage = select_companions_raw(
            client, thema, data["primary_text"], model=GEN_MODEL,
            appeal=data.get("appeal", "medium"),
        )
        if usage:
            _kompass_model = stage_models.get_stage_config("kompass")["model"]
            cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                               schritt="kompass", modell=_kompass_model, **usage)
        api_exhausted     = (not companions_raw) and (not usage)
        companions_failed = not companions_raw
        if companions_failed:
            failed_topics.append(thema)
            log.warning("  Kompass '%s': 0 Companions — Topic in failed_topics", thema)
        else:
            log.info("  Kompass '%s': %d Vorschläge", thema, len(companions_raw))

        # — Circuit Breaker —
        if api_exhausted:
            cb_consecutive_failures += 1
            log.warning("  Circuit Breaker: %d/%d aufeinanderfolgende API-Ausfälle",
                        cb_consecutive_failures, CB_THRESHOLD)
            if cb_consecutive_failures >= CB_THRESHOLD:
                log.error(
                    "Circuit Breaker AUSGELÖST: %d aufeinanderfolgende Kompass-Ausfälle "
                    "— warte %d Minuten, dann weiter (nächste Topics könnten profitieren).",
                    cb_consecutive_failures, CB_WAIT_MIN)
                time.sleep(CB_WAIT_MIN * 60)
                cb_consecutive_failures = 0
                log.info("Circuit Breaker: Pause beendet, weiter mit nächstem Topic.")
        else:
            cb_consecutive_failures = 0   # Reset bei jedem erfolgreichen Call

        # — Companion-Validate + Fetch —
        companion_cap = COMPANION_CAP.get(data["appeal"], 5)
        valid_companions, _, _ = validate_and_resolve_companions(
            session, companions_raw, data["resolved_title"], cap=companion_cap,
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

        # — Bild-Kandidaten + Download + Vision-Sync —
        primary_wp = data["resolved_title"]
        comp_with_text = [c for c in valid_companions if c in companion_texts]
        all_candidates: list[dict] = []
        # LEITBILDER zuerst (kanonisch/bekannt): Infobox-Bild von Haupt- + JEDEM Companion
        # gezielt holen und voranstellen — generator=images kappt das Leitbild sonst
        # alphabetisch weg (z. B. Mona Lisa, Selbstbildnis, Abendmahl).
        for lt in [primary_wp] + comp_with_text:
            lead = fetch_lead_image(session, lt)
            time.sleep(0.3)
            if lead:
                lead["_source"] = lt
                all_candidates.append(lead)
                log.info("    Leitbild '%s': %s", lt, lead["filename"][:60])
        primary_imgs = fetch_image_candidates(session, primary_wp, max_candidates=MAX_IMG_PRIMARY)
        for img in primary_imgs:
            img["_source"] = primary_wp
        all_candidates.extend(primary_imgs)
        for comp in comp_with_text:
            time.sleep(0.3)
            comp_imgs = fetch_image_candidates(session, comp, max_candidates=MAX_IMG_COMPANION)
            for img in comp_imgs:
                img["_source"] = comp
            all_candidates.extend(comp_imgs)

        seen_fn: set[str] = set()
        unique: list[dict] = []
        for img in all_candidates:
            if img["filename"] not in seen_fn:
                seen_fn.add(img["filename"])
                unique.append(img)
        to_check = unique[:MAX_VISION_CHECKS]
        log.info("  '%s': %d Kandidaten, Vision-Check max %d", thema, len(unique), len(to_check))

        topic_meta:   dict[str, dict] = {}  # key → img-meta
        topic_vision: dict[str, dict] = {}  # key → vision-result
        vision_failed: list[dict] = []      # Bilder ohne Vision-Verdict (→ vision_retry.py)
        for i, img in enumerate(to_check):
            if i > 0:
                time.sleep(3.0)
            img_bytes = download_image(session, img["thumb_url"])
            if img_bytes is None:
                log.debug("    Download fehlgeschlagen: %s", img["filename"][:40])
                continue
            key = _img_key(thema, img["filename"])
            topic_meta[key] = {**img, "thema": thema}
            # Companion-Bilder bekommen präzisen Kontext: aus welchem Begleitartikel
            source = img.get("_source", "")
            if source and source != primary_wp:
                thema_vision = f"{thema} (Bild aus Begleitartikel: {source})"
            else:
                thema_vision = thema
            result, vusage = analyze_with_vision(
                client, img_bytes, "image/jpeg", thema_vision, model=VISION_MODEL
            )
            if result is None:
                vision_failed.append({**topic_meta[key],
                                      "vision_fail_reason": "no_result_after_retries"})
                log.warning("  Vision fehlgeschlagen (kein Ergebnis): %s",
                            img.get("title") or img.get("filename", "?"))
                continue
            topic_vision[key] = result
            if vusage:
                cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                                   schritt="vision", modell=VISION_MODEL,
                                   input_tok=vusage["input_tok"], output_tok=vusage["output_tok"])

        # — Conservative Upgrade + Pool (roh, ohne Opus) —
        accepted: list[dict] = []
        n_rejected = 0
        for key, img_meta in topic_meta.items():
            result = topic_vision.get(key)
            if result is None:
                n_rejected += 1
                continue
            ab_stufe        = result.get("ab_stufe", 0)
            grenzfall       = result.get("grenzfall", False)
            grenzfall_grund = result.get("grenzfall_grund", "")
            confidence      = result.get("confidence", "hoch")
            beschreibung    = result.get("beschreibung", "")
            relevanz        = result.get("relevanz", 0)
            bildqualitaet   = result.get("bildqualitaet", 5)
            hero            = result.get("hero_candidate", False)
            ist_symbol      = result.get("ist_symbol_oder_logo", False)
            ist_konkret     = result.get("ist_konkret", True)
            motiv_key       = (result.get("motiv_key") or "").strip().lower()
            if grenzfall and ab_stufe == 1:
                ab_stufe = 2
                log.info("    grenzfall=true: '%s' → ab_stufe 1→2 (%s)",
                         img_meta.get("filename", "")[:40], grenzfall_grund[:60])
            # Logo/Wappen/Symbol NICHT hart verwerfen (kann beim passenden Thema
            # sinnvoll sein, z.B. Landesflagge). Nur nie Hero; tangentiale Symbole
            # filtert die Relevanz-Schwelle (relevanz<4) ohnehin heraus.
            if ist_symbol:
                hero = False
            # Abstrakt (Diagramm/Schema/Detail/Karte) → nicht für die Kleinsten, nie Hero
            if not ist_konkret:
                if ab_stufe < 2:
                    ab_stufe = 2
                hero = False
            if ab_stufe == 0 or relevanz < 4:
                n_rejected += 1
                continue
            accepted.append({
                **img_meta,
                "ab_stufe":        ab_stufe,
                "grenzfall":       grenzfall,
                "grenzfall_grund": grenzfall_grund,
                "confidence":      confidence,
                "relevanz":        relevanz,
                "bildqualitaet":   bildqualitaet,
                "hero_candidate":  hero,
                "ist_konkret":     ist_konkret,
                "motiv_key":       motiv_key,
                "beschreibung":    beschreibung,
            })
        # Bei Motiv-Dubletten das qualitativ beste Foto behalten: nach Relevanz,
        # dann Bildqualität, dann Hero sortieren — Dedup behält jeweils das erste.
        accepted.sort(key=lambda x: (-x["relevanz"], -x.get("bildqualitaet", 5),
                                     -int(x.get("hero_candidate", False))))
        # Dubletten desselben Motivs entfernen (z.B. 3× Kolosseum) → bestes je motiv_key
        _seen_motive: set[str] = set()
        _deduped: list[dict] = []
        for a in accepted:
            mk = a.get("motiv_key", "")
            if mk and mk in _seen_motive:
                log.info("    Dublette verworfen (%s): '%s'", mk, a.get("filename", "")[:40])
                continue
            if mk:
                _seen_motive.add(mk)
            _deduped.append(a)
        accepted = _deduped
        # Sensible Themen: Pool auf top-OPUS_CAP begrenzen (Stage 2 zieht nur daraus)
        images = accepted[:OPUS_CAP] if data["sensibel"] else accepted
        s1 = sum(1 for i in images if i.get("ab_stufe", 0) == 1)
        s2 = sum(1 for i in images if i.get("ab_stufe", 0) == 2)
        s3 = sum(1 for i in images if i.get("ab_stufe", 0) == 3)
        log.info("  '%s': %d akzeptiert, %d verworfen → Pool %d (S1=%d S2=%d S3=%d)",
                 thema, len(accepted), n_rejected, len(images), s1, s2, s3)

        # — Topic-Eintrag assemblieren + Partial atomar persistieren —
        topics_data[thema] = {
            "primary_text":      data["primary_text"],
            "resolved_title":    data["resolved_title"],
            "lemma_flags":       data["lemma_flags"],
            "framing_note":      data["framing_note"],
            "appeal":            data["appeal"],
            "sensibel":          data["sensibel"],
            "valid_companions":  valid_companions,
            "companion_texts":   companion_texts,
            "companions_failed": companions_failed,
            "images":            images,
            "images_vision_failed": vision_failed,
        }
        if vision_failed:
            log.error("  %s: %d Bild(er) ohne Vision-Verdict — "
                      "vision_retry.py ausführen vor Stage 2!", thema, len(vision_failed))
        _save_partial(out_dir, topics_data)

    # ── Phase B: Bild-Recheck-Nachlauf (cross-topic, über alle Partial-Topics) ─
    # Nur wenn in stage_models aktiviert (provider 'anthropic'); sonst Gemini-Urteil.
    _recheck_model = stage_models.image_recheck_model()
    if anthropic_key and _recheck_model:
        opus_kandidaten: list[dict] = []
        for thema, entry in topics_data.items():
            imgs = entry.get("images", [])
            if entry.get("sensibel"):
                pool = imgs  # bereits auf OPUS_CAP begrenzt (Phase A)
            else:
                # Nicht-sensibel: nur grenzfall=true-Bilder → Recheck, gecappt
                pool = [e for e in imgs if e.get("grenzfall", False)][:OPUS_CAP]
            for e in pool:
                opus_kandidaten.append({"thema": thema, "img": e})
        if opus_kandidaten:
            log.info("\n=== Stage 1 / Phase B: Bild-Recheck (%s, %d Bilder) ===",
                     _recheck_model, len(opus_kandidaten))
            _opus_recheck(anthropic_key, opus_kandidaten, topics_data, model=_recheck_model)

    # ── Pool-Übersicht je Thema (nach Opus) ───────────────────────────────────
    for thema, entry in topics_data.items():
        imgs = entry.get("images", [])
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

    # ── Phase C: Finalisierung (Checkpoint schreiben, Partial aufräumen) ──────
    if failed_topics:
        log.error("Stage 1 abgeschlossen — %d Topics ohne Companions: %s — Neustart empfohlen",
                  len(failed_topics), failed_topics)
    _save_cp(out_dir, 1, {"status": "done", "topics": topics_data})
    try:
        _partial_path(out_dir).unlink(missing_ok=True)
    except OSError:
        pass
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
    S2/S3 (age_level 2/3): ein Bild bei <=5 Sätzen; bis zu ZWEI erst bei mehr als
      5 Sätzen (Prompt-Regel maßgeblich, Code = Backstop). Die vom Generator je
      Satz gesetzte Zuordnung auf die beiden Section-Bilder bleibt erhalten;
      positionsbasierter Split nur als Fallback.
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
        allow_two = age in (2, 3) and n > 5 and len(ranked) >= 2

        if not allow_two:
            chosen = ranked[0]
            for s in sents:
                s["img_index"] = chosen
        else:
            a, b = ranked[0], ranked[1]
            allowed = {a, b}
            # Semantische Generator-Zuordnung beibehalten statt positionsbasiert neu
            # verteilen: Sätze, die schon auf eines der beiden Section-Bilder zeigen,
            # bleiben; -1-/Fremdbild-Sätze erben per Forward-Fill das laufende Bild
            # (führende -1 erben das dominante Bild a). Rückfall auf den alten
            # Positions-Split nur, wenn KEIN Satz auf a/b zeigt (kaputte Zuordnung).
            if any(s.get("img_index", -1) in allowed for s in sents):
                last = a
                for s in sents:
                    ix = s.get("img_index", -1)
                    if ix in allowed:
                        last = ix
                    else:
                        s["img_index"] = last
            else:
                half = n // 2  # floor(n/2) Sätze → Bild A, Rest → Bild B
                for i, s in enumerate(sents):
                    s["img_index"] = a if i < half else b


# ── Stage 2: GENERIERUNG ──────────────────────────────────────────────────────

def _stage2_pipeline_new(
    themen: list[str],
    stufen: list[int],
    topics_data: dict,
    out_dir: Path,
    client: genai.Client,
    api_key: str,
    anthropic_key: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Stage 2 über die NEUE modulare Pass-Pipeline (Pass 1→2→6).

    Synchron pro Thema×Stufe (umgeht die Batch-Maschinerie). Resume via
    Datei-Existenz + age_floor-Gate wie im alten Pfad. Schreibt app-valides
    JSON im selben Format. Boxen/Bilder/Quiz sind MVP-Stubs (Phase 2/3).
    """
    import pipeline_new  # lazy: nur laden, wenn der neue Pfad wirklich läuft

    articles_dir = out_dir / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    # Erwartete Artikel + Resume-Vorscan (Datei-Existenz = Wahrheitsquelle)
    articles: dict[str, str] = {}
    plan_jobs: list[dict] = []
    for thema in themen:
        data = topics_data.get(thema)
        if not data:
            log.warning("  '%s' fehlt in topics_data — übersprungen", thema)
            continue
        if data.get("companions_failed"):
            log.warning("  '%s': companions_failed — Stage 2 (new) übersprungen", thema)
            continue
        slug = thema.lower().replace(" ", "_").replace("/", "_")
        age_floor = int(data.get("age_floor") or 1)
        for stufe in stufen:
            aid = f"{slug}_l{stufe}"
            op = articles_dir / f"{aid}.json"
            if op.exists():
                articles[aid] = str(op)
                log.info("  %s: bereits vorhanden — übersprungen (Resume)", aid)
                continue
            if stufe < age_floor:
                log.info("  age_floor-Gate: '%s' S%d < floor S%d — übersprungen",
                         thema, stufe, age_floor)
                continue
            plan_jobs.append({"thema": thema, "data": data, "slug": slug, "stufe": stufe})

    if dry_run:
        print("\n=== DRY-RUN Stage 2 (Pipeline NEW) ===")
        print(f"Neu zu generieren: {len(plan_jobs)} Artikel (synchron, Pass 1→2→6)")
        for pj in plan_jobs:
            print(f"  {pj['slug']}_l{pj['stufe']}  (Modell {pipeline_new.BASELINE_MODEL})")
        print(f"Bereits vorhanden (Resume): {len(articles)}")
        return articles

    # Quelltext-Cache je Thema (einmal), von allen Pässen aller Stufen geteilt
    # → spart auf dem wiederholten Quelltext ~75 % Tokens + deutlich Laufzeit.
    # Graceful: None (kleines Thema/Fehler) → voller Kontext je Pass.
    src_caches: dict[str, str | None] = {}
    for pj in plan_jobs:
        th = pj["thema"]
        if th not in src_caches:
            d = pj["data"]
            src_caches[th] = pipeline_new.create_source_cache(
                client, pipeline_new.BASELINE_MODEL, th,
                d["primary_text"], d.get("companion_texts", {}))

    ok = flagged = failed = 0
    for pj in plan_jobs:
        thema, data, slug, stufe = pj["thema"], pj["data"], pj["slug"], pj["stufe"]
        job = _stage2_job(thema, data, slug, stufe)
        aid = job["article_id"]
        log.info("\n--- [new] %s (S%d) ---", aid, stufe)
        try:
            article, report = pipeline_new.generate_article_new(
                job,
                data["primary_text"],
                data.get("companion_texts", {}),
                data.get("valid_companions", []),
                model=pipeline_new.BASELINE_MODEL,
                run_id=_RUN_ID,
                cache=src_caches.get(thema),
                images=data.get("images", []),
                appeal=data.get("appeal", "medium"),
            )
        except Exception as e:
            log.error("  [new] %s: unerwarteter Fehler — übersprungen: %s", aid, e)
            failed += 1
            continue
        if article is None:
            log.error("  [new] %s: keine Ausgabe (%s) — übersprungen",
                      aid, "; ".join(report.get("errors", [])) or "unbekannt")
            failed += 1
            continue

        # App-Validität prüfen (schreiben trotzdem — Shadow-/Validierungslauf, geflaggt).
        # word_floor=wmin wie im alten Pfad: wenige lange Sätze bei gesundem
        # Wortbudget sind stilistisch, kein Stub-Signal.
        try:
            val_errors = validate_article(article, job, word_floor=report.get("wmin"))
        except Exception as _ve:
            val_errors = [f"validate_article exception: {_ve}"]
        if val_errors:
            for ve in val_errors:
                log.warning("  [new] %s Validierung: %s", aid, ve)
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "") + "; "
                + "; ".join(val_errors[:3])).lstrip("; ")
            flagged += 1
        else:
            ok += 1

        op = articles_dir / f"{aid}.json"
        op.write_text(json.dumps(article, ensure_ascii=False, indent=2, default=str),
                      encoding="utf-8")
        articles[aid] = str(op)
        log.info("  [new] %s gespeichert: %d Sätze, %d Boxen, %d Bilder, %d Quiz, %d Belege, %d Wörter%s",
                 aid, report.get("n_sentences", 0), report.get("n_boxes", 0),
                 report.get("n_images", 0), report.get("n_quiz", 0),
                 report.get("n_source_passages", 0),
                 report.get("word_count", 0), "  ⚠ Validierung" if val_errors else "")

    # Quelltext-Caches best-effort löschen (sonst via TTL, unkritisch).
    for th, cn in src_caches.items():
        if cn:
            try:
                client.caches.delete(name=cn)
            except Exception:
                pass

    log.info("\n=== Stage 2 (new) fertig: %d OK, %d mit Validierungsfehler, %d fehlgeschlagen ===",
             ok, flagged, failed)
    _save_cp(out_dir, 2, {"status": "done", "articles": articles})
    return articles


def stage2_generierung(
    themen: list[str],
    stufen: list[int],
    topics_data: dict,
    out_dir: Path,
    client: genai.Client,
    api_key: str,
    anthropic_key: str = None,
    dry_run: bool = False,
    pipeline: str = "old",
) -> dict:
    """
    Stage 2: Gemini Batch — Artikel-Generierung (Themen × Stufen).

    1. Je Thema: Gemini Context Cache (stable Wikipedia-Prefix)
    2. Je Thema × Stufe: InlinedRequest mit variablem Suffix + source_passages-Wrapper
    3. Gemini Batch einreichen + pollen
    4. Post-Processing (synchron): JSON-Parse, Wortzahl-Guard, Box-Guard, is_hero
    """
    # ── Pipeline-Schalter ────────────────────────────────────────────────────
    # Der neue modulare Pfad (Pass 1→2→6) läuft synchron pro Thema×Stufe und
    # umgeht die Batch-Maschinerie komplett. Der alte Pfad darunter bleibt
    # dadurch nachweislich unberührt (Fallback-Garantie).
    if pipeline == "new":
        return _stage2_pipeline_new(
            themen, stufen, topics_data, out_dir, client, api_key,
            anthropic_key, dry_run=dry_run,
        )

    # Resume-fest: ganze Stage NUR überspringen, wenn ALLE erwarteten Artikel
    # (themen × stufen) bereits als JSON auf Platte liegen. Datei-Existenz ist die
    # Wahrheitsquelle (nicht companions_failed wie Stage 1 — bewusste Asymmetrie).
    # Sonst Fall-through: Disk-Vorscan + Pro-Artikel-Skip generieren nur das Fehlende.
    cp = _load_cp_raw(out_dir, 2)
    if cp is not None:
        art_dir = out_dir / "articles"
        expected_ids = [
            f"{t.lower().replace(' ', '_').replace('/', '_')}_l{s}"
            for t in themen for s in stufen
        ]
        missing = [a for a in expected_ids if not (art_dir / f"{a}.json").exists()]
        if not missing:
            log.info("Checkpoint Stage 2 (status=done, alle %d Artikel vorhanden) "
                     "— Stage übersprungen", len(expected_ids))
            return cp.get("articles", {})
        log.warning("Checkpoint Stage 2 unvollständig (%d/%d Artikel fehlen: %s) — "
                    "Resume: fehlende neu generieren, vorhandene überspringen",
                    len(missing), len(expected_ids), ", ".join(missing))

    if not SYSTEM_PROMPT_PATH.exists():
        log.error("System-Prompt fehlt: %s", SYSTEM_PROMPT_PATH)
        return {}
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    thinking_cfg = _make_thinking_config(GEN_MODEL, budget_for_2_5=8192)
    articles_dir = out_dir / "articles"
    articles_dir.mkdir(exist_ok=True)

    # Provider-Schalter (Weg B): generator-Stufe gemini ODER anthropic.
    gen_cfg      = stage_models.get_stage_config("generator")
    gen_provider = gen_cfg["provider"]
    gen_model    = gen_cfg["model"]
    # Im anthropic-Pfad gibt das Modell den Artikel über das emit-Tool aus → der
    # v4-<planung>-Block entfällt (Planung wandert ins thinking). Hinweis NUR lokal
    # anhängen, die Prompt-Datei bleibt unangetastet (Gemini-Pfad nutzt system_prompt pur).
    system_prompt_emit = system_prompt + (
        "\n\n## AUSGABE-MODUS (tool-use)\n"
        "Gib den Artikel AUSSCHLIESSLICH über das Tool `emit` aus (rufe es IMMER auf). "
        "Kein Freitext, kein <planung>-Block — die Planung gehört in den Denkprozess. "
        "Das emit-Tool-Input ist das vollständige Artikel-JSON."
    )

    if dry_run:
        n = sum(1 for t in themen if t in topics_data)
        total = n * len(stufen)
        print(f"\n=== DRY-RUN Stage 2 ===")
        print(f"Artikel-Batch: {total} Requests ({n} Themen × {len(stufen)} Stufen)")
        print(f"  Gemini Context Cache: 1 Cache je Thema (stable Wikipedia-Prefix)")
        print(f"  Variable Suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL + source_passages-Wrapper")
        print(f"  Post-Processing: Wortzahl-Guard + Box-Guard (synchron)")
        return {}

    # ── Step 1: Context-Caches je Thema (nur Gemini-Pfad) ───────────────────
    # Anthropic nutzt Prompt-Caching (cache_control: ephemeral) direkt im Request,
    # nicht das Gemini-Cache-Objekt → Step 1 entfällt dort.
    caches: dict[str, str | None] = {}
    if gen_provider == "gemini":
        log.info("\n=== Stage 2 / Step 1: Context-Caches (%d Themen) ===", len(themen))
        for thema in themen:
            data = topics_data.get(thema)
            if not data:
                log.warning("  '%s' fehlt in topics_data — kein Cache", thema)
                caches[thema] = None
                continue
            if data.get("companions_failed"):
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
    gen_reqs:       list[types.InlinedRequest] = []   # Gemini-Pfad
    anthropic_reqs: list[dict]                 = []   # Anthropic-Pfad (Message-Batches)
    req_meta:  dict[str, dict]                 = {}   # article_id → Metadaten für Post-Processing

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
        if data.get("companions_failed"):
            log.warning("  '%s': companions_failed — Stage 2 übersprungen", thema)
            continue
        slug       = thema.lower().replace(" ", "_").replace("/", "_")
        images_all = data.get("images", [])
        appeal     = data.get("appeal", "medium")
        # Gemini Batch: cached_content in InlinedRequest inkompatibel → voller Prompt
        # je Request. Anthropic: Prompt-Caching via cache_control direkt im Request.
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

            stable, _ = _split_grounded_user_message(
                job, data["primary_text"],
                data.get("companion_texts", {}),
                data.get("valid_companions", []),
                images_all,
            )
            variable = _gen2_variable_suffix(job, wmax)

            req_meta[article_id] = {
                "thema":        thema,
                "stufe":        stufe,
                "job":          job,
                "images_stufe": images_stufe,
                "wmin":         wmin,
                "wmax":         wmax,
            }

            if gen_provider == "anthropic":
                anthropic_reqs.append({
                    "custom_id": article_id,
                    "params": {
                        "model":       gen_model,
                        "max_tokens":  32768,
                        "thinking":    {"type": "enabled", "budget_tokens": 8192},
                        "tools": [{
                            "name": "emit",
                            "description": "Gib den vollständigen Artikel als JSON-Objekt aus.",
                            "input_schema": stage_models.ARTICLE_SCHEMA,
                        }],
                        "tool_choice": {"type": "auto"},   # forced + thinking inkompatibel
                        "system": [{"type": "text", "text": system_prompt_emit,
                                    "cache_control": {"type": "ephemeral"}}],
                        "messages": [{"role": "user", "content": [
                            {"type": "text", "text": stable,
                             "cache_control": {"type": "ephemeral"}},
                            {"type": "text", "text": variable},
                        ]}],
                    },
                })
            else:
                full_msg = stable + "\n" + variable
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
                gen_reqs.append(types.InlinedRequest(
                    contents=contents,
                    config=cfg,
                    metadata={"key": article_id},
                ))
            log.info("  %s: S%d | %d Bilder | Wmax=%d | Provider=%s",
                     article_id, stufe, len(images_stufe), wmax, gen_provider)

    if not gen_reqs and not anthropic_reqs:
        if articles:
            log.info("Stage 2: keine neuen Requests — alle %d Artikel bereits vorhanden",
                     len(articles))
            _save_cp(out_dir, 2, {"status": "done", "articles": articles})
            return articles
        log.error("Stage 2: keine Requests — abgebrochen")
        return {}

    # ── Step 3 / PHASE A: Roh-Artikel sammeln (provider-abhängig) ───────────
    # raw_articles[article_id] = (payload, usage)
    #   payload: str  → Gemini-Rohtext (in Phase B via _parse_gen2_response geparst)
    #   payload: dict → Anthropic emit-Output (bereits destringified)
    raw_articles: dict[str, tuple] = {}
    _status_seen: set = set()   # article_ids mit bereits geschriebenem run_status (Doppel-Vermeidung)

    if gen_provider == "anthropic":
        import anthropic
        if not anthropic_key:
            log.error("Generator-Provider=anthropic, aber ANTHROPIC_API_KEY fehlt — Abbruch.")
            return {}
        log.info("\n=== Stage 2 / Step 3: Sonnet-Generierungs-Batch (%d Requests) ===",
                 len(anthropic_reqs))
        aclient = anthropic.Anthropic(api_key=anthropic_key)
        # Batch-Create gegen transiente 5xx/429 absichern (502 Bad Gateway beobachtet)
        abatch = None
        for _att in range(1, 5):
            try:
                abatch = aclient.messages.batches.create(requests=anthropic_reqs)
                break
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                _code = getattr(e, "status_code", None)
                if _att < 4 and (_code is None or _code in (429, 500, 502, 503, 529)):
                    _wait = min(10 * 2 ** (_att - 1), 80)
                    log.warning("  Batch-Create %s (Versuch %d/4) — warte %ds",
                                type(e).__name__, _att, _wait)
                    time.sleep(_wait)
                else:
                    raise
        log.info("Anthropic-Batch eingereicht: %s", abatch.id)
        while abatch.processing_status == "in_progress":
            time.sleep(15)
            abatch = aclient.messages.batches.retrieve(abatch.id)
            c = abatch.request_counts
            log.info("  Batch %s … %s (✓%d ✗%d ⌛%d)", abatch.id[:20],
                     abatch.processing_status, c.succeeded, c.errored, c.processing)
        for result in aclient.messages.batches.results(abatch.id):
            aid = result.custom_id
            if result.result.type != "succeeded":
                log.error("  [%s] Anthropic-Batch: %s — Artikel fehlt", aid, result.result.type)
                continue
            msg = result.result.message
            art = next((b.input for b in msg.content
                        if b.type == "tool_use" and b.name == "emit"), None)
            if art is None:
                # tool_choice=auto → emit evtl. ausgelassen → Freitext-Fallback
                text = "".join(b.text for b in msg.content if b.type == "text")
                try:
                    art, _sp = _parse_gen2_response(text)
                except Exception as e:
                    log.error("  [%s] kein emit-Block + Freitext-Parse: %s", aid, e)
                    err_dir = out_dir / "_errors"
                    err_dir.mkdir(exist_ok=True)
                    (err_dir / f"{aid}_raw.txt").write_text(text or "", encoding="utf-8")
                    continue
            else:
                try:
                    art = generate_grounded._destringify_article(art)
                except Exception as e:
                    log.error("  [%s] Destringify/Parse: %s", aid, str(e)[:100])
                    err_dir = out_dir / "_errors"
                    err_dir.mkdir(exist_ok=True)
                    # Roh-emit-Input sichern (Inspektion + späterer Re-Parse, kein Batch-Verlust)
                    (err_dir / f"{aid}_raw.json").write_text(
                        json.dumps(art, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
                    continue
            u = msg.usage
            usage = {
                "input_tok":    u.input_tokens,
                "output_tok":   u.output_tokens,
                "cached_tok":   getattr(u, "cache_read_input_tokens", 0),
                "thoughts_tok": 0,
            }
            raw_articles[aid] = (art, usage)
    else:
        log.info("\n=== Stage 2 / Step 3: Gemini-Generierungs-Batch (%d Requests) ===",
                 len(gen_reqs))
        gen_batch = client.batches.create(model=GEN_MODEL, src=gen_reqs)
        log.info("Batch eingereicht: %s", gen_batch.name)
        try:
            gen_batch = poll_gemini_batch(client, gen_batch.name)
        except TimeoutError as _te:
            # Stall: alle noch offenen Artikel dieses Batches als FAILED(timeout) vermerken,
            # dann weiterreichen (Exit≠0 bleibt erhalten — sichtbarer Fehlerzustand).
            for _aid in req_meta:
                _th, _st = _thema_stufe_from_aid(_aid, req_meta)
                _run_status(_th, _st, "FAILED", "timeout", str(_te))
            raise
        state = _state_str(gen_batch)
        if state not in SUCCESS_STATES:
            log.error("Generierungs-Batch fehlgeschlagen: %s — Artikel fehlen", state)
            for _aid in req_meta:
                _th, _st = _thema_stufe_from_aid(_aid, req_meta)
                _run_status(_th, _st, "FAILED", "other", f"batch_state:{state}")
            return {}
        for resp in _get_inlined_responses(gen_batch):
            meta_resp = getattr(resp, "metadata", {}) or {}
            aid = meta_resp.get("key", "")
            if not aid or aid not in req_meta:
                log.warning("  Unbekannte Response-Key: '%s'", aid)
                continue
            raw   = _extract_text(getattr(resp, "response", None))
            usage = _extract_usage(getattr(resp, "response", None))
            if not raw:
                log.error("  [%s] Leere Batch-Antwort", aid)
                _th, _st = _thema_stufe_from_aid(aid, req_meta)
                _run_status(_th, _st, "FAILED", "empty_output", "Leere Batch-Antwort")
                _status_seen.add(aid)
                continue
            raw_articles[aid] = (raw, usage)

    # ── Step 4 / PHASE B: Post-Processing (provider-NEUTRAL) ────────────────
    log.info("\n=== Stage 2 / Step 4: Post-Processing (%d Roh-Artikel) ===", len(raw_articles))
    # articles wurde in Step 2 vorinitialisiert (bereits gespeicherte Artikel)
    _gen_model_label = gen_model if gen_provider == "anthropic" else GEN_MODEL

    for article_id, (payload, usage) in raw_articles.items():
        m         = req_meta[article_id]
        thema     = m["thema"]
        stufe     = m["stufe"]
        job       = m["job"]
        imgs_s    = m["images_stufe"]
        wmin      = m["wmin"]
        wmax      = m["wmax"]
        data      = topics_data[thema]

        if usage:
            cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe=f"S{stufe}",
                               schritt="article_gen", modell=_gen_model_label, **usage)

        # payload: str (Gemini) → parsen; dict (Anthropic emit) → direkt nutzen
        if isinstance(payload, str):
            try:
                article, source_passages = _parse_gen2_response(payload)
            except Exception as e:
                log.error("  [%s] JSON-Parse: %s", article_id, e)
                err_dir = out_dir / "_errors"
                err_dir.mkdir(exist_ok=True)
                (err_dir / f"{article_id}_raw.txt").write_text(payload or "", encoding="utf-8")
                _run_status(thema, stufe, "FAILED", "degraded_output", f"JSON-Parse: {e}")
                _status_seen.add(article_id)
                continue
        else:
            article         = payload
            source_passages = article.get("source_passages", []) or []

        # Metadaten
        article.setdefault("meta", {})
        article["meta"]["id"]                   = article_id
        article["meta"]["title"]                = thema
        article["meta"]["generated_at"]         = datetime.now(timezone.utc).isoformat()
        article["meta"]["grounding_companions"] = data.get("valid_companions", [])
        _prompt_version = SYSTEM_PROMPT_PATH.stem.split("_v")[-1].split("_")[0]
        article["meta"]["generation_method"]    = f"{_gen_model_label}/batch/v{_prompt_version}"
        article["meta"]["generation_temperature"] = 1.0
        article["meta"]["generation_thinking"]    = "8192" if gen_provider == "anthropic" else "MEDIUM"

        # Wortzahl-Guard
        word_count = count_article_words(article)
        trim_limit = round(wmax * 1.25)   # Trim-Schwelle UND Trim-Ziel; Erzählfluss vor Länge
        log.info("  [%s] Wortzahl: %d (Ziel-Band %d–%d, Trim ab %d)",
                 article_id, word_count, wmin, wmax, trim_limit)

        trims = 0
        orig_box_count = sum(len(s.get("boxes", [])) for s in article.get("sections", []))
        while word_count > trim_limit and trims < 2:
            trims += 1
            log.warning("  [%s] Zu lang (%d > %d) — Trim %d/2", article_id, word_count, trim_limit, trims)
            try:
                trimmed, trimmed_wc = _trim_article_to_cap(article, trim_limit, GEN_MODEL, thinking_cfg)
                u = dict(generate_grounded._last_trim_usage)
                _m = u.pop("model", GEN_MODEL)
                if u:
                    cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe=f"S{stufe}",
                                       schritt="trim", modell=_m, **u)
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
        # Fix 2: review_flag wenn Artikel nach Trim immer noch über dem Trim-Limit liegt
        if word_count > trim_limit:
            log.warning("  [%s] Über Trim-Limit (%d > %d) nach Trim — review_flag", article_id,
                        word_count, trim_limit)
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                (article["meta"].get("review_reason", "") + f"; Wortzahl {word_count} > Trim-Limit {trim_limit}")
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
                u = dict(generate_grounded._last_box_usage)
                _m = u.pop("model", GEN_MODEL)
                if u:
                    cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe=f"S{stufe}",
                                       schritt="box_repair", modell=_m, **u)
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
        _run_status(thema, stufe, "OK")
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

    # Reconcile: neu angeforderte Artikel, die weder OK noch bereits FAILED gemeldet
    # wurden (z.B. still aus der Batch-Antwort verschwunden) → als FAILED("other") melden.
    _written = {a for a in req_meta if a in articles}
    for _aid in req_meta:
        if _aid not in _written and _aid not in _status_seen:
            _th, _st = _thema_stufe_from_aid(_aid, req_meta)
            _run_status(_th, _st, "FAILED", "other", "kein Ergebnis im Batch (missing)")
    # Einzeilige Klartext-Zusammenfassung ins Log (ein Blick ins Log-Ende genügt).
    _n_req  = len(req_meta)
    _n_ok   = len(_written)
    _n_fail = _n_req - _n_ok
    log.info("RUN-ZUSAMMENFASSUNG Stage2 (Run %s): %d/%d Artikel OK, %d FAILED%s",
             _RUN_ID, _n_ok, _n_req, _n_fail,
             "" if _n_fail == 0 else " — siehe run_status.jsonl")

    _save_cp(out_dir, 2, {"status": "done", "articles": articles})
    return articles


# ── Stage 3: LEKTORAT ────────────────────────────────────────────────────────

def _stage3_lektorat_new(
    themen: list[str],
    stufen: list[int],
    topics_data: dict,
    out_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Stage 3 über das NEUE Lektorat (Pass A Fakten + Pass B Stil, re-grounded).

    Synchron pro Artikel; prüft gegen den Phase-1-Quelltext-Snapshot aus
    topics_data. Schreibt review-kompatible lektorat_{aid}.json. Resume via
    Datei-Existenz. Alter Lektorat-Pfad bleibt unberührt.
    """
    import json as _json
    import lektorat_new

    art_dir = out_dir / "articles"
    lekt_dir = out_dir / "lektorat"
    lekt_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    jobs = []
    for thema in themen:
        data = topics_data.get(thema)
        if not data:
            continue
        slug = thema.lower().replace(" ", "_").replace("/", "_")
        for stufe in stufen:
            aid = f"{slug}_l{stufe}"
            src = art_dir / f"{aid}.json"
            dst = lekt_dir / f"lektorat_{aid}.json"
            if dst.exists():
                results[aid] = str(dst)
                continue
            if src.exists():
                jobs.append((thema, data, stufe, aid, src, dst))

    if dry_run:
        print(f"\n=== DRY-RUN Stage 3 (Lektorat NEW) ===")
        print(f"Zu lektorieren: {len(jobs)} Artikel (Pass A→B, Modell {lektorat_new.LEKTORAT_MODEL})")
        return results

    ok = failed = 0
    for thema, data, stufe, aid, src, dst in jobs:
        log.info("\n--- [lektorat-new] %s (S%d) ---", aid, stufe)
        try:
            article = _json.loads(src.read_text(encoding="utf-8"))
            article, stats = lektorat_new.run_lektorat_new(
                article,
                data.get("resolved_title", thema),
                data["primary_text"],
                data.get("companion_texts", {}),
                stufe,
            )
            dst.write_text(_json.dumps(article, ensure_ascii=False, indent=2, default=str),
                           encoding="utf-8")
            results[aid] = str(dst)
            ok += 1
            log.info("  [lektorat-new] %s: A %d/%d, B %d angewandt/%d verworfen%s",
                     aid, stats["a_applied"], stats["a_pruefen"],
                     stats["b_applied"], stats["b_rejected"],
                     "  ⚠ " + "; ".join(stats["errors"]) if stats["errors"] else "")
        except Exception as e:
            log.error("  [lektorat-new] %s: fehlgeschlagen — übersprungen: %s", aid, e)
            failed += 1

    log.info("\n=== Stage 3 (Lektorat new) fertig: %d OK, %d fehlgeschlagen ===", ok, failed)
    _save_cp(out_dir, 3, {"status": "done", "lektorat_results": results})
    return results


def stage3_lektorat(
    themen: list[str],
    stufen: list[int],
    articles: dict,
    topics_data: dict,
    out_dir: Path,
    anthropic_key: str,
    dry_run: bool = False,
    pipeline: str = "old",
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
    # ── Pipeline-Schalter ────────────────────────────────────────────────────
    # Neuer Pfad: fokussiertes Zwei-Pass-Lektorat (A Fakten + B Stil, re-grounded),
    # synchron. Alter Batch-Pfad darunter unberührt (Fallback-Garantie).
    if pipeline == "new":
        return _stage3_lektorat_new(themen, stufen, topics_data, out_dir, dry_run=dry_run)

    import anthropic

    # Resume-fest (analog Stage 2): ganze Stage NUR überspringen, wenn ALLE erwarteten
    # Lektorate (themen × stufen) bereits auf Platte liegen. Sonst Fall-through —
    # der Datei-Vorscan (unten) + Pro-Lektorat-Skip lektorieren nur das Fehlende.
    cp = _load_cp_raw(out_dir, 3)
    if cp is not None:
        lekt_dir_chk = out_dir / "lektorat"
        expected_ids = [
            f"{t.lower().replace(' ', '_').replace('/', '_')}_l{s}"
            for t in themen for s in stufen
        ]
        missing = [a for a in expected_ids
                   if not (lekt_dir_chk / f"lektorat_{a}.json").exists()]
        if not missing:
            log.info("Checkpoint Stage 3 (status=done, alle %d Lektorate vorhanden) "
                     "— Stage übersprungen", len(expected_ids))
            return cp.get("lektorat_results", {})
        log.warning("Checkpoint Stage 3 unvollständig (%d/%d Lektorate fehlen: %s) — "
                    "Resume: fehlende neu lektorieren, vorhandene überspringen",
                    len(missing), len(expected_ids), ", ".join(missing))

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

    # Datei-Vorscan (Spiegel von Stage 2 Teil A): bereits lektorierte Artikel
    # vormerken, damit der finale Checkpoint vollständig bleibt und bei reinem
    # Resume nicht auf den aktuellen Batch zusammenschrumpft (Titanic/WW2 würden
    # sonst aus lektorat_results fallen, obwohl ihre Dateien auf Platte liegen).
    lektorat_results: dict[str, str] = {}
    for _t in themen:
        _slug = _t.lower().replace(" ", "_").replace("/", "_")
        for _s in stufen:
            _aid = f"{_slug}_l{_s}"
            _lp  = lektorat_dir / f"lektorat_{_aid}.json"
            if _lp.exists():
                lektorat_results[_aid] = str(_lp)

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
        log.info("Stage 3: keine offenen Artikel — %d bereits lektoriert übernommen",
                 len(lektorat_results))
        _save_cp(out_dir, 3, {"status": "done", "lektorat_results": lektorat_results})
        return lektorat_results

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
                "model":       LEKTORAT_MODEL,
                "max_tokens":  16000,
                "temperature": 0,  # Reproduzierbarkeit: gleicher Artikel → gleiches Lektorat
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

    # lektorat_results ist bereits per Datei-Vorscan vorbefüllt (s.o.) — die
    # Batch-Ergebnisse unten ergänzen nur die NEU lektorierten Artikel.
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
    """Stage 4: TTS-Vertonung aller Artikel via tts_produce.produce_article()."""
    import tts_produce  # Root liegt bereits im sys.path (wie cost_tracker)

    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Erwartete Artikel-Liste aufbauen (analog Stage-2-expected_ids-Muster)
    targets = []
    for thema in themen:
        slug = thema.lower().replace(" ", "_").replace("/", "_")
        for stufe in stufen:
            article_id = f"{slug}_l{stufe}"
            # Lektorat-Fassung bevorzugen (korrigierter Text), Fallback auf articles/
            lektorat_path = out_dir / "lektorat" / f"lektorat_{article_id}.json"
            articles_path = out_dir / "articles" / f"{article_id}.json"
            if lektorat_path.exists():
                json_path, quelle = lektorat_path, "lektorat"
            elif articles_path.exists():
                json_path, quelle = articles_path, "articles (kein Lektorat)"
            else:
                log.warning("Stage 4: Artikel nicht gefunden: %s", article_id)
                continue
            targets.append((article_id, json_path, quelle))

    log.info("Stage 4 (TTS): %d Artikel zu vertonen → %s", len(targets), audio_dir)

    if dry_run:
        for article_id, json_path, quelle in targets:
            print(f"[dry-run] TTS: {article_id} ({quelle}) -> {audio_dir}")
        return

    ok, fehler = 0, 0
    for article_id, json_path, quelle in targets:
        log.info("TTS: %s (aus %s)", article_id, quelle)
        try:
            result = tts_produce.produce_article(
                json_path=json_path,
                out_dir=audio_dir,
                quiz=True,
                run_id=_RUN_ID,
            )
            # Präfix "lektorat_" aus WAV-Namen entfernen → article_id als Schlüssel
            for wav in list(audio_dir.glob(f"lektorat_{article_id}_*.wav")):
                clean = audio_dir / wav.name.replace("lektorat_", "", 1)
                wav.rename(clean)
            wav_count = (1 if result.get("article_wav") else 0) + len(result.get("quiz_wavs", []))
            errs = result.get("errors", [])
            if errs and not result.get("article_wav"):
                fehler += 1
                log.error("TTS FEHLER %s: %s", article_id, "; ".join(errs))
            else:
                ok += 1
                log.info("TTS OK: %s — %d WAVs, %.1f s%s",
                         article_id, wav_count, result.get("article_sec", 0.0),
                         f" (Teilfehler: {'; '.join(errs)})" if errs else "")
        except Exception as e:
            fehler += 1
            log.error("TTS FEHLER %s: %s", article_id, e)

    log.info("Stage 4 abgeschlossen: %d OK, %d Fehler", ok, fehler)


# ── Stage 5: UPLOAD (Artikel-JSON + Audio → R2) ───────────────────────────────

def stage5_upload(themen: list[str], stufen: list[int],
                  out_dir: Path, dry_run: bool = False) -> None:
    """Stage 5: Artikel-JSONs + Audio-WAVs nach R2 hochladen."""
    import subprocess, sys
    upload_script = Path(__file__).parent / "upload_articles.py"
    articles_dir = out_dir / "articles"
    audio_dir = out_dir / "audio"
    cmd = [
        sys.executable, str(upload_script),
        "--articles-dir", str(articles_dir),
        "--audio-dir", str(audio_dir),
    ]
    if dry_run:
        cmd.append("--dry-run")
    log.info("Stage 5 (Upload): %s", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        log.error("Stage 5: upload_articles.py mit Exit %d beendet", result.returncode)
    else:
        log.info("Stage 5: Upload abgeschlossen")


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
        "--stufen", nargs="+", type=int, choices=[2, 3], default=[2, 3],
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
    parser.add_argument(
        "--force-stage2", action="store_true", default=False,
        help="Stage 2 trotz Vision-Fehlschlägen in Stage 1 erzwingen",
    )
    parser.add_argument(
        "--gen-model",
        default=None,
        help="Generator-Modell überschreiben (z.B. gemini-2.5-flash). "
             "Nur für Tests — Produktion nutzt GEMINI_MODEL aus generate_grounded.py.",
    )
    parser.add_argument(
        "--pipeline", default=None, choices=["old", "new"],
        help="Generierungs-Pipeline: 'old' (Standard, bisheriges Verhalten) oder "
             "'new' (modulare Pass-Struktur). Fallback über Env WF_PIPELINE, sonst 'old'.",
    )
    args = parser.parse_args()

    global _RUN_ID, GEN_MODEL
    _RUN_ID = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Pipeline-Schalter (Phase 0): CLI > Env WF_PIPELINE > Default 'old'.
    # 'old' hält das Verhalten 100 % identisch; 'new' spricht die modulare
    # Pass-Struktur an (ab Phase 1). --pipeline wird von argparse (choices)
    # validiert; den Env-Wert prüfen wir hier separat.
    pipeline = args.pipeline or os.environ.get("WF_PIPELINE") or "old"
    pipeline = pipeline.strip().lower()
    if pipeline not in ("old", "new"):
        parser.error(f"WF_PIPELINE muss 'old' oder 'new' sein (nicht '{pipeline}')")
    if pipeline == "new":
        log.warning("⚠ Pipeline: NEU (modulare Pässe) — alter Pfad unberührt")

    if args.gen_model:
        import generate_grounded as _gg
        import generate_articles as _ga
        _gg.GEMINI_MODEL = args.gen_model
        _gg.KOMPASS_MODEL = args.gen_model
        # KOMPASS_MODEL_FALLBACK bleibt auf gemini-2.5-flash (sinnvoll)
        # Lemma-/BKS-Doppelbedeutungs-Check (eigene Modul-Konstante in generate_articles)
        _ga._FLASH_DOPPELBEDEUTUNG_MODEL = args.gen_model
        # GEN_MODEL ist ein Modul-Alias → hier neu binden
        GEN_MODEL = args.gen_model
        log.warning("⚠ gen-model Override: %s (Lemma+Kompass+Gen, nur für Tests!)", args.gen_model)

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

    log.info("Run-ID: %s | Themen: %d | Stufen: %s | Stage: %s | Pipeline: %s | dry-run: %s",
             _RUN_ID, len(themen_raw), stufen,
             args.stage if args.stage else "alle", pipeline, args.dry_run)

    # 10-min Client-Timeout: haengende Gemini-Calls (SDK hat sonst KEIN Timeout ->
    # ein Server-Stall blockiert endlos) brechen ab statt still zu haengen.
    client  = genai.Client(api_key=api_key,
                           http_options=types.HttpOptions(timeout=600_000))
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
        # Gate: Stage 1 darf keine Vision-Fehlschläge offen lassen (sonst fehlen Bilder)
        if not args.dry_run:
            failed_vision = [
                (t, len(v["images_vision_failed"]))
                for t, v in topics_data.items()
                if v.get("images_vision_failed")
            ]
            if failed_vision and not getattr(args, "force_stage2", False):
                log.error("Stage 2 BLOCKIERT: Vision-Fehlschläge in Stage 1:")
                for t, n in failed_vision:
                    log.error("  %s: %d Bild(er) ohne Verdict", t, n)
                log.error("Lösung: python scripts/vision_retry.py %s dann erneut starten.",
                          out_dir)
                sys.exit(2)
        articles = stage2_generierung(
            themen_raw, stufen, topics_data, out_dir, client, api_key, anthropic_key,
            dry_run=args.dry_run, pipeline=pipeline,
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
            dry_run=args.dry_run, pipeline=pipeline,
        )
        if args.stage == 3:
            return

    # ── Stage 4 ───────────────────────────────────────────────────────────────
    if run_all or args.stage == 4:
        log.info("\n" + "=" * 60)
        log.info("STAGE 4: TTS")
        log.info("=" * 60)
        stage4_tts(themen_raw, stufen, out_dir, dry_run=args.dry_run)

    # ── Stage 5: Upload (NICHT in run_all — explizit auslösen) ─────────────────
    if args.stage == 5:
        log.info("\n" + "=" * 60)
        log.info("STAGE 5: UPLOAD → R2")
        log.info("=" * 60)
        stage5_upload(themen_raw, stufen, out_dir, dry_run=args.dry_run)

    log.info("\n=== Batch-Run abgeschlossen (Run-ID: %s) ===", _RUN_ID)


if __name__ == "__main__":
    main()
