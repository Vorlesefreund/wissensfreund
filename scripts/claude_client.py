#!/usr/bin/env python3
"""claude_client.py — anbieter-neutraler JSON-Call für Anthropic (Weg B, Baustein 1).

call_claude_json() liefert garantiert valides JSON via forced tool-use: das Modell
MUSS das "emit"-Tool mit dem übergebenen json_schema aufrufen; das Tool-Input ist
ein strukturiertes Objekt (kein zu parsender Text → kein „…"-Quote-Defekt möglich).

Analog zu gemini_client.call_gemini. Liest ANTHROPIC_API_KEY aus der Umgebung
(bzw. .env via python-dotenv, falls vorhanden).
"""
import base64
import logging
import time
from pathlib import Path

import anthropic

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5"
_client = None
_last_usage: dict = {}


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()   # liest ANTHROPIC_API_KEY aus env
    return _client


def call_claude_json(system_prompt, user_message, json_schema, *,
                     model=None, max_tokens=4096, thinking_budget=0,
                     image_bytes=None, image_media_type="image/jpeg",
                     call_name="", max_attempts=4, stream=False,
                     cached_prefix=None, temperature=None):
    """Anbieter-neutraler JSON-Call via forced tool-use. Gibt das validierte dict zurück.

    json_schema: JSON-Schema-Dict (input_schema des emit-Tools).
    thinking_budget>0: extended thinking aktiv. Da forced tool_choice NICHT mit
      thinking kombinierbar ist, wird dann tool_choice={"type":"auto"} genutzt und
      der tool_use-Block aus der Antwort gefischt (das emit-Tool ist das einzige).
    stream=True: nutzt messages.stream() statt messages.create(). Nötig bei großem
      max_tokens (>~8k), weil das SDK nicht-streamende Requests, die >10 Min dauern
      könnten, mit ValueError ablehnt. Für Echo-lastige Pässe (Trim/Box-Repair).
    """
    global _last_usage
    client = _get_client()
    effective_model = model or _DEFAULT_MODEL

    tools = [{
        "name": "emit",
        "description": "Gib das Ergebnis als strukturiertes JSON-Objekt zurück.",
        "input_schema": json_schema,
    }]

    content = []
    if image_bytes is not None:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": image_media_type, "data": b64},
        })
    # cached_prefix: großer, über mehrere Calls stabiler Block (z.B. Quelltext) →
    # eigener cache_control-Block (Anthropic Prompt-Caching, 5-min TTL).
    if cached_prefix:
        content.append({"type": "text", "text": cached_prefix,
                        "cache_control": {"type": "ephemeral"}})
    content.append({"type": "text", "text": user_message})

    kwargs = dict(
        model=effective_model,
        max_tokens=max_tokens,
        system=system_prompt,
        tools=tools,
        messages=[{"role": "user", "content": content}],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature

    if thinking_budget > 0:
        # thinking ist NICHT mit forced tool_choice kombinierbar → "auto"
        # (emit ist das einzige Tool; wir fischen den tool_use-Block heraus).
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        kwargs["tool_choice"] = {"type": "auto"}
        # max_tokens muss > thinking_budget sein
        if max_tokens <= thinking_budget:
            kwargs["max_tokens"] = thinking_budget + max_tokens
    else:
        # ohne thinking: forced tool-use erzwingt den emit-Aufruf
        kwargs["tool_choice"] = {"type": "tool", "name": "emit"}

    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            if stream:
                with client.messages.stream(**kwargs) as s:
                    resp = s.get_final_message()
            else:
                resp = client.messages.create(**kwargs)
            _last_usage = {
                "input_tokens":  resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }
            if getattr(resp, "stop_reason", None) == "max_tokens":
                raise ValueError(
                    f"Antwort am max_tokens-Cap abgeschnitten ({call_name}, "
                    f"max_tokens={kwargs['max_tokens']})"
                )
            for block in resp.content:
                if block.type == "tool_use" and block.name == "emit":
                    return block.input
            raise ValueError(
                f"Kein emit-tool_use-Block in Antwort ({call_name}); "
                f"stop_reason={getattr(resp, 'stop_reason', '?')}"
            )
        except anthropic.APIStatusError as e:
            last_err = e
            if e.status_code in (429, 503, 529) and attempt < max_attempts:
                wait = min(10 * (2 ** (attempt - 1)), 160)
                log.warning("  Claude %s %d (V%d/%d) — warte %ds",
                            call_name, e.status_code, attempt, max_attempts, wait)
                time.sleep(wait)
            else:
                raise
    raise last_err


def call_claude_text(system_prompt, user_message, *,
                     model=None, max_tokens=16000, thinking_budget=0,
                     effort=None, call_name="", max_attempts=4, temperature=None):
    """Freies Text-Ergebnis (KEIN forced tool-use) — für die Artikel-GENERIERUNG.

    Anders als call_claude_json (das ein Schema erzwingt) gibt diese Funktion den
    rohen Modell-Text zurück; der Aufrufer parst ihn mit parse_article_json
    (robust gegen <planung>-Prefix, Markdown-Fences und den „…"-ASCII-Defekt).
    Nutzt Streaming, weil die Hörspiel-/Erzähltext-Ausgabe groß ist (>10-Min-Schutz
    des SDK bei nicht-streamenden Langläufern).
    """
    global _last_usage
    client = _get_client()
    effective_model = model or _DEFAULT_MODEL

    kwargs = dict(
        model=effective_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    if thinking_budget > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        if max_tokens <= thinking_budget:
            kwargs["max_tokens"] = thinking_budget + max_tokens
    # Claude-5-Familie: adaptives Thinking wird über output_config.effort gesteuert
    # (nicht über thinking.budget). Niedriger Effort spart Output-Budget, damit die
    # große Artikel-JSON nicht am max_tokens-Cap abbricht.
    if effort is not None:
        kwargs["output_config"] = {"effort": effort}

    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            with client.messages.stream(**kwargs) as s:
                resp = s.get_final_message()
            _last_usage = {
                "input_tokens":  resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }
            if getattr(resp, "stop_reason", None) == "max_tokens":
                raise ValueError(
                    f"Antwort am max_tokens-Cap abgeschnitten ({call_name}, "
                    f"max_tokens={kwargs['max_tokens']})"
                )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            if not text.strip():
                raise ValueError(f"Leerer Text-Block in Antwort ({call_name})")
            return text
        except anthropic.APIStatusError as e:
            last_err = e
            if e.status_code in (429, 503, 529) and attempt < max_attempts:
                wait = min(10 * (2 ** (attempt - 1)), 160)
                log.warning("  Claude %s %d (V%d/%d) — warte %ds",
                            call_name, e.status_code, attempt, max_attempts, wait)
                time.sleep(wait)
            else:
                raise
    raise last_err


def get_last_usage():
    return dict(_last_usage)
