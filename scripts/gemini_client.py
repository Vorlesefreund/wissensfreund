"""
gemini_client.py
Schlankes Modul für Gemini API-Aufrufe in der Wissensfreund-Pipeline.
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

log = logging.getLogger(__name__)

GEMINI_MODEL        = "gemini-2.5-flash"
RETRY_ATTEMPTS      = 3
RETRY_WAIT_SECONDS  = 60
_DOTENV_PATH        = Path(__file__).parent.parent / ".env"


def call_gemini(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    thinking_config: types.ThinkingConfig | None = None,
) -> str:
    """Ruft Gemini auf und gibt den Antworttext zurück. Modell + ThinkingConfig wählbar."""
    load_dotenv(_DOTENV_PATH)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY nicht gesetzt. "
            "Entweder in .env (GEMINI_API_KEY=...) oder als Umgebungsvariable."
        )

    effective_model   = model or GEMINI_MODEL
    effective_thinking = thinking_config or types.ThinkingConfig(thinking_budget=8192)
    client = genai.Client(api_key=api_key)

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=effective_model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.6,
                    thinking_config=effective_thinking,
                ),
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
                log.warning(
                    "Gemini Rate-Limit (Versuch %d/%d) — warte %ds ...",
                    attempt, RETRY_ATTEMPTS, RETRY_WAIT_SECONDS,
                )
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            raise RuntimeError(f"Gemini API-Fehler ({effective_model}): {e}") from e

    raise RuntimeError(f"Gemini API: alle {RETRY_ATTEMPTS} Versuche ausgeschöpft")
