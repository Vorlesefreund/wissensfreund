#!/usr/bin/env python3
"""
Synchroner Stage-2-Diagnosetest: Elefant S2.

Zwei Ziele:
  1. DIAGNOSE: Rohe Response zeigen (finish_reason, candidates, usage_metadata)
     um "leere Batch-Antwort"-Problem zu isolieren.
  2. A/B-VERGLEICH: ThinkingLevel.MEDIUM vs. kein Thinking (gleiche Quelltexte,
     gleicher Prompt) — Artikelqualitaet, Wortzahl, Dauer, Token-Verbrauch.

Aufruf:
  python temp/_sync_test_s2.py          → Variante A (MEDIUM, Diagnose)
  python temp/_sync_test_s2.py --ab     → A + B (MEDIUM vs. kein Thinking)
"""
import argparse, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from google import genai
from google.genai import types

from generate_grounded import (
    _split_grounded_user_message,
    _make_thinking_config,
    SYSTEM_PROMPT_PATH,
    GEMINI_MODEL,
    select_images_for_stufe,
    wortziel_for,
)
from run_batch import _stage2_job, _gen2_variable_suffix

CHECKPOINT = ROOT / "articles" / "elefant_durchstich" / "stage1_checkpoint.json"
STUFE      = 2
WAITS      = [10, 20, 40, 80, 160]


def _build_inputs():
    cp    = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    data  = cp["topics"]["Elefant"]
    job   = _stage2_job("Elefant", data, "elefant", STUFE)

    images_stufe = select_images_for_stufe(
        data.get("images", []), STUFE, job.get("resolved_appeal", "medium"))
    wmin, wmax, _ = wortziel_for("Elefant", STUFE)
    stable, _ = _split_grounded_user_message(
        job, data["primary_text"],
        data.get("companion_texts", {}),
        data.get("valid_companions", []),
        images_stufe,
    )
    variable = _gen2_variable_suffix(job, wmax)
    full_msg = stable + "\n" + variable

    print(f"[INPUT] {len(images_stufe)} Bilder | wmax={wmax} | "
          f"msg={len(full_msg)} Zeichen (~{len(full_msg)//4} Tokens)")
    return full_msg, wmax


def _call(client, full_msg, cfg_obj, label):
    """Einzelner synchroner Call mit Retry. Gibt (response, dauer_s) zurueck."""
    for attempt, wait in enumerate(WAITS, start=1):
        t0 = time.time()
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[types.Content(role="user",
                                        parts=[types.Part.from_text(text=full_msg)])],
                config=cfg_obj,
            )
            return resp, time.time() - t0
        except Exception as e:
            code = str(e)[:100]
            is_503 = "503" in code or "unavailable" in code.lower()
            is_429 = "429" in code or "quota" in code.lower()
            if (is_503 or is_429) and attempt < len(WAITS):
                print(f"  [{label}] Versuch {attempt}/5: {code[:60]} -> warte {wait}s ...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"[{label}] Alle 5 Versuche fehlgeschlagen")


def _show_response(resp, dauer, label, wmax):
    print(f"\n{'='*70}")
    print(f"RAW RESPONSE — {label}")
    print(f"{'='*70}")

    cands = resp.candidates or []
    print(f"candidates count : {len(cands)}")
    print(f"dauer            : {dauer:.1f}s")

    for i, c in enumerate(cands):
        print(f"\n  candidate[{i}]:")
        print(f"    finish_reason  : {c.finish_reason}")
        if getattr(c, "finish_message", None):
            print(f"    finish_message : {c.finish_message}")
        content = c.content
        if content and content.parts:
            out_parts   = [p for p in content.parts if not getattr(p, "thought", False)]
            think_parts = [p for p in content.parts if getattr(p, "thought", False)]
            out_text    = "".join(getattr(p, "text", "") or "" for p in out_parts)
            think_text  = "".join(getattr(p, "text", "") or "" for p in think_parts)
            print(f"    parts count    : {len(content.parts)}")
            print(f"    output text len: {len(out_text)}")
            print(f"    thinking len   : {len(think_text)}")
            if out_text:
                print(f"    first 500 chars: {repr(out_text[:500])}")
                # Wortzahl-Schaetzung
                wc = len(out_text.split())
                print(f"    ~Woerter (roh) : {wc} (Ziel: <={wmax})")
            else:
                print(f"    output text    : LEER")
        else:
            print(f"    content/parts  : LEER")
        if getattr(c, "safety_ratings", None):
            print(f"    safety_ratings :")
            for sr in c.safety_ratings:
                print(f"      {sr.category}: {sr.probability}")

    u = resp.usage_metadata
    if u:
        print(f"\nusage_metadata:")
        print(f"  prompt_token_count        : {getattr(u, 'prompt_token_count', '?')}")
        print(f"  candidates_token_count    : {getattr(u, 'candidates_token_count', '?')}")
        print(f"  thoughts_token_count      : {getattr(u, 'thoughts_token_count', '?')}")
        print(f"  total_token_count         : {getattr(u, 'total_token_count', '?')}")
    else:
        print("\nusage_metadata: FEHLT")

    pf = getattr(resp, "prompt_feedback", None)
    if pf:
        print(f"\nprompt_feedback: {pf}")


def _save_article(resp, label):
    """Speichert den Artikel-Text (falls vorhanden) fuer spaetere Qualitaetsbewertung."""
    cands = resp.candidates or []
    if not cands:
        return
    content = cands[0].content
    if not content:
        return
    out_parts = [p for p in content.parts if not getattr(p, "thought", False)]
    out_text  = "".join(getattr(p, "text", "") or "" for p in out_parts)
    if not out_text:
        return
    out_dir  = ROOT / "articles" / "test_thinking_ab"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug     = label.lower().replace(" ", "_").replace("/", "_")
    out_path = out_dir / f"elefant_s2_{slug}.txt"
    out_path.write_text(out_text, encoding="utf-8")
    print(f"  -> Artikel gespeichert: {out_path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ab", action="store_true",
                        help="A/B-Vergleich: MEDIUM vs. kein Thinking")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[ERR] Kein GEMINI_API_KEY/GOOGLE_API_KEY in .env")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    full_msg, wmax = _build_inputs()
    system_prompt  = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    # Variante A: ThinkingLevel.MEDIUM (Produktionskonfiguration)
    cfg_a = types.GenerateContentConfig(
        system_instruction=system_prompt,
        thinking_config=_make_thinking_config(GEMINI_MODEL, budget_for_2_5=8192),
        max_output_tokens=32768,
    )
    print(f"\n[A] gemini-3.5-flash + ThinkingLevel.MEDIUM + max_output_tokens=32768")
    resp_a, dur_a = _call(client, full_msg, cfg_a, "A-MEDIUM")
    _show_response(resp_a, dur_a, "A — MEDIUM", wmax)
    _save_article(resp_a, "medium")

    if not args.ab:
        return

    # Variante B: kein Thinking
    cfg_b = types.GenerateContentConfig(
        system_instruction=system_prompt,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.NONE)
        if hasattr(types.ThinkingLevel, "NONE")
        else types.ThinkingConfig(thinking_budget=0),
        max_output_tokens=32768,
    )
    print(f"\n[B] gemini-3.5-flash + KEIN Thinking + max_output_tokens=32768")
    resp_b, dur_b = _call(client, full_msg, cfg_b, "B-KEIN-THINKING")
    _show_response(resp_b, dur_b, "B — kein Thinking", wmax)
    _save_article(resp_b, "no_thinking")

    # Vergleichszusammenfassung
    print(f"\n{'='*70}")
    print("A/B-VERGLEICH ZUSAMMENFASSUNG")
    print(f"{'='*70}")

    def _extract(resp):
        cands = resp.candidates or []
        if not cands or not cands[0].content:
            return 0, 0, 0, 0
        out_parts = [p for p in cands[0].content.parts if not getattr(p, "thought", False)]
        out_text  = "".join(getattr(p, "text", "") or "" for p in out_parts)
        u = resp.usage_metadata
        pt = getattr(u, "prompt_token_count", 0) or 0 if u else 0
        ct = getattr(u, "candidates_token_count", 0) or 0 if u else 0
        tt = getattr(u, "thoughts_token_count", 0) or 0 if u else 0
        wc = len(out_text.split())
        return pt, ct, tt, wc

    pt_a, ct_a, tt_a, wc_a = _extract(resp_a)
    pt_b, ct_b, tt_b, wc_b = _extract(resp_b)

    print(f"{'':30} {'A (MEDIUM)':>14} {'B (kein Thinking)':>18}")
    print(f"{'Dauer':30} {dur_a:>13.1f}s {dur_b:>17.1f}s")
    print(f"{'prompt_tokens':30} {pt_a:>14} {pt_b:>18}")
    print(f"{'candidates_tokens':30} {ct_a:>14} {ct_b:>18}")
    print(f"{'thoughts_tokens':30} {tt_a:>14} {tt_b:>18}")
    print(f"{'~Woerter (roh)':30} {wc_a:>14} {wc_b:>18}")
    print(f"{'Wortziel':30} {'<=' + str(wmax):>14} {'<=' + str(wmax):>18}")
    print(f"\nArtikel fuer Qualitaetsbewertung: articles/test_thinking_ab/")


if __name__ == "__main__":
    main()
