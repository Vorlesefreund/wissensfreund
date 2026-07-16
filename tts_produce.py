#!/usr/bin/env python3
"""
tts_produce.py  v2  (2026-06-24)
Wissensfreund — TTS-Orchestrator (Stage 4): vertont fertige Canonical-JSON-Artikel.

- Artikel-Audio (immer): tts_compose.compose() → EINE WAV pro Artikel.
- Quiz-Audio (--quiz):    intro / qN / richtig_N / falsch_N / abschluss_* als Einzelclips.

Kein separater Tagging-Schritt — compose() liefert den fertigen Vorlesetext inkl.
Stil-Tags ([excited]/[thoughtful]/[serious]) und [pause=N]-Marker.

Pausen: gemini-3.1-flash-tts-preview honoriert [pause=N] nur qualitativ (cappt bei
~1.9 s). Große Pausen (>= PAUSE_SPLIT_MIN) werden daher als ECHTE Stille-Segmente
auf Audio-Ebene eingefügt (Text an der Pause splitten, PCM mit N s Stille verbinden).
Kleine Pausen (z.B. 0.3 s im Quiz) bleiben inline — die qualitative Modell-Pause genügt.

Stimme:  Iapetus
Modell:  gemini-3.1-flash-tts-preview
Stimmung: neutral | ernst | staunend (auto aus title+category), je 3 Stufen-Varianten.

Nutzung (CLI):
  python tts_produce.py <artikel.json> [--out-dir DIR] [--quiz]

Importierbar:
  produce_article(json_path, out_dir, quiz=False) -> dict
"""

import os
import sys
import re
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

TTS_MODEL       = "gemini-3.1-flash-tts-preview"
VOICE_NAME      = "Iapetus"
SAMPLE_RATE     = 24000   # Gemini liefert PCM 24 kHz mono 16-bit
PAUSE_SPLIT_MIN = 1.5     # Pausen >= 1.5 s → echte Stille; kleinere bleiben inline
TTS_TIMEOUT_MS  = 60_000  # Das SDK hat KEIN Default-Timeout — ohne das hängt ein Call unbegrenzt
                          # und blockiert den ganzen Batch (Flash liefert regelmäßig 504/503).

# ── Stimmungs-Varianten der Scene-Instruction (je Stufe) ───────────────────────
MOOD_SCENE = {
    "neutral": {
        "S1": ("Read aloud as a good-natured professor sharing something with a young child, "
               "as if sitting together quietly. Calm, warm, a little slower than normal. "
               "Friendly but understated — let the wonder come from the words, not loud emphasis."),
        "S2": ("Read aloud as a relaxed, good-natured professor sharing a story with a child. "
               "Conversational and unhurried, as if chatting at the kitchen table. "
               "Understated, warm, natural — no dramatic emphasis."),
        "S3": ("Read aloud as a calm, knowledgeable professor explaining something to an older child. "
               "Conversational and even, quietly engaged. "
               "Natural pace, minimal emphasis — clear and grounded, never dramatic."),
    },
    "ernst": {
        "S1": ("Read aloud as a calm, gentle professor telling a young child about a serious "
               "historical event. Very quiet and warm, measured pace. No dramatization — just "
               "honest, simple, and kind."),
        "S2": ("Read aloud as a composed professor explaining a difficult historical topic to a "
               "child. Steady, thoughtful, and respectful. Calm gravitas without being heavy or scary."),
        "S3": ("Read aloud as a knowledgeable professor discussing a serious historical subject with "
               "an older child. Measured, clear, with quiet weight. Factual but humane — never cold, "
               "never theatrical."),
    },
    "staunend": {
        "S1": ("Read aloud as a warmly curious professor sharing something amazing with a small "
               "child. Gently animated at surprising moments, but mostly calm and cozy. Never loud "
               "or overdone."),
        "S2": ("Read aloud as an enthusiastic but composed professor telling a child something "
               "extraordinary. Allow quiet wonder to show at key moments, then return to a relaxed "
               "pace. Understated delight."),
        "S3": ("Read aloud as a professor genuinely fascinated by a topic, sharing it with an older "
               "child. Subtly engaged — let curiosity color the delivery without overemphasizing. "
               "Intellectually alive."),
    },
}

ERNST_KEYWORDS = {"krieg", "weltkrieg", "holocaust", "terror", "katastrophe",
                  "sklaverei", "völkermord", "pest", "seuche", "spartacus"}
STAUNEND_KEYWORDS = {"weltraum", "galaxie", "universum", "dinosaurier",
                     "evolution", "ozean", "tiefseee", "vulkan", "naturwunder"}

# ── Quiz-Bausteine ─────────────────────────────────────────────────────────────
RICHTIG_VARIANTEN = [
    "Richtig! [pause=0.3] Sehr gut.",
    "Genau! [pause=0.3] Das hast du dir gut gemerkt.",
    "Ja, stimmt! [pause=0.3] Wunderbar.",
    "Richtig! [pause=0.3] Du kennst dich aus.",
    "Sehr gut! [pause=0.3] Genau richtig.",
]
FALSCH_VARIANTEN = [
    "Diese Antwort war leider falsch. [pause=0.3] Die richtige Antwort war {ck}: {ct}.",
    "Knapp daneben. [pause=0.3] Richtig wäre gewesen: {ck}: {ct}.",
    "Das stimmt leider nicht ganz. [pause=0.3] Die Antwort war {ck}: {ct}.",
    "Nicht ganz. [pause=0.3] Es war {ck}: {ct}.",
    "Fast! [pause=0.3] Aber richtig ist: {ck}: {ct}.",
]
ABSCHLUSS_VARIANTEN = {
    "alle_richtig": "Fantastisch! [pause=0.3] Du hast alle Fragen richtig beantwortet. [pause=0.5] Bis zum nächsten Mal!",
    "eine_falsch":  "Sehr gut! [pause=0.3] Fast alles richtig. [pause=0.5] Beim nächsten Mal schaffst du es sicher ganz.",
    "zwei_falsch":  "Gut gemacht! [pause=0.3] Du hast schon viel gelernt. [pause=0.5] Bis zum nächsten Mal!",
    "drei_falsch":  "Du hast gut mitgemacht! [pause=0.3] Schau dir den Artikel noch einmal an — dann klappt es noch besser.",
    "alle_falsch":  "Das war knifflig! [pause=0.3] Hör den Artikel noch einmal und versuch es dann wieder.",
}

_PAUSE_RE = re.compile(r"\[pause=([0-9.]+)\]")


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


def detect_mood(meta: dict) -> str:
    """Stimmung aus title + category_top + category_sub. ernst > staunend > neutral."""
    hay = " ".join(str(meta.get(k) or "") for k in
                   ("title", "category_top", "category_sub")).lower()
    if any(k in hay for k in ERNST_KEYWORDS):
        return "ernst"
    if any(k in hay for k in STAUNEND_KEYWORDS):
        return "staunend"
    return "neutral"


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate() or SAMPLE_RATE)


def _silence(seconds: float) -> bytes:
    """N s Stille als 16-bit-mono-PCM (Null-Frames)."""
    return b"\x00\x00" * int(round(seconds * SAMPLE_RATE))


def synth_pcm(client, text: str, scene_text: str) -> bytes | None:
    """Ein TTS-Call → rohe PCM-Bytes. Scene voran, 3× Retry. None bei Fehler."""
    from google.genai import types
    prompt = f"{scene_text}\n\n{text}"
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
            return resp.candidates[0].content.parts[0].inline_data.data
        except Exception as e:
            print(f"      TTS-Retry {attempt+1}: {str(e)[:60]}")
            time.sleep(5)
    return None


def synth_with_pauses(client, text: str, scene_text: str, out_wav: Path) -> tuple[bool, float]:
    """
    Vertont Text mit exakten Pausen → eine WAV.
    Splittet nur an großen Pausen (>= PAUSE_SPLIT_MIN) und fügt echte Stille ein;
    kleine [pause=N] bleiben inline (Modell-qualitativ).
    Rückgabe: (ok, synthetisierte_audio_sekunden_ohne_stille).
    """
    parts = _PAUSE_RE.split(text)   # [seg, n, seg, n, seg, ...]
    pcm_chunks: list[bytes] = []
    synth_bytes = 0
    buf = parts[0]
    i = 1
    while i < len(parts):
        pause_val = float(parts[i])
        seg_after = parts[i + 1] if i + 1 < len(parts) else ""
        if pause_val >= PAUSE_SPLIT_MIN:
            if buf.strip():
                pcm = synth_pcm(client, buf.strip(), scene_text)
                if pcm is None:
                    return (False, 0.0)
                pcm_chunks.append(pcm)
                synth_bytes += len(pcm)
            pcm_chunks.append(_silence(pause_val))
            buf = seg_after
        else:
            # kleine Pause inline behalten
            buf += f"[pause={parts[i]}]" + seg_after
        i += 2

    if buf.strip():
        pcm = synth_pcm(client, buf.strip(), scene_text)
        if pcm is None:
            return (False, 0.0)
        pcm_chunks.append(pcm)
        synth_bytes += len(pcm)

    if not pcm_chunks:
        return (False, 0.0)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(pcm_chunks))

    return (True, synth_bytes / 2 / SAMPLE_RATE)


def _track(thema: str, stufe: str, audio_sec: float, run_id: str):
    """Synthetisierte tts_audio_sec je Datei an cost_tracker melden (ohne Stille)."""
    if cost_tracker is None:
        return
    try:
        cost_tracker.track(
            run_id=run_id, thema=thema, stufe=stufe,
            schritt="tts", modell=TTS_MODEL, tts_audio_sec=audio_sec,
        )
    except Exception as e:
        print(f"      WARN cost_tracker.track: {str(e)[:80]}")


def _opts_line(options: list[dict]) -> str:
    """'A: Magma. B: Lava. C: Wasser.'"""
    return " ".join(f"{o.get('key')}: {(o.get('text') or '').rstrip('.')}."
                    for o in options)


def _build_quiz_clips(article: dict) -> list[tuple[str, str]]:
    """[(suffix, text), ...] für die Quiz-Einzelclips."""
    quiz = article.get("quiz") or {}
    questions = quiz.get("questions") or []
    clips: list[tuple[str, str]] = []
    if not questions:
        return clips

    for n, q in enumerate(questions, start=1):
        idx = (n - 1) % 5
        qtext = (q.get("text") or "").strip()
        opts = _opts_line(q.get("options") or [])

        # a) Frage 1 im Intro; b) Frage n>=2 eigener Clip
        if n == 1:
            clips.append((
                "quiz_intro",
                f"Jetzt habe ich noch ein paar Fragen für dich!\n"
                f"Frage eins: {qtext}\n{opts}",
            ))
        else:
            clips.append((f"quiz_q{n}", f"Frage {n}: {qtext}\n{opts}"))

        # c) richtig-Clip (Variante deterministisch per Index)
        clips.append((f"quiz_richtig_{n}", RICHTIG_VARIANTEN[idx]))

        # d) falsch-Clip (korrekte Antwort mit vorangestelltem key)
        correct_key = q.get("correct_key")
        correct_text = ""
        for o in (q.get("options") or []):
            if o.get("key") == correct_key:
                correct_text = (o.get("text") or "").strip()
                break
        clips.append((
            f"quiz_falsch_{n}",
            FALSCH_VARIANTEN[idx].format(ck=correct_key, ct=correct_text),
        ))

    # e) Abschluss-Clips nach Ergebnis-Kategorie (App wählt zur Laufzeit)
    for cat, txt in ABSCHLUSS_VARIANTEN.items():
        clips.append((f"quiz_abschluss_{cat}", txt))

    return clips


def produce_article(json_path, out_dir, quiz: bool = False,
                    client=None, run_id: str | None = None) -> dict:
    """
    Vertont einen Artikel: eine Artikel-WAV (immer) + optional Quiz-Clips.
    Rückgabe: dict mit erzeugten Dateien, Längen, Stimmung und etwaigen Fehlern.
    """
    # UTF-8-sichere Ausgabe (Windows-Konsole = cp1252 → … / ü / — crashen sonst).
    # Einmalig: nach dem Wrap ist encoding bereits utf-8, Folgeaufrufe überspringen.
    import io
    if hasattr(sys.stdout, "buffer") and (getattr(sys.stdout, "encoding", "") or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    json_path = Path(json_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    article = json.loads(json_path.read_text(encoding="utf-8"))
    meta = article.get("meta", {}) or {}
    thema = meta.get("title", json_path.stem)
    stufe = _stufe_from_meta(article)
    mood = detect_mood(meta)
    scene_text = MOOD_SCENE[mood][stufe]
    stem = json_path.stem

    if run_id is None:
        run_id = "tts_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if client is None:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                              http_options=types.HttpOptions(timeout=TTS_TIMEOUT_MS))

    result = {
        "json": str(json_path), "thema": thema, "stufe": stufe, "mood": mood,
        "article_wav": None, "article_sec": 0.0,
        "quiz_wavs": [], "errors": [],
    }

    print(f"  [{stem}] {stufe} mood={mood}")

    # ── Artikel-Audio (immer) ──────────────────────────────────────────────
    text = compose(article)  # Stufe intern aus meta.age_level
    if not text.strip():
        result["errors"].append("compose() lieferte leeren Text")
        return result

    art_wav = out_dir / f"{stem}_artikel.wav"
    print("      Artikel-Audio …", flush=True)
    ok, synth_sec = synth_with_pauses(client, text, scene_text, art_wav)
    if ok:
        result["article_wav"] = art_wav.name
        result["article_sec"] = round(_wav_seconds(art_wav), 1)
        _track(thema, stufe, synth_sec, run_id)
        print(f"      OK {art_wav.name} ({result['article_sec']}s WAV, {synth_sec:.1f}s gesprochen)")
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
            ok, synth_sec = synth_with_pauses(client, clip_text, scene_text, wav)
            if ok:
                result["quiz_wavs"].append(wav.name)
                _track(thema, stufe, synth_sec, run_id)
                print(f"      OK {wav.name} ({_wav_seconds(wav):.1f}s)")
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
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(timeout=TTS_TIMEOUT_MS))

    res = produce_article(args.json_path, args.out_dir, quiz=args.quiz,
                          client=client, run_id=args.run_id)

    print("\n=== Ergebnis ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
