#!/usr/bin/env python3
"""
tts_produce.py  v1  (2026-06-24)
Wissensfreund — TTS-Orchestrator (Stage 4): vertont fertige Canonical-JSON-Artikel.

- Artikel-Audio (immer): tts_compose.compose() → EINE WAV pro Artikel.
- Quiz-Audio (--quiz):    intro / qN / richtig_N / falsch_N / abschluss als Einzelclips.

Kein separater Tagging-Schritt — compose() liefert den fertigen Vorlesetext.
TTS-Aufruf (Stimme, Modell, Scene-Instruction, PCM→WAV, Retry) 1:1 wie tts_audio_compare.py.

Stimme:  Iapetus
Modell:  gemini-3.1-flash-tts-preview
Scene-Instructions S1/S2/S3 exakt wie in CLAUDE_CHAT_NOTIZEN.md ("TTS — Festgelegte Parameter").

Nutzung (CLI):
  python tts_produce.py <artikel.json> [--out-dir DIR] [--quiz]

Importierbar:
  produce_article(json_path, out_dir, quiz=False) -> dict
"""

import os
import sys
import json
import wave
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

# compose() + cost_tracker liegen im Repo-Root (neben dieser Datei)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_compose import compose

try:
    import cost_tracker
except Exception as _e:  # pragma: no cover
    cost_tracker = None
    print(f"WARN: cost_tracker nicht importierbar ({_e}) — Tracking deaktiviert.")

TTS_MODEL   = "gemini-3.1-flash-tts-preview"
VOICE_NAME  = "Iapetus"
SAMPLE_RATE = 24000  # Gemini liefert PCM 24 kHz mono 16-bit

# Exakt die Texte aus CLAUDE_CHAT_NOTIZEN.md / tts_audio_compare.py
SCENE = {
    "S1": ("Read aloud as a good-natured professor sharing something with a young child, "
           "as if sitting together quietly. Calm, warm, a little slower than normal. "
           "Friendly but understated — let the wonder come from the words, not loud emphasis."),
    "S2": ("Read aloud as a relaxed, good-natured professor sharing a story with a child. "
           "Conversational and unhurried, as if chatting at the kitchen table. "
           "Understated, warm, natural — no dramatic emphasis."),
    "S3": ("Read aloud as a calm, knowledgeable professor explaining something to an older child. "
           "Conversational and even, quietly engaged. "
           "Natural pace, minimal emphasis — clear and grounded, never dramatic."),
}


def load_env():
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _stufe_from_meta(article: dict) -> str:
    level = article.get("meta", {}).get("age_level", 2)
    return f"S{max(1, min(3, int(level)))}"


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or SAMPLE_RATE
        return frames / float(rate)


def _opts_line(options: list[dict]) -> str:
    """'A: Magma. B: Lava. C: Wasser.'"""
    return " ".join(f"{o.get('key')}: {(o.get('text') or '').rstrip('.')}."
                    for o in options)


def synth(client, text: str, stufe: str, out_wav: Path) -> bool:
    """TTS-Call 1:1 wie tts_audio_compare.py.synth_tts — Scene voran, PCM→WAV, 3× Retry."""
    from google.genai import types
    prompt = f"{SCENE[stufe]}\n\n{text}"
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=TTS_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=VOICE_NAME))),
                ),
            )
            audio_b = resp.candidates[0].content.parts[0].inline_data.data
            # Gemini liefert rohes PCM 24kHz mono → in WAV verpacken
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_b)
            return True
        except Exception as e:
            print(f"      TTS-Retry {attempt+1}: {str(e)[:60]}")
            time.sleep(5)
    return False


def _track(thema: str, stufe: str, audio_sec: float, run_id: str):
    """tts_audio_sec je Datei an cost_tracker melden (Stage-4-Kontrakt)."""
    if cost_tracker is None:
        return
    try:
        cost_tracker.track(
            run_id=run_id, thema=thema, stufe=stufe,
            schritt="tts", modell=TTS_MODEL, tts_audio_sec=audio_sec,
        )
    except Exception as e:
        print(f"      WARN cost_tracker.track: {str(e)[:80]}")


def _build_quiz_clips(article: dict) -> list[tuple[str, str]]:
    """Liefert [(suffix, text), ...] für die Quiz-Einzelclips."""
    quiz = article.get("quiz") or {}
    questions = quiz.get("questions") or []
    clips: list[tuple[str, str]] = []
    if not questions:
        return clips

    for n, q in enumerate(questions, start=1):
        qtext = (q.get("text") or "").strip()
        opts = _opts_line(q.get("options") or [])

        # a) Frage 1 steckt im Intro; b) Frage n>=2 als eigener Clip
        if n == 1:
            clips.append((
                "quiz_intro",
                f"Jetzt habe ich noch ein paar Fragen für dich!\n"
                f"Frage eins: {qtext}\n{opts}",
            ))
        else:
            clips.append((f"quiz_q{n}", f"Frage {n}: {qtext}\n{opts}"))

        # c) richtig-Clip
        clips.append((f"quiz_richtig_{n}", "Richtig! [pause=0.3] Sehr gut."))

        # d) falsch-Clip (enthält korrekte Antwort, key vorangestellt)
        correct_key = q.get("correct_key")
        correct_text = ""
        for o in (q.get("options") or []):
            if o.get("key") == correct_key:
                correct_text = (o.get("text") or "").strip()
                break
        clips.append((
            f"quiz_falsch_{n}",
            f"Diese Antwort war leider falsch. [pause=0.3] "
            f"Die richtige Antwort war {correct_key}: {correct_text}.",
        ))

    # e) Quiz-Abschluss
    clips.append((
        "quiz_abschluss",
        "Super! Du hast alle Fragen beantwortet. [pause=0.5] Bis zum nächsten Mal!",
    ))
    return clips


def produce_article(json_path, out_dir, quiz: bool = False,
                    client=None, run_id: str | None = None) -> dict:
    """
    Vertont einen Artikel: eine Artikel-WAV (immer) + optional Quiz-Clips.

    Rückgabe: dict mit erzeugten Dateien, Längen und etwaigen Fehlern.
    """
    json_path = Path(json_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    article = json.loads(json_path.read_text(encoding="utf-8"))
    meta = article.get("meta", {}) or {}
    thema = meta.get("title", json_path.stem)
    stufe = _stufe_from_meta(article)
    stem = json_path.stem

    if run_id is None:
        run_id = "tts_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if client is None:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    result = {
        "json": str(json_path), "thema": thema, "stufe": stufe,
        "article_wav": None, "article_sec": 0.0,
        "quiz_wavs": [], "errors": [],
    }

    # ── Artikel-Audio (immer) ──────────────────────────────────────────────
    text = compose(article)  # Stufe wird intern aus meta.age_level abgeleitet
    if not text.strip():
        result["errors"].append("compose() lieferte leeren Text")
        return result

    art_wav = out_dir / f"{stem}_artikel.wav"
    print(f"  [{stem}] {stufe} Artikel-Audio …", flush=True)
    if synth(client, text, stufe, art_wav):
        sec = _wav_seconds(art_wav)
        result["article_wav"] = art_wav.name
        result["article_sec"] = round(sec, 1)
        _track(thema, stufe, sec, run_id)
        print(f"      OK {art_wav.name} ({sec:.1f}s)")
    else:
        result["errors"].append("Artikel-TTS fehlgeschlagen")
        print("      FEHLER Artikel-TTS")
        return result

    # ── Quiz-Audio (nur --quiz) ────────────────────────────────────────────
    if quiz:
        clips = _build_quiz_clips(article)
        if not clips:
            print("      (kein Quiz im JSON — übersprungen)")
        for suffix, clip_text in clips:
            wav = out_dir / f"{stem}_{suffix}.wav"
            if synth(client, clip_text, stufe, wav):
                sec = _wav_seconds(wav)
                result["quiz_wavs"].append(wav.name)
                _track(thema, stufe, sec, run_id)
                print(f"      OK {wav.name} ({sec:.1f}s)")
                time.sleep(1)
            else:
                result["errors"].append(f"Quiz-TTS fehlgeschlagen: {suffix}")
                print(f"      FEHLER {suffix}")

    return result


def main():
    ap = argparse.ArgumentParser(description="Wissensfreund TTS-Orchestrator (Stage 4)")
    ap.add_argument("json_path", help="Artikel-JSON (Canonical-Format mit sections+quiz)")
    ap.add_argument("--out-dir", default="tts_out", help="Ausgabeverzeichnis (default: tts_out)")
    ap.add_argument("--quiz", action="store_true", help="Quiz-Audio mitvertonen")
    ap.add_argument("--run-id", default=None, help="Run-ID für cost_tracker (default: Zeitstempel)")
    args = ap.parse_args()

    load_env()
    if "GEMINI_API_KEY" not in os.environ:
        sys.exit("FEHLER: GEMINI_API_KEY nicht gesetzt (.env).")

    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    res = produce_article(args.json_path, args.out_dir, quiz=args.quiz,
                          client=client, run_id=args.run_id)

    print("\n=== Ergebnis ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
