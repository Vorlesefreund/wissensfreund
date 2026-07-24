"""
gemini_client.py
Schlankes Modul für Gemini API-Aufrufe in der Wissensfreund-Pipeline.

Retry-Strategie (synchrone Calls):
  503 UNAVAILABLE / 429 RESOURCE_EXHAUSTED → exponentielles Backoff + Jitter
  400 / 404 (echte API-Fehler) → sofort raise, kein Retry
"""

import logging
import os
import random
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

log = logging.getLogger(__name__)

# Letzter Token-Verbrauch — wird nach jedem erfolgreichen call_gemini() befüllt.
_last_usage: dict = {}

GEMINI_MODEL   = "gemini-2.5-flash"
RETRY_ATTEMPTS = 5
_RETRY_WAITS   = [10, 20, 40, 80, 160]   # Sekunden; je + random Jitter 0–5s

_DOTENV_PATH   = Path(__file__).parent.parent / ".env"


def is_billing_depleted(err_str: str) -> bool:
    """True, wenn der Fehler „Prepaid-Guthaben aufgebraucht" meldet.

    Das ist zwar ein 429 RESOURCE_EXHAUSTED, aber KEIN transienter Last-Fehler:
    Retry ist zwecklos, bis der User im AI Studio Guthaben auflaedt. Deshalb
    NICHT wiederholen, sondern sofort mit klarer Meldung scheitern (sonst
    verheizt der Nachtlauf Stunden gegen eine Abrechnungswand)."""
    s = err_str.lower()
    return (
        "prepayment credits" in s
        or "credits are depleted" in s
        or "billing#prepay" in s
        or ("billing" in s and "depleted" in s)
    )


def _is_retriable_error(err_str: str) -> bool:
    """True für transiente Fehler (503, 429, Timeout/Deadline, Verbindungsabbruch) → Retry.
    False für echte API-Fehler (400 Bad Request, 404 Not Found) → sofort raise.
    """
    s = err_str.lower()
    # Sofort-Fehler: nie retrien
    if (
        "400 " in err_str
        or "invalid_argument" in s
        or "404 " in err_str
        or "not_found" in s
        or ("not found" in s and "model" in s)
        or is_billing_depleted(err_str)   # Guthaben leer → Retry sinnlos, sofort raise
    ):
        return False
    return (
        "503" in err_str
        or "429" in err_str
        or "quota" in s
        or "resource exhausted" in s
        or "unavailable" in s
        or "overloaded" in s              # Modell-Ueberlastung
        or "rate" in s
        or "timeout" in s or "timed out" in s or "deadline" in s   # Client-Timeout / Server-Deadline (Hang-Schutz)
        or "connection" in s or "reset" in s                        # abgebrochene Verbindung
        or "499" in err_str or "cancelled" in s or "canceled" in s  # Client-Timeout -> 499 CANCELLED -> Retry (nicht droppen)
        or "finish_reason" in err_str     # unvollständige Antwort → Retry
        or "unvollst" in s                # eigene RuntimeError-Meldung
    )


def call_gemini(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    thinking_config: types.ThinkingConfig | None = None,
    response_mime_type: str | None = None,
    response_schema: Any = None,
    cached_content: str | None = None,
    call_name: str = "",
    max_output_tokens: int | None = None,
) -> str:
    global _last_usage
    """Ruft Gemini synchron auf und gibt den Antworttext zurück.

    Bei 503/429: exponentielles Backoff mit Jitter (5 Versuche, 10→160s).
    Bei 400/404: sofort raise (kein Retry).
    """
    load_dotenv(_DOTENV_PATH)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY nicht gesetzt. "
            "Entweder in .env (GEMINI_API_KEY=...) oder als Umgebungsvariable."
        )

    effective_model    = model or GEMINI_MODEL
    effective_thinking = thinking_config or types.ThinkingConfig(thinking_budget=8192)
    label              = f"[{call_name}] " if call_name else ""
    # 10-min Client-Timeout: haengende Gemini-Calls (SDK hat sonst KEIN Timeout ->
    # Server-Stall blockiert endlos) brechen ab -> _is_retriable_error faengt sie -> Retry.
    client             = genai.Client(api_key=api_key,
                                      http_options=types.HttpOptions(timeout=600_000))

    last_exc: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            cfg = types.GenerateContentConfig(
                temperature=0.6,
                thinking_config=effective_thinking,
            )
            if not cached_content:
                cfg.system_instruction = system_prompt
            else:
                cfg.cached_content = cached_content
            if response_mime_type:
                cfg.response_mime_type = response_mime_type
            if response_schema is not None:
                cfg.response_schema = response_schema
            if max_output_tokens is not None:
                cfg.max_output_tokens = max_output_tokens

            response = client.models.generate_content(
                model=effective_model,
                contents=user_message,
                config=cfg,
            )

            um = getattr(response, "usage_metadata", None)
            if um:
                prompt_tok   = getattr(um, "prompt_token_count", 0) or 0
                cand_tok     = getattr(um, "candidates_token_count", 0) or 0
                cached_tok   = getattr(um, "cached_content_token_count", 0) or 0
                thoughts_tok = getattr(um, "thoughts_token_count", 0) or 0
                log.info(
                    "  %susage: prompt=%s cached=%d thoughts=%d output=%s",
                    label, prompt_tok, cached_tok, thoughts_tok, cand_tok,
                )
                _last_usage = {
                    "input_tok":    int(prompt_tok),
                    "output_tok":   int(cand_tok),
                    "cached_tok":   int(cached_tok),
                    "thoughts_tok": int(thoughts_tok),
                }
            else:
                _last_usage = {}

            candidates = getattr(response, "candidates", [])
            text = response.text
            if text is None:
                parts = []
                for cand in candidates:
                    for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                        if not getattr(part, "thought", False) and getattr(part, "text", None):
                            parts.append(part.text)
                text = "".join(parts) or None

            if candidates:
                fr = str(getattr(candidates[0], "finish_reason", "") or "")
                if fr and "STOP" not in fr:
                    raise RuntimeError(
                        f"Antwort unvollstaendig (finish_reason={fr})"
                    )

            if not text:
                fr_str = (
                    str(getattr(candidates[0], "finish_reason", "UNKNOWN"))
                    if candidates else "NO_CANDIDATES"
                )
                raise RuntimeError(
                    f"Gemini gab keinen Text zurueck (finish_reason: {fr_str})"
                )
            return text

        except Exception as e:
            err_str = str(e)

            if not _is_retriable_error(err_str):
                raise RuntimeError(
                    f"Gemini API-Fehler {label}(Modell={effective_model}): {e}"
                ) from e

            last_exc = e
            if attempt < RETRY_ATTEMPTS:
                base_wait = _RETRY_WAITS[attempt - 1]
                jitter    = random.uniform(0, 5)
                wait      = base_wait + jitter
                log.warning(
                    "503/429 bei %s%s, Versuch %d/%d, warte %.0fs ...",
                    label, effective_model, attempt, RETRY_ATTEMPTS, wait,
                )
                time.sleep(wait)
            else:
                log.error(
                    "503/429 bei %s%s, Versuch %d/%d — alle Versuche ausgeschoepft.",
                    label, effective_model, attempt, RETRY_ATTEMPTS,
                )

    raise RuntimeError(
        f"Gemini {label}(Modell={effective_model}): alle {RETRY_ATTEMPTS} Versuche "
        f"fehlgeschlagen. Letzter Fehler: {last_exc}"
    )
