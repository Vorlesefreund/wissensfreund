#!/usr/bin/env python3
"""
temp/mistral_test_elefant_s2.py
Modell-Vergleich Elefant S2: mistral-large-3 vs. mistral-medium-3.5 vs. gemini-3.5-flash

Fairer Vergleich: identischer System-Prompt v3.23b, identischer User-Message-Aufbau,
identische Wikipedia-Quelltexte aus dem Stage-1-Checkpoint (articles/elefant_durchstich).
Nur das Modell variiert.

Nutzung:
    set MISTRAL_API_KEY=sk-...  (Windows) | export MISTRAL_API_KEY=sk-... (Bash)
    python temp/mistral_test_elefant_s2.py
"""

import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

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

from generate_grounded import (  # noqa: E402
    _split_grounded_user_message,
    wortziel_for,
    select_images_for_stufe,
    count_article_words,
    _box_lint,
)
from run_batch import _gen2_variable_suffix, _parse_gen2_response  # noqa: E402
import gemini_client  # noqa: E402
from google.genai import types  # noqa: E402

SYSTEM_PROMPT_PATH = ROOT / "wissensfreund_generator_prompt_v3.23_production.md"
CHECKPOINT_PATH    = ROOT / "articles" / "elefant_durchstich" / "stage1_checkpoint.json"
RUN_ID             = "mistral_test_2026_06_16"

# (api_model_id, cost_tracker_key)
MISTRAL_MODELS = [
    ("mistral-large-latest",  "mistral-large-3"),
    ("mistral-medium-latest", "mistral-medium-3.5"),
]


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
                art = outer["article"]
                return art, outer.get("source_passages", [])
            return outer, []
    except json.JSONDecodeError:
        pass
    return None, []


def _section_preview(article: dict, max_sections: int = 2) -> str:
    lines = []
    for sec in article.get("sections", [])[:max_sections]:
        lines.append(f"\n  Abschnitt: {sec.get('title', '(kein Titel)')}")
        for s in sec.get("sentences", []):
            txt = s.get("text", "").strip()
            if txt:
                lines.append(f"    {txt}")
        for b in sec.get("boxes", []):
            btype = b.get("box_type", "box")
            btxt  = b.get("text", "")[:200]
            lines.append(f"    [{btype.upper()}] {btxt}")
            if b.get("reveal_text"):
                lines.append(f"      → {b['reveal_text'][:200]}")
    return "\n".join(lines)


def _all_boxes_preview(article: dict) -> str:
    lines = []
    for sec in article.get("sections", []):
        for b in sec.get("boxes", []):
            btype = b.get("box_type", "box")
            btxt  = b.get("text", "")[:200]
            lines.append(f"  [{btype.upper()}] (in '{sec.get('title','?')}'): {btxt}")
            if b.get("reveal_text"):
                lines.append(f"    → {b['reveal_text'][:200]}")
    return "\n".join(lines) if lines else "  (keine Boxen)"


def main() -> None:
    # ── Voraussetzungen prüfen ─────────────────────────────────────────────────
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    if not mistral_key:
        print("\nFEHLER: MISTRAL_API_KEY nicht gesetzt.")
        print("  Windows:  set MISTRAL_API_KEY=sk-...")
        print("  Bash/PS:  $env:MISTRAL_API_KEY = 'sk-...'")
        sys.exit(1)

    if not SYSTEM_PROMPT_PATH.exists():
        print(f"FEHLER: System-Prompt fehlt: {SYSTEM_PROMPT_PATH}")
        sys.exit(1)
    if not CHECKPOINT_PATH.exists():
        print(f"FEHLER: Stage-1-Checkpoint fehlt: {CHECKPOINT_PATH}")
        sys.exit(1)

    # ── System-Prompt + Checkpoint laden ──────────────────────────────────────
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    log.info("System-Prompt: %d Zeichen", len(system_prompt))

    checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    elefant    = checkpoint["topics"]["Elefant"]

    primary_text     = elefant["primary_text"]
    companion_texts  = elefant["companion_texts"]
    valid_companions = elefant.get("valid_companions", [])
    images_all       = elefant.get("images", [])
    appeal           = elefant.get("appeal", "high")
    resolved_title   = elefant.get("resolved_title", "Elefanten")

    log.info(
        "Checkpoint: primary=%d ch, %d companions, %d Bilder, appeal=%s",
        len(primary_text), len(valid_companions), len(images_all), appeal,
    )

    # ── Job-Dict für Elefant S2 ────────────────────────────────────────────────
    job = {
        "article_id":        "elefant_l2",
        "thema":             "Elefant",
        "primaer_wikipedia": resolved_title,
        "title":             "Elefant",
        "age_level":         2,
        "topic_interest":    "high",
        "sensibel":          elefant.get("sensibel", False),
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "saeugetiere",
        "resolved_appeal":   appeal,
        "framing_note":      elefant.get("framing_note", ""),
        "lemma_flags":       elefant.get("lemma_flags", []),
    }

    # ── User-Message aufbauen (identisch zum Gemini-Produktionspfad) ───────────
    images_s2 = select_images_for_stufe(images_all, stufe=2, appeal=appeal)
    wmin, wmax, wz_src = wortziel_for("Elefant", 2)
    log.info("Wortziel S2: %d–%d Wörter (Quelle: %s)", wmin, wmax, wz_src)
    log.info("Bilder für S2: %d (von %d gesamt)", len(images_s2), len(images_all))

    # Stable prefix via _split_grounded_user_message, dann gen2-Suffix anhängen
    stable, _ = _split_grounded_user_message(
        job, primary_text, companion_texts, valid_companions, images_s2
    )
    variable   = _gen2_variable_suffix(job, wmax)
    full_msg   = stable + "\n" + variable

    log.info(
        "User-Message: %d Zeichen, ~%d Token geschätzt",
        len(full_msg), len(full_msg) // 4,
    )

    results: dict[str, dict] = {}

    # ══════════════════════════════════════════════════════════════════════════
    # MISTRAL-CALLS
    # ══════════════════════════════════════════════════════════════════════════
    mistral_client = MistralClient(api_key=mistral_key)

    for idx_model, (api_model, cost_model) in enumerate(MISTRAL_MODELS):
        sep = "=" * 68
        print(f"\n{sep}")
        print(f"  MODELL: {api_model}  (cost-key: {cost_model})")
        print(sep)

        # Zwischen den Mistral-Calls warten — nach großem Large-Call Rate-Limit-Schutz
        if idx_model > 0:
            wait_between = 300  # 5 Minuten nach dem Large-Call
            log.info("  Warte %ds vor nächstem Mistral-Call (Rate-Limit nach Large-Call) ...", wait_between)
            time.sleep(wait_between)

        # Retry-Schleife + äußeres try-except zusammen, damit raise sauber gefangen wird
        MAX_RETRIES = 3
        RETRY_WAITS = [120, 240, 480]  # Sekunden bei 429 — längere Wartezeiten für Token-Budget
        t0 = time.monotonic()
        try:
            resp = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = mistral_client.chat.complete(
                        model=api_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": full_msg},
                        ],
                        response_format=ResponseFormat(type="json_object"),
                        max_tokens=32768,
                        temperature=0.6,
                        timeout_ms=360_000,  # 6 Minuten — großzügig für 59K Input-Token
                    )
                    break  # Erfolg
                except Exception as exc_inner:
                    err_str = str(exc_inner)
                    is_429 = "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower()
                    if is_429 and attempt < MAX_RETRIES:
                        wait_s = RETRY_WAITS[attempt - 1]
                        log.warning("  429 Rate-Limit (V%d/%d) — warte %ds ...", attempt, MAX_RETRIES, wait_s)
                        time.sleep(wait_s)
                    else:
                        raise
            if resp is None:
                raise RuntimeError("Keine Response erhalten (alle Retries erschöpft)")
            elapsed = time.monotonic() - t0

            choice        = resp.choices[0]
            finish_reason = str(choice.finish_reason)
            raw_text      = choice.message.content or ""
            actual_model  = getattr(resp, "model", api_model)

            usage    = getattr(resp, "usage", None)
            in_tok   = int(getattr(usage, "prompt_tokens",     0) or 0)
            out_tok  = int(getattr(usage, "completion_tokens", 0) or 0)

            print(f"  API-Modell (laut Response): {actual_model}")
            print(f"  finish_reason:  {finish_reason}")
            print(f"  Dauer:          {elapsed:.1f}s")
            print(f"  Tokens:         input={in_tok:,}  output={out_tok:,}")

            cost_entry = cost_tracker.track(
                run_id=RUN_ID, thema="Elefant", stufe="S2",
                schritt="article_gen", modell=cost_model,
                input_tok=in_tok, output_tok=out_tok,
            )
            print(f"  Kosten:         ${cost_entry['kosten_usd']:.6f}")

            # JSON parsen
            article, source_passages = _parse_mistral_json(raw_text)

            if article is None:
                print(f"\n  JSON-PARSE FEHLER — kein Artikel extrahiert")
                print(f"  Raw (erste 500 Zeichen):\n{raw_text[:500]}")
                results[api_model] = {"error": "json_parse_failed", "raw": raw_text[:2000]}
                continue

            wc       = count_article_words(article)
            sections = article.get("sections", [])
            all_boxes = [b for s in sections for b in s.get("boxes", [])]
            quiz     = article.get("quiz", [])
            box_lint = _box_lint(article)
            schema_v = article.get("schema_version", "?")

            wc_status = (
                "✅ GETROFFEN" if wmin <= wc <= round(wmax * 1.05)
                else ("⚠️ ZU KURZ" if wc < wmin else "⚠️ ZU LANG")
            )
            finish_ok = "STOP" in finish_reason.upper() or finish_reason.lower() == "stop"

            print(f"\n  ERGEBNIS-ÜBERSICHT:")
            print(f"    schema_version:  {schema_v}")
            print(f"    Wortzahl:        {wc}  (Ziel {wmin}–{wmax})  {wc_status}")
            print(f"    finish_reason:   {finish_reason}  {'✅' if finish_ok else '⚠️ TRUNCATED?'}")
            print(f"    Sektionen:       {len(sections)}")
            print(f"    Boxen:           {len(all_boxes)}  ({[b.get('box_type','?') for b in all_boxes]})")
            print(f"    Quiz-Fragen:     {len(quiz)}")
            print(f"    source_passages: {len(source_passages)}")
            print(f"    Box-Lint:        {'✅ OK' if not box_lint else f'⚠️ {box_lint}'}")

            print(f"\n  ARTIKEL-VOLLTEXT — erste 2 Sektionen:")
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

            results[api_model] = {
                "article":         article,
                "source_passages": source_passages,
                "wc": wc, "wmin": wmin, "wmax": wmax,
                "finish_reason":   finish_reason,
                "in_tok": in_tok, "out_tok": out_tok,
                "kosten_usd":      cost_entry["kosten_usd"],
                "elapsed":         elapsed,
                "box_lint":        box_lint,
                "schema_version":  schema_v,
                "finish_ok":       finish_ok,
            }

        except Exception as exc:
            elapsed = time.monotonic() - t0
            print(f"\n  FEHLER nach {elapsed:.1f}s: {exc}")
            results[api_model] = {"error": str(exc)}

    # ══════════════════════════════════════════════════════════════════════════
    # GEMINI-VERGLEICH (Sync, mit Retry/Backoff)
    # ══════════════════════════════════════════════════════════════════════════
    sep = "=" * 68
    print(f"\n{sep}")
    print("  GEMINI-3.5-FLASH (Sync-Vergleich, max. 5 Retries mit Backoff)")
    print(sep)

    gemini_model = "gemini-3.5-flash"
    thinking_cfg = types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM)
    t0 = time.monotonic()
    try:
        raw_g = gemini_client.call_gemini(
            system_prompt=system_prompt,
            user_message=full_msg,
            model=gemini_model,
            thinking_config=thinking_cfg,
            call_name="elefant_s2_mistral_cmp",
        )
        elapsed_g = time.monotonic() - t0
        usage_g   = gemini_client._last_usage
        in_tok_g  = usage_g.get("input_tok", 0)
        out_tok_g = usage_g.get("output_tok", 0)
        tho_tok_g = usage_g.get("thoughts_tok", 0)

        article_g, sp_g = _parse_gen2_response(raw_g)
        wc_g = count_article_words(article_g) if article_g else 0
        box_lint_g = _box_lint(article_g) if article_g else "kein Artikel"

        cost_g = cost_tracker.track(
            run_id=RUN_ID, thema="Elefant", stufe="S2",
            schritt="article_gen", modell=gemini_model,
            input_tok=in_tok_g, output_tok=out_tok_g,
            thoughts_tok=tho_tok_g,
        )
        print(f"  finish_reason:   STOP (OK)")
        print(f"  Dauer:           {elapsed_g:.1f}s")
        print(f"  Tokens:          input={in_tok_g:,}  output={out_tok_g:,}  thoughts={tho_tok_g:,}")
        print(f"  Kosten:          ${cost_g['kosten_usd']:.6f}")

        if article_g:
            wc_status_g = (
                "✅ GETROFFEN" if wmin <= wc_g <= round(wmax * 1.05)
                else ("⚠️ ZU KURZ" if wc_g < wmin else "⚠️ ZU LANG")
            )
            all_boxes_g = [b for s in article_g.get("sections",[]) for b in s.get("boxes",[])]
            print(f"\n  ERGEBNIS-ÜBERSICHT:")
            print(f"    Wortzahl:        {wc_g}  (Ziel {wmin}–{wmax})  {wc_status_g}")
            print(f"    Sektionen:       {len(article_g.get('sections',[]))}")
            print(f"    Boxen:           {len(all_boxes_g)}  ({[b.get('box_type','?') for b in all_boxes_g]})")
            print(f"    Quiz-Fragen:     {len(article_g.get('quiz',[]))}")
            print(f"    source_passages: {len(sp_g)}")
            print(f"    Box-Lint:        {'✅ OK' if not box_lint_g else f'⚠️ {box_lint_g}'}")

            print(f"\n  ARTIKEL-VOLLTEXT — erste 2 Sektionen:")
            print(_section_preview(article_g, max_sections=2))
            print(f"\n  ALLE BOXEN:")
            print(_all_boxes_preview(article_g))

        results["gemini-3.5-flash"] = {
            "article": article_g,
            "source_passages": sp_g,
            "wc": wc_g, "wmin": wmin, "wmax": wmax,
            "finish_reason": "stop",
            "in_tok": in_tok_g, "out_tok": out_tok_g,
            "kosten_usd": cost_g["kosten_usd"],
            "elapsed": elapsed_g,
            "box_lint": box_lint_g,
        }

    except Exception as exc:
        elapsed_g = time.monotonic() - t0
        err_str = str(exc)
        if "503" in err_str or "unavailable" in err_str.lower():
            print(f"  Gemini 503 — Modell weiterhin nicht erreichbar ({elapsed_g:.0f}s).")
            print("  Gemini-Vergleich: später nachholen (temp/_sync_test_s2.py).")
        else:
            print(f"  Gemini Fehler nach {elapsed_g:.1f}s: {exc}")
        results["gemini-3.5-flash"] = {"error": err_str}

    # ══════════════════════════════════════════════════════════════════════════
    # FINALE VERGLEICHSTABELLE
    # ══════════════════════════════════════════════════════════════════════════
    sep = "=" * 68
    print(f"\n{sep}")
    print("  VERGLEICH: ALLE DREI MODELLE — Elefant S2")
    print(f"  Wortziel: {wmin}–{wmax} Wörter")
    print(sep)

    rows = [
        ("mistral-large-latest",  "mistral-large-3"),
        ("mistral-medium-latest", "mistral-medium-3.5"),
        ("gemini-3.5-flash",      "gemini-3.5-flash"),
    ]
    for api_key, label in rows:
        r = results.get(api_key, {})
        if "error" in r:
            print(f"\n  {label:<22}  FEHLER: {r['error'][:60]}")
            continue
        wc   = r.get("wc", 0)
        wmx  = r.get("wmax", wmax)
        wmn  = r.get("wmin", wmin)
        wst  = "✅" if wmn <= wc <= round(wmx * 1.05) else ("⚠️ kurz" if wc < wmn else "⚠️ lang")
        bl   = "✅" if not r.get("box_lint") else "⚠️"
        fin  = r.get("finish_reason", "?")
        fin_icon = "✅" if "stop" in str(fin).lower() else "⚠️"
        print(f"\n  {label}")
        print(f"    Wortzahl:     {wc}/{wmx}  {wst}")
        print(f"    finish:       {fin}  {fin_icon}")
        print(f"    Box-Lint:     {bl}")
        print(f"    source_pass.: {len(r.get('source_passages', []))}")
        print(f"    Tokens in/out:{r.get('in_tok',0):,} / {r.get('out_tok',0):,}")
        print(f"    Kosten:       ${r.get('kosten_usd', 0):.6f}")
        print(f"    Dauer:        {r.get('elapsed', 0):.1f}s")

    # Artikel als JSON speichern für spätere Analyse
    out_dir = ROOT / "articles" / "test_modelcompare2"
    out_dir.mkdir(parents=True, exist_ok=True)
    for api_key, label in rows:
        r = results.get(api_key, {})
        art = r.get("article")
        if art:
            fname = label.replace("/", "_").replace(".", "_") + "_elefant_s2.json"
            (out_dir / fname).write_text(
                json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info("Artikel gespeichert: %s", fname)

    print(f"\n  Artikel-JSONs gespeichert in: {out_dir}")
    print(f"  Cost-Log: {cost_tracker.LOG_PATH}")
    print()


if __name__ == "__main__":
    main()
