"""
gemini_client.py
Schlankes Modul für Gemini API-Aufrufe in der Wissensfreund-Pipeline.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

log = logging.getLogger(__name__)

GEMINI_MODEL        = "gemini-2.5-flash"
RETRY_ATTEMPTS      = 6
_DOTENV_PATH        = Path(__file__).parent.parent / ".env"


def _retry_wait(attempt: int) -> int:
    """Exponentieller Backoff: 60 / 120 / 240 / 300 / 300 s."""
    return min(60 * (2 ** (attempt - 1)), 300)


def call_gemini(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    thinking_config: types.ThinkingConfig | None = None,
    response_mime_type: str | None = None,
    response_schema: Any = None,
    cached_content: str | None = None,
) -> str:
    """Ruft Gemini auf und gibt den Antworttext zurück.

    Optionale Parameter:
      - response_mime_type: z.B. 'application/json' für Structured Output
      - response_schema:    Schema-Objekt (genai types.Schema oder dict)
      - cached_content:     Cache-Name aus client.caches.create (Gemini Context Cache)
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
    client = genai.Client(api_key=api_key)

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            cfg = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.6,
                thinking_config=effective_thinking,
            )
            if response_mime_type:
                cfg.response_mime_type = response_mime_type
            if response_schema is not None:
                cfg.response_schema = response_schema
            if cached_content:
                cfg.cached_content = cached_content

            response = client.models.generate_content(
                model=effective_model,
                contents=user_message,
                config=cfg,
            )
            # usage_metadata auswerten
            um = getattr(response, "usage_metadata", None)
            if um:
                prompt_tok    = getattr(um, "prompt_token_count", "?")
                cand_tok      = getattr(um, "candidates_token_count", "?")
                cached_tok    = getattr(um, "cached_content_token_count", 0) or 0
                thoughts_tok  = getattr(um, "thoughts_token_count", 0) or 0
                log.info(
                    "  usage: prompt=%s cached=%d thoughts=%d output=%s",
                    prompt_tok, cached_tok, thoughts_tok, cand_tok,
                )

            # Thinking-Mode kann response.text=None liefern → Parts direkt auslesen
            text = response.text
            if text is None:
                parts = []
                for cand in getattr(response, "candidates", []):
                    for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                        if not getattr(part, "thought", False) and getattr(part, "text", None):
                            parts.append(part.text)
                text = "".join(parts) or None
            if not text:
                candidates = getattr(response, "candidates", [])
                finish_reason = (
                    str(getattr(candidates[0], "finish_reason", "UNKNOWN"))
                    if candidates else "NO_CANDIDATES"
                )
                raise RuntimeError(
                    f"Gemini gab keinen Text zurück (finish_reason: {finish_reason})"
                )
            return text
        except Exception as e:
            err_str = str(e)
            is_rate_limit = (
                "429" in err_str
                or "503" in err_str
                or "quota" in err_str.lower()
                or "resource exhausted" in err_str.lower()
                or "rate" in err_str.lower()
                or "unavailable" in err_str.lower()
            )
            if is_rate_limit and attempt < RETRY_ATTEMPTS:
                wait = _retry_wait(attempt)
                log.warning(
                    "Gemini Rate-Limit (Versuch %d/%d) — warte %ds ...",
                    attempt, RETRY_ATTEMPTS, wait,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini API-Fehler ({effective_model}): {e}") from e

    raise RuntimeError(f"Gemini API: alle {RETRY_ATTEMPTS} Versuche ausgeschöpft")
