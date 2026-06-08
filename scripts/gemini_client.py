"""
gemini_client.py
Schlankes Modul für Gemini 2.5 Flash API-Aufrufe in der Wissensfreund-Pipeline.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash"
_DOTENV_PATH = Path(__file__).parent.parent / ".env"


def call_gemini(system_prompt: str, user_message: str) -> str:
    """Ruft Gemini 2.5 Flash auf und gibt den Antworttext zurück."""
    load_dotenv(_DOTENV_PATH)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY nicht gesetzt. "
            "Entweder in .env (GEMINI_API_KEY=...) oder als Umgebungsvariable."
        )

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.6,
            ),
        )
        return response.text
    except Exception as e:
        raise RuntimeError(f"Gemini API-Fehler ({GEMINI_MODEL}): {e}") from e
