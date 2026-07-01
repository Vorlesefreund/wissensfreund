#!/usr/bin/env python3
"""
flash_monitor.py — Verfügbarkeits-Messpunkt für gemini-3.5-flash (Produktions-Queue).

Zweck: Über mehrere Tage die tageszeitliche Verfügbarkeit des Generierungs-Modells
messen, um das 503-arme Frühfenster und realistische Timeout-/Paketgrößen
datenbasiert zu bestimmen.

Betrieb: EIN Messpunkt pro Aufruf, dann Exit. KEIN Intervall-Loop — die Wiederholung
macht der Windows Task Scheduler. Trifft denselben Modell-String (GEN_MODEL) und
denselben Batch-Einreichungsweg (client.batches.create) wie der Produktions-Generator
in run_batch.py, damit die Messung die echte Queue misst.

Budget-Transparenz:
    Requests pro Messpunkt: 4 (Wegwerf-Antworten, werden NICHT gespeichert).
    Bei 19 Messpunkten/Tag: 4 × 19 = 76 Requests/Tag.
    Jeder Request: ~1500 Zeichen Füll-Kontext + triviale Aufgabe ("Zähle 1..20").

Seiteneffekte: schreibt AUSSCHLIESSLICH flash_monitor.jsonl (Repo-Root, append-only).
Fasst KEINE Checkpoints, kein articles/, keinen Katalog an.

Exit-Code: 0 nur bei result=="succeeded"; sonst 1 (stalled/error → maschinell erkennbar).
Garantie: Es wird IMMER genau eine flash_monitor.jsonl-Zeile geschrieben — auch im
Fehlerfall (try/except/finally um den Kern). Ein Messpunkt ohne Zeile ist der einzige
inakzeptable Ausgang.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# ── Konstanten ────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
MONITOR_PATH = ROOT / "flash_monitor.jsonl"
load_dotenv(ROOT / ".env")

N_REQUESTS         = 4       # Wegwerf-Requests pro Messpunkt
POLL_SECS          = 30      # Poll-Intervall
TIMEOUT_MIN        = 20      # Messpunkt-Timeout (dann Cancel + "stalled")
SUBMIT_MAX_RETRIES = 4       # Batch-Create-Retries bei 503/5xx
FILLER_CHARS       = 1500    # realistische Prompt-Länge (Queue-Aufnahme-Test)


# ── Status-Zeile schreiben (append-only, abbruch-robust) ─────────────────────
def _write_line(rec: dict) -> None:
    with open(MONITOR_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── genai-Batch-State (analog run_batch._state_str) ──────────────────────────
def _state_str(job) -> str:
    s = getattr(job, "state", None)
    if s is None:
        return "unknown"
    return s.value if hasattr(s, "value") else str(s)


def _build_requests(types_mod, gen_model: str) -> list:
    """4 InlinedRequests: realistischer Füll-Kontext + triviale Aufgabe."""
    filler = ("Dies ist ein Fülltext zur realistischen Auslastung der Modell-Queue. "
              * 40)[:FILLER_CHARS]
    reqs = []
    for i in range(N_REQUESTS):
        prompt = (f"{filler}\n\nIgnoriere den obigen Text vollständig. "
                  f"Deine einzige Aufgabe: Zähle von 1 bis 20, nur die Zahlen.")
        contents = types_mod.Content(
            role="user",
            parts=[types_mod.Part.from_text(text=prompt)],
        )
        cfg = types_mod.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=256,
        )
        reqs.append(types_mod.InlinedRequest(
            contents=contents, config=cfg, metadata={"key": f"probe_{i}"},
        ))
    return reqs


def _is_503(exc: Exception) -> bool:
    txt = f"{getattr(exc, 'code', '')} {exc}".lower()
    return "503" in txt or "unavailable" in txt


# ── Messkern ──────────────────────────────────────────────────────────────────
def measure(rec: dict) -> None:
    """Führt EINEN Messpunkt aus und aktualisiert rec in-place."""
    from google import genai
    from google.genai import types
    from generate_grounded import GEMINI_MODEL as GEN_MODEL  # exakt Produktions-Modell

    rec["model"] = GEN_MODEL
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        rec.update(result="error_other", error_category="no_api_key",
                   detail="GEMINI_API_KEY nicht gesetzt")
        return

    client = genai.Client(api_key=api_key)
    reqs   = _build_requests(types, GEN_MODEL)

    # — Einreichen mit begrenztem 503-Retry (Retries zählen) —
    submit_503 = 0
    batch = None
    for att in range(1, SUBMIT_MAX_RETRIES + 1):
        try:
            batch = client.batches.create(model=GEN_MODEL, src=reqs)
            break
        except Exception as e:
            if _is_503(e) and att < SUBMIT_MAX_RETRIES:
                submit_503 += 1
                time.sleep(min(10 * 2 ** (att - 1), 80))
                continue
            rec.update(result=("error_503" if _is_503(e) else "error_other"),
                       error_category=("submit_503_exhausted" if _is_503(e) else "submit_error"),
                       submit_503_retries=submit_503, detail=str(e)[:300])
            return
    rec["submit_503_retries"] = submit_503

    # — Pollen mit eigenem Timeout + Auto-Cancel (wie run_batch) —
    t0       = time.monotonic()
    deadline = t0 + TIMEOUT_MIN * 60
    DONE = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED",
            "JOB_STATE_PARTIALLY_SUCCEEDED", "JOB_STATE_EXPIRED"}
    while True:
        job   = client.batches.get(name=batch.name)
        state = _state_str(job)
        if state in DONE:
            if state in ("JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"):
                rec.update(result="succeeded",
                           seconds_to_succeeded=round(time.monotonic() - t0, 1),
                           final_state=state)
            else:
                rec.update(result="error_other", error_category="batch_failed",
                           final_state=state, detail=f"Batch-Endzustand {state}")
            return
        if time.monotonic() > deadline:
            try:
                client.batches.cancel(name=batch.name)
                cancel_note = "gecancelt"
            except Exception as ce:
                cancel_note = f"Cancel-Fehler: {ce}"
            rec.update(result="stalled", error_category="poll_timeout",
                       final_state=state,
                       detail=f"nach {TIMEOUT_MIN}min nicht fertig ({cancel_note})")
            return
        time.sleep(POLL_SECS)


# ── Einstiegspunkt: garantiert EINE Zeile, dann Exit ─────────────────────────
def main() -> int:
    now_utc = datetime.now(timezone.utc)
    rec = {
        "ts_utc":    now_utc.isoformat(),
        "ts_berlin": now_utc.astimezone().isoformat(),  # lokale TZ = Europe/Berlin
        "result":    "error_other",                     # Default bis überschrieben
        "error_category": "uncaught",
    }
    try:
        measure(rec)
    except Exception as e:
        rec.update(result="error_other", error_category="uncaught_exception",
                   detail=str(e)[:300])
    finally:
        try:
            _write_line(rec)
        except Exception as we:
            # Letzter Ausweg: auf stderr, damit der Scheduler-Log etwas sieht.
            print(f"FATAL: flash_monitor.jsonl nicht schreibbar: {we}", file=sys.stderr)
    return 0 if rec.get("result") == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
