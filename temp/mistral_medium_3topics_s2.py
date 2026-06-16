#!/usr/bin/env python3
"""
temp/mistral_medium_3topics_s2.py
mistral-medium-latest — S2-Generierung für 3 Topics: Elefant, Vulkan, Indianer

Datenquellen:
  Elefant:  articles/elefant_durchstich/stage1_checkpoint.json
  Vulkan:   articles/batch_output/stage1_checkpoint.json → topics["Vulkan"]
  Indianer: frischer Wikipedia-Fetch (kein Stage-1-Checkpoint vorhanden)

Analyse je Artikel:
  - finish_reason, Dauer, Token-Zahlen, Kosten
  - Wortzahl vs. Ziel (S2-Deckel 400 Wörter)
  - Schema-Abweichungen (box.type vs box_type, quiz-Wrapper, box-Key-Namen)
  - Quiz correct_key-Verteilung (A/B/C-Balance)
  - Qualitätsnotiz (Kindwelt-Brücken, Eröffnung Hook vs. Datendump)

Nutzung:
    python temp/mistral_medium_3topics_s2.py
"""

import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# UTF-8 stdout — verhindert charmap-Fehler auf Windows mit deutschen Sonderzeichen
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import cost_tracker  # noqa: E402

from mistralai.client.sdk import Mistral as MistralClient  # noqa: E402
from mistralai.client.models.responseformat import ResponseFormat  # noqa: E402

from generate_articles import fetch_wikipedia_text  # noqa: E402
from generate_grounded import (  # noqa: E402
    _split_grounded_user_message,
    wortziel_for,
    select_images_for_stufe,
    count_article_words,
    _box_lint,
)
from run_batch import _gen2_variable_suffix  # noqa: E402

MODEL_API      = "mistral-medium-latest"
MODEL_COST_KEY = "mistral-medium-3.5"
RUN_ID         = "mistral_medium_3topics_2026_06_16"

SYSTEM_PROMPT_PATH   = ROOT / "wissensfreund_generator_prompt_v3.23_production.md"
ELEFANT_CKPT         = ROOT / "articles" / "elefant_durchstich" / "stage1_checkpoint.json"
BATCH_CKPT           = ROOT / "articles" / "batch_output" / "stage1_checkpoint.json"
OUT_DIR              = ROOT / "articles" / "test_modelcompare2"

# Zwischen Topics warten — Rate-Limit-Schutz
TOPIC_WAIT_S   = 300   # 5 Minuten zwischen Topic-Calls
# Bei 429 warten und nochmal versuchen
MAX_RETRIES    = 5
RETRY_WAIT_429 = 900   # 15 Minuten — hourly token budget braucht Zeit zum Reset


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _strip_planung(text: str) -> str:
    return re.sub(r"<planung>.*?</planung>", "", text or "", flags=re.DOTALL).strip()


def _strip_md(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    return re.sub(r"\n?```$", "", text).strip()


def _parse_mistral_json(raw: str) -> tuple[dict | None, list]:
    """Wrapper-JSON {article, source_passages} oder plain article JSON."""
    cleaned = _strip_planung(_strip_md(raw))
    try:
        outer = json.loads(cleaned)
        if isinstance(outer, dict):
            if "article" in outer:
                return outer["article"], outer.get("source_passages", [])
            return outer, []
    except json.JSONDecodeError:
        pass
    return None, []


def _analyze_schema_deviations(article: dict) -> list[str]:
    """Prüft bekannte Mistral-Abweichungen vom WF-Schema."""
    issues = []
    seen_type_key = False
    seen_warnung   = False
    for sec in article.get("sections", []):
        for box in sec.get("boxes", []):
            if "type" in box and "box_type" not in box and not seen_type_key:
                issues.append(f"box.type statt box_type (z.B. '{box.get('type')}')")
                seen_type_key = True
            btype = box.get("box_type", box.get("type", ""))
            if btype == "warnung" and not seen_warnung:
                issues.append("box_type='warnung' statt 'warn'")
                seen_warnung = True
    quiz = article.get("quiz")
    if isinstance(quiz, dict) and "questions" in quiz:
        issues.append("quiz als {questions:[...]} statt flaches Array")
    elif isinstance(quiz, list) and quiz:
        for q in quiz:
            if not isinstance(q, dict):
                issues.append("quiz-Items kein dict")
                break
    return issues


def _quiz_key_distribution(article: dict) -> dict:
    """Zählt correct_key-Verteilung A/B/C im Quiz."""
    quiz = article.get("quiz", [])
    if isinstance(quiz, dict):
        quiz = quiz.get("questions", [])
    dist: dict[str, int] = {}
    for q in quiz:
        k = str(q.get("correct_key", "?")).upper()
        dist[k] = dist.get(k, 0) + 1
    return dist


def _quality_note(article: dict) -> str:
    """Einfache Qualitätsbewertung: Hook vs. Datendump, Kindwelt-Brücken."""
    sections = article.get("sections", [])
    if not sections:
        return "(kein Inhalt)"
    first_sec = sections[0]
    sentences = first_sec.get("sentences", [])
    first_text = " ".join(s.get("text", "") for s in sentences[:3]).lower()
    hook_signals = [
        "stell dir vor", "weißt du", "hast du gewusst", "kennst du",
        "magst du", "stell euch vor", "was wäre",
    ]
    bridge_signals = [
        "wie ein", "so groß wie", "genau wie", "zum beispiel",
        "stell dir vor", "als ob", "vergleich",
        # Kindwelt-Brücken
        "kühlschrank", "wasserflaschen", "ventilator", "haus", "schulbus",
        "auto", "fußball", "elefant", "hund", "garten",
    ]
    has_hook   = any(s in first_text for s in hook_signals)
    has_bridge = any(s in first_text for s in bridge_signals)
    notes = []
    if has_hook:
        notes.append("Eröffnung: Hook")
    else:
        notes.append("Eröffnung: Faktensatz (Datendump?)")
    if has_bridge:
        notes.append("Kindwelt-Brücken erkannt")
    else:
        notes.append("keine offensichtlichen Kindwelt-Brücken in Abschnitt 1")
    return " | ".join(notes)


def _section_preview(article: dict, max_sections: int = 2) -> str:
    lines = []
    for sec in article.get("sections", [])[:max_sections]:
        lines.append(f"\n  Abschnitt: {sec.get('title', '(kein Titel)')}")
        for s in sec.get("sentences", []):
            txt = s.get("text", "").strip()
            if txt:
                lines.append(f"    {txt}")
        for b in sec.get("boxes", []):
            btype = b.get("box_type", b.get("type", "box"))
            btxt  = b.get("text", "")[:200]
            lines.append(f"    [{btype.upper()}] {btxt}")
            if b.get("reveal_text"):
                lines.append(f"      → {b['reveal_text'][:200]}")
    return "\n".join(lines)


def _all_boxes_preview(article: dict) -> str:
    lines = []
    for sec in article.get("sections", []):
        for b in sec.get("boxes", []):
            btype = b.get("box_type", b.get("type", "?"))
            btxt  = b.get("text", "")[:200]
            lines.append(f"  [{btype.upper()}] (in '{sec.get('title','?')}'): {btxt}")
            if b.get("reveal_text"):
                lines.append(f"    → {b['reveal_text'][:200]}")
    return "\n".join(lines) if lines else "  (keine Boxen)"


def call_mistral_with_retry(
    client: MistralClient,
    system_prompt: str,
    user_msg: str,
    topic_label: str,
) -> tuple[object | None, float, str]:
    """
    Ruft mistral-medium-latest auf. Bei 429: wartet RETRY_WAIT_429 Sekunden, bis zu MAX_RETRIES.
    Gibt (response, elapsed, error_str) zurück.
    """
    t0 = time.monotonic()
    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.complete(
                model=MODEL_API,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
                response_format=ResponseFormat(type="json_object"),
                max_tokens=32768,
                temperature=0.6,
                timeout_ms=360_000,
            )
            elapsed = time.monotonic() - t0
            return resp, elapsed, ""
        except Exception as exc:
            err_str  = str(exc)
            is_429   = "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower()
            elapsed_ = time.monotonic() - t0
            last_err = err_str
            if is_429 and attempt < MAX_RETRIES:
                log.warning(
                    "  [%s] 429 Rate-Limit (V%d/%d) — warte %ds (~%.0f min) ...",
                    topic_label, attempt, MAX_RETRIES, RETRY_WAIT_429, RETRY_WAIT_429 / 60,
                )
                time.sleep(RETRY_WAIT_429)
            else:
                elapsed = time.monotonic() - t0
                return None, elapsed, err_str
    elapsed = time.monotonic() - t0
    return None, elapsed, last_err


def run_topic(
    client: MistralClient,
    system_prompt: str,
    job: dict,
    primary_text: str,
    companion_texts: dict,
    valid_companions: list,
    images_all: list,
    topic_idx: int,
) -> dict:
    """
    Baut User-Message, ruft Mistral auf, analysiert Ergebnis.
    Gibt result-Dict zurück.
    """
    thema = job["thema"]
    appeal = job.get("resolved_appeal", "medium")

    images_s2          = select_images_for_stufe(images_all, stufe=2, appeal=appeal)
    wmin, wmax, wz_src = wortziel_for(thema, 2)

    log.info(
        "  Bilder S2: %d (von %d gesamt) | Wortziel: %d–%d (%s)",
        len(images_s2), len(images_all), wmin, wmax, wz_src,
    )

    stable, _ = _split_grounded_user_message(
        job, primary_text, companion_texts, valid_companions, images_s2
    )
    variable  = _gen2_variable_suffix(job, wmax)
    full_msg  = stable + "\n" + variable

    log.info(
        "  User-Message: %d Zeichen (~%d Token gesch.)",
        len(full_msg), len(full_msg) // 4,
    )

    # Zwischen Topics warten (außer erstes)
    if topic_idx > 0:
        log.info("  Warte %ds zwischen Topics (Rate-Limit) ...", TOPIC_WAIT_S)
        time.sleep(TOPIC_WAIT_S)

    sep = "=" * 68
    print(f"\n{sep}")
    print(f"  THEMA: {thema} | S2 | {MODEL_API}")
    print(sep)

    resp, elapsed, err = call_mistral_with_retry(client, system_prompt, full_msg, thema)

    if resp is None:
        print(f"\n  FEHLER nach {elapsed:.1f}s: {err}")
        return {"error": err, "elapsed": elapsed, "thema": thema}

    choice        = resp.choices[0]
    finish_reason = str(choice.finish_reason)
    raw_text      = choice.message.content or ""
    actual_model  = getattr(resp, "model", MODEL_API)

    usage   = getattr(resp, "usage", None)
    in_tok  = int(getattr(usage, "prompt_tokens",     0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)

    print(f"  API-Modell:    {actual_model}")
    print(f"  finish_reason: {finish_reason}")
    print(f"  Dauer:         {elapsed:.1f}s")
    print(f"  Tokens:        input={in_tok:,}  output={out_tok:,}")

    cost_entry = cost_tracker.track(
        run_id=RUN_ID, thema=thema, stufe="S2",
        schritt="article_gen", modell=MODEL_COST_KEY,
        input_tok=in_tok, output_tok=out_tok,
    )
    print(f"  Kosten:        ${cost_entry['kosten_usd']:.6f}")

    article, source_passages = _parse_mistral_json(raw_text)

    if article is None:
        print(f"\n  JSON-PARSE FEHLER — kein Artikel extrahiert")
        print(f"  Raw (erste 500 Zeichen):\n{raw_text[:500]}")
        return {
            "error": "json_parse_failed", "raw": raw_text[:2000],
            "elapsed": elapsed, "in_tok": in_tok, "out_tok": out_tok,
            "kosten_usd": cost_entry["kosten_usd"], "thema": thema,
        }

    wc        = count_article_words(article)
    sections  = article.get("sections", [])
    all_boxes = [b for s in sections for b in s.get("boxes", [])]
    quiz      = article.get("quiz", [])
    box_lint  = _box_lint(article)
    schema_v  = article.get("schema_version", "?")
    deviations = _analyze_schema_deviations(article)
    key_dist   = _quiz_key_distribution(article)
    qual_note  = _quality_note(article)
    finish_ok  = "stop" in finish_reason.lower()

    wc_status = (
        "✅ GETROFFEN" if wmin <= wc <= round(wmax * 1.05)
        else ("⚠️ ZU KURZ" if wc < wmin else "⚠️ ZU LANG")
    )

    print(f"\n  ERGEBNIS:")
    print(f"    schema_version:   {schema_v}")
    print(f"    Wortzahl:         {wc} / Ziel {wmin}–{wmax}  {wc_status}")
    print(f"    finish_reason:    {finish_reason}  {'✅' if finish_ok else '⚠️ TRUNCATED?'}")
    print(f"    Sektionen:        {len(sections)}")
    print(f"    Boxen:            {len(all_boxes)}  ({[b.get('box_type', b.get('type','?')) for b in all_boxes]})")
    box_count = len(quiz.get("questions", []) if isinstance(quiz, dict) else quiz) if quiz else 0
    print(f"    Quiz-Fragen:      {box_count}")
    print(f"    source_passages:  {len(source_passages)}")
    print(f"    Box-Lint:         {'✅ OK' if not box_lint else f'⚠️ {box_lint}'}")

    print(f"\n  SCHEMA-ABWEICHUNGEN:")
    if deviations:
        for d in deviations:
            print(f"    ⚠️  {d}")
    else:
        print(f"    ✅ keine bekannten Abweichungen")

    print(f"\n  QUIZ correct_key-Verteilung: {key_dist}")
    all_same = len(key_dist) == 1 and sum(key_dist.values()) > 1
    if all_same:
        print(f"    ⚠️  Alle Antworten zeigen auf denselben Key!")
    else:
        print(f"    ✅ Verteilung variiert")

    print(f"\n  QUALITÄTSNOTIZ: {qual_note}")

    print(f"\n  ERSTE 2 SEKTIONEN:")
    print(_section_preview(article, max_sections=2))

    print(f"\n  ALLE BOXEN:")
    print(_all_boxes_preview(article))

    if source_passages:
        print(f"\n  SOURCE_PASSAGES (erste 3):")
        for sp in source_passages[:3]:
            print(f"    claim:   {str(sp.get('claim',''))[:100]}")
            print(f"    source:  {sp.get('source','')}")
            print(f"    passage: {str(sp.get('passage',''))[:120]}")
            print()

    return {
        "article":         article,
        "source_passages": source_passages,
        "thema":           thema,
        "wc":              wc,
        "wmin":            wmin,
        "wmax":            wmax,
        "finish_reason":   finish_reason,
        "finish_ok":       finish_ok,
        "in_tok":          in_tok,
        "out_tok":         out_tok,
        "kosten_usd":      cost_entry["kosten_usd"],
        "elapsed":         elapsed,
        "box_lint":        box_lint,
        "deviations":      deviations,
        "key_dist":        key_dist,
        "quality_note":    qual_note,
        "schema_version":  schema_v,
    }


def main() -> None:
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    if not mistral_key:
        print("\nFEHLER: MISTRAL_API_KEY nicht gesetzt.")
        sys.exit(1)

    if not SYSTEM_PROMPT_PATH.exists():
        print(f"FEHLER: System-Prompt fehlt: {SYSTEM_PROMPT_PATH}")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    log.info("System-Prompt: %d Zeichen", len(system_prompt))

    # ── Topic-Daten laden ─────────────────────────────────────────────────────

    # Elefant
    ckpt_elefant = json.loads(ELEFANT_CKPT.read_text(encoding="utf-8"))
    elefant_data = ckpt_elefant["topics"]["Elefant"]

    # Vulkan
    log.info("Lade Vulkan aus batch_output stage1_checkpoint ...")
    ckpt_batch   = json.loads(BATCH_CKPT.read_text(encoding="utf-8"))
    vulkan_data  = ckpt_batch["topics"]["Vulkan"]

    # Indianer — frischer Wikipedia-Fetch
    log.info("Hole Indianer-Wikipedia-Text fresh ...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Wissensfreund-Test/1.0 (az@expansionssupport.de)"})
    indianer_primary = fetch_wikipedia_text(session, "Indianer")
    log.info("Indianer primary_text: %d Zeichen", len(indianer_primary))

    # ── Job-Dicts ─────────────────────────────────────────────────────────────

    topics = [
        {
            "job": {
                "article_id":        "elefant_l2",
                "thema":             "Elefant",
                "primaer_wikipedia": elefant_data.get("resolved_title", "Elefanten"),
                "title":             "Elefant",
                "age_level":         2,
                "topic_interest":    "high",
                "sensibel":          elefant_data.get("sensibel", False),
                "pattern":           "living_being",
                "category_top":      "tiere",
                "category_sub":      "saeugetiere",
                "resolved_appeal":   elefant_data.get("appeal", "high"),
                "framing_note":      elefant_data.get("framing_note", ""),
                "lemma_flags":       elefant_data.get("lemma_flags", []),
            },
            "primary_text":    elefant_data["primary_text"],
            "companion_texts": elefant_data["companion_texts"],
            "valid_companions":elefant_data.get("valid_companions", []),
            "images_all":      elefant_data.get("images", []),
        },
        {
            "job": {
                "article_id":        "vulkan_l2",
                "thema":             "Vulkan",
                "primaer_wikipedia": vulkan_data.get("resolved_title", "Vulkan"),
                "title":             "Vulkan",
                "age_level":         2,
                "topic_interest":    "high",
                "sensibel":          vulkan_data.get("sensibel", False),
                "pattern":           "tech_science",
                "category_top":      "natur",
                "category_sub":      "geologie",
                "resolved_appeal":   vulkan_data.get("appeal", "high"),
                "framing_note":      vulkan_data.get("framing_note", ""),
                "lemma_flags":       vulkan_data.get("lemma_flags", []),
            },
            "primary_text":    vulkan_data["primary_text"],
            "companion_texts": vulkan_data["companion_texts"],
            "valid_companions":vulkan_data.get("valid_companions", []),
            "images_all":      vulkan_data.get("images", []),
        },
        {
            "job": {
                "article_id":        "indianer_l2",
                "thema":             "Indianer",
                "primaer_wikipedia": "Indianer",
                "title":             "Indianer",
                "age_level":         2,
                "topic_interest":    "medium",
                "sensibel":          True,
                "pattern":           "history_person",
                "category_top":      "geschichte",
                "category_sub":      "voelker",
                "resolved_appeal":   "medium",
                "framing_note":      "",
                "lemma_flags":       [],
            },
            "primary_text":    indianer_primary,
            "companion_texts": {},
            "valid_companions": [],
            "images_all":      [],
        },
    ]

    # ── Hauptschleife ─────────────────────────────────────────────────────────
    client  = MistralClient(api_key=mistral_key)
    results = {}

    for idx, t in enumerate(topics):
        thema = t["job"]["thema"]
        log.info("=== %s (S2, %s) ===", thema, MODEL_API)
        r = run_topic(
            client=client,
            system_prompt=system_prompt,
            job=t["job"],
            primary_text=t["primary_text"],
            companion_texts=t["companion_texts"],
            valid_companions=t["valid_companions"],
            images_all=t["images_all"],
            topic_idx=idx,
        )
        results[thema] = r

    # ── Finale Zusammenfassung ────────────────────────────────────────────────
    sep = "=" * 68
    print(f"\n{sep}")
    print(f"  ZUSAMMENFASSUNG — mistral-medium-latest, 3 Topics S2")
    print(sep)

    total_cost = 0.0
    for thema in ["Elefant", "Vulkan", "Indianer"]:
        r = results.get(thema, {})
        if "error" in r:
            print(f"\n  {thema}: FEHLER — {str(r['error'])[:80]}")
            continue
        wc     = r.get("wc", 0)
        wmax   = r.get("wmax", 400)
        wmin   = r.get("wmin", 200)
        fin    = r.get("finish_reason", "?")
        cost   = r.get("kosten_usd", 0.0)
        dur    = r.get("elapsed", 0.0)
        devs   = r.get("deviations", [])
        kdist  = r.get("key_dist", {})
        qnote  = r.get("quality_note", "")
        total_cost += cost
        wst = "✅" if wmin <= wc <= round(wmax * 1.05) else ("⚠️ kurz" if wc < wmin else "⚠️ lang")
        print(f"\n  {thema}")
        print(f"    Wörter:      {wc}/{wmax}  {wst}")
        print(f"    finish:      {fin}  {'✅' if 'stop' in fin.lower() else '⚠️'}")
        print(f"    Kosten:      ${cost:.6f}  |  Dauer: {dur:.1f}s")
        print(f"    in/out Tok:  {r.get('in_tok',0):,} / {r.get('out_tok',0):,}")
        print(f"    Schema-Dev:  {len(devs)} — {devs or 'keine'}")
        print(f"    Quiz-Keys:   {kdist}")
        print(f"    Qualität:    {qnote}")

    print(f"\n  Gesamtkosten: ${total_cost:.6f}")

    # Artikel-JSONs speichern
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for thema, r in results.items():
        art = r.get("article")
        if art:
            fname = f"mistral-medium-3.5_{thema.lower()}_s2.json"
            (OUT_DIR / fname).write_text(
                json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info("Gespeichert: %s", fname)

    print(f"\n  Artikel-JSONs: {OUT_DIR}")
    print(f"  Cost-Log: {cost_tracker.LOG_PATH}")
    print()


if __name__ == "__main__":
    main()
