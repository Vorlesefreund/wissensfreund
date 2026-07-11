#!/usr/bin/env python3
"""tts_story.py — Mehrsprecher-Vertonung für den Story-Modus (4–8 J.).

Eine Wissensgeschichte hat drei Sprecher: Erzähler + neugieriges Kind + erwachsene
Person. Dieses Skript
  1) segmentiert die fertige Geschichte per Modell in Sprecher-Turns (Wortlaut bleibt),
  2) rendert jeden Turn mit der ZUGEORDNETEN Stimme (Gemini-TTS, eine Stimme je Call),
  3) schneidet die PCM-Segmente mit kurzen Pausen zu EINER WAV zusammen ("das Schneiden").

Stimmen (Prebuilt): Erzähler=Iapetus · Kind ♂=Puck ♀=Leda · Erwachsener ♂=Gacrux ♀=Vindemiatrix.

  # aus Roh-Prosa (schnell, keine Neugenerierung):
  python -X utf8 tts_story.py --story-file story.txt --titel "Leonardo" --out-dir "C:/Users/Andreas/Desktop/_vertonung"
  # oder frisch aus dem Checkpoint erzeugen und vertonen:
  python -X utf8 tts_story.py --checkpoint <cp.json> --thema "Leonardo da Vinci" --model claude-sonnet-5 --out-dir DIR
"""
from __future__ import annotations
import argparse, json, re, sys, time, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

SAMPLE_RATE = 24000          # Gemini liefert PCM 24 kHz mono 16-bit
TTS_MODEL   = "gemini-3.1-flash-tts-preview"
GAP_TURN    = 0.35           # Pause zwischen Turns desselben Sprechers / kurzer Wechsel
GAP_SCENE   = 0.75           # Pause an Szenen-/Absatzgrenzen

# ── Stimm-Zuordnung + (bewusst zurückgenommene) Stil-Vorgaben ──────────────────
VOICES = {
    "erzähler":          "Iapetus",
    ("kind", "m"):       "Puck",
    ("kind", "w"):       "Leda",
    ("erwachsener", "m"): "Gacrux",
    ("erwachsener", "w"): "Vindemiatrix",
}
STYLE = {
    "erzähler":     "Lies ruhig und warm vor, wie ein guter Vorlese-Erzähler. Natürlich und unaufgeregt, ein leises Lächeln in der Stimme.",
    "kind":         "Sprich als neugieriges Kind: natürlich lebendig und interessiert, aber nicht überdreht.",
    "erwachsener":  "Sprich warm, geduldig und erklärend, mit einem Lächeln — ruhig, nicht theatralisch.",
}

# ── Segmentierung (Modell) ─────────────────────────────────────────────────────
SEG_SYSTEM = """Du zerlegst eine vorgelesene Kindergeschichte in SPRECHER-ABSCHNITTE für die Vertonung. Die Geschichte hat genau drei Sprecher-Rollen:
- "erzähler": beschreibt Umgebung und Handlung (alles außerhalb wörtlicher Rede).
- "kind": das neugierige Kind (wörtliche Rede des Kindes).
- "erwachsener": die erwachsene Person, die erklärt (wörtliche Rede der erwachsenen Person).

REGELN:
- Gib die Turns in EXAKTER Reihenfolge des Textes zurück. Fasse direkt aufeinanderfolgenden Text DERSELBEN Rolle zu EINEM Turn zusammen.
- Der Wortlaut bleibt UNVERÄNDERT — nichts hinzufügen, nichts weglassen, nichts umformulieren. Entferne nur die Anführungszeichen der wörtlichen Rede und abgetrennte Redebegleitsätze („, fragt Nico") ordne dem erzähler zu, wenn sie außerhalb der Anführungszeichen stehen.
- Ordne jede wörtliche Rede der richtigen sprechenden Rolle zu (an der Redebegleitung erkennbar: „…", sagt Oma → erwachsener; „…", fragt Nico → kind).
- setze szene=true beim ersten Turn eines neuen Absatzes/Schauplatzwechsels, sonst false.

Bestimme außerdem den CAST: Name + Geschlecht (m/w) des Kindes und der erwachsenen Person.

Antworte NUR als JSON: {"cast":{"kind":{"name":"...","geschlecht":"m|w"},"erwachsener":{"name":"...","geschlecht":"m|w"}},"turns":[{"rolle":"erzähler|kind|erwachsener","text":"...","szene":true|false}]}"""

SEG_SCHEMA = {
    "type": "object",
    "required": ["cast", "turns"],
    "properties": {
        "cast": {"type": "object", "required": ["kind", "erwachsener"], "properties": {
            "kind":       {"type": "object", "required": ["name", "geschlecht"],
                           "properties": {"name": {"type": "string"}, "geschlecht": {"type": "string"}}},
            "erwachsener": {"type": "object", "required": ["name", "geschlecht"],
                           "properties": {"name": {"type": "string"}, "geschlecht": {"type": "string"}}}}},
        "turns": {"type": "array", "items": {
            "type": "object", "required": ["rolle", "text", "szene"],
            "properties": {"rolle": {"type": "string"}, "text": {"type": "string"},
                           "szene": {"type": "boolean"}}}},
    },
}


def segment_story(story_text: str, model: str = "claude-sonnet-5") -> dict:
    body = ("GESCHICHTE:\n" + story_text + "\n\n"
            "AUFGABE: Zerlege sie nach deinen Regeln in Sprecher-Turns und bestimme den Cast. Nur JSON.")
    if model.startswith("claude"):
        import claude_client
        return claude_client.call_claude_json(SEG_SYSTEM, body, SEG_SCHEMA,
                                               model=model, max_tokens=8192, call_name="tts_seg") or {}
    import gemini_client
    raw = gemini_client.call_gemini(SEG_SYSTEM, body, model=model,
                                    response_mime_type="application/json",
                                    response_schema=SEG_SCHEMA, call_name="tts_seg")
    return json.loads(raw)


def _voice_for(rolle: str, cast: dict) -> str:
    if rolle == "erzähler":
        return VOICES["erzähler"]
    g = ((cast.get(rolle) or {}).get("geschlecht") or "m").lower()[:1]
    g = g if g in ("m", "w") else "m"
    return VOICES.get((rolle, g), VOICES["erzähler"])


# ── TTS + Schnitt ──────────────────────────────────────────────────────────────
def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(round(seconds * SAMPLE_RATE))


def synth_pcm(client, voice: str, style: str, text: str, retries: int = 3) -> bytes | None:
    from google.genai import types
    prompt = f"{style}\n\n{text}"
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=TTS_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))),
            )
            return resp.candidates[0].content.parts[0].inline_data.data
        except Exception as e:
            print(f"      TTS-Retry {attempt+1}: {str(e)[:60]}")
            time.sleep(6)
    return None


def vertone(seg: dict, out_wav: Path) -> dict:
    """Rendert alle Turns und schneidet sie zu einer WAV. Gibt ein Manifest zurück."""
    import os
    from google import genai
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    cast, turns = seg.get("cast", {}), seg.get("turns", [])
    print(f"  Cast: Kind={cast.get('kind')} · Erwachsener={cast.get('erwachsener')} · {len(turns)} Turns")
    chunks: list[bytes] = []
    manifest = []
    for i, t in enumerate(turns):
        rolle = t.get("rolle", "erzähler")
        text  = (t.get("text") or "").strip()
        if not text:
            continue
        voice = _voice_for(rolle, cast)
        style = STYLE.get(rolle, STYLE["erzähler"])
        if chunks:                                   # Pause VOR diesem Turn
            chunks.append(_silence(GAP_SCENE if t.get("szene") else GAP_TURN))
        print(f"    [{i+1:02}/{len(turns)}] {rolle:12} {voice:12} \"{text[:48]}…\"")
        pcm = synth_pcm(client, voice, style, text)
        if pcm is None:
            print(f"      ! Turn {i+1} fehlgeschlagen — übersprungen")
            continue
        chunks.append(pcm)
        manifest.append({"i": i, "rolle": rolle, "voice": voice,
                         "sec": round(len(pcm) / 2 / SAMPLE_RATE, 2), "text": text[:80]})
        time.sleep(0.8)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(chunks))
    total = sum(len(c) for c in chunks) / 2 / SAMPLE_RATE
    return {"cast": cast, "n_turns": len(turns), "n_rendered": len(manifest),
            "total_sec": round(total, 1), "wav": str(out_wav), "turns": manifest}


# ── Story beschaffen ───────────────────────────────────────────────────────────
def _story_from_checkpoint(cp: Path, thema: str, model: str) -> str:
    import story_mode_v2 as sm
    d = json.loads(cp.read_text(encoding="utf-8"))
    topics = d.get("topics") or d.get("topics_data") or d
    res = sm.build_story(thema, topics[thema], model)
    return res["story_clean"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story-file", help="Roh-Prosa der Geschichte (txt) — direkt vertonen")
    ap.add_argument("--checkpoint", help="Stage-1-Checkpoint (alternativ: frisch erzeugen)")
    ap.add_argument("--thema", help="Thema im Checkpoint")
    ap.add_argument("--model", default="claude-sonnet-5", help="Generierungsmodell (mit --checkpoint)")
    ap.add_argument("--seg-model", default="claude-sonnet-5", help="Segmentierungsmodell")
    ap.add_argument("--titel", default="story", help="Dateiname-Basis")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    if args.story_file:
        story = Path(args.story_file).read_text(encoding="utf-8").strip()
    elif args.checkpoint and args.thema:
        print(f"Erzeuge Geschichte ({args.model}) …")
        story = _story_from_checkpoint(Path(args.checkpoint), args.thema, args.model)
    else:
        sys.exit("Entweder --story-file ODER (--checkpoint + --thema) angeben.")

    print(f"Segmentiere ({args.seg_model}) …")
    seg = segment_story(story, args.seg_model)

    out_dir = Path(args.out_dir)
    safe = re.sub(r"[^\w]+", "_", args.titel).strip("_")
    wav = out_dir / f"{safe}.wav"
    print(f"Vertone → {wav}")
    info = vertone(seg, wav)

    (out_dir / f"{safe}_manifest.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFERTIG: {info['n_rendered']}/{info['n_turns']} Turns · "
          f"{info['total_sec']} s · {wav}")


if __name__ == "__main__":
    main()
