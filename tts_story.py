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
import argparse, json, re, subprocess, sys, time, wave
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
SEG_SYSTEM = """Du zerlegst eine vorgelesene Kindergeschichte in SPRECHER-ABSCHNITTE für eine HÖRSPIEL-Vertonung mit verschiedenen Stimmen. Drei Sprecher-Rollen:
- "erzähler": beschreibt Umgebung, Szene und HANDLUNGEN (alles außerhalb wörtlicher Rede), z. B. "Oma Rina lacht." oder "Theo blättert weiter."
- "kind": die wörtliche Rede des neugierigen Kindes.
- "erwachsener": die wörtliche Rede der erwachsenen Person, die erklärt.

HÖRSPIEL-REGELN (wichtig):
- Verschiedene Stimmen sagen dem Zuhörer bereits, WER spricht. Reine Redebegleitsätze ("sagt Oma Rina", "fragt Theo", "antwortet sie") werden daher NICHT als Turn ausgegeben — lass sie komplett weg.
- Enthält ein Redebegleitsatz eine ECHTE zusätzliche Handlung ("… und tippt mit dem Finger auf das Bild"), behalte NUR diesen Handlungsteil als erzähler-Turn; den reinen "sagt/fragt X"-Teil lässt du weg.
- Ganze Handlungs-/Szenensätze ("Oma Rina lacht.", "Theo schließt das Buch vorsichtig.") BLEIBEN als erzähler-Turn erhalten.
- Wird wörtliche Rede durch einen Redebegleitsatz UNTERBROCHEN ("A", sagt X, "B"), füge die beiden Hälften zu EINEM Sprech-Turn zusammen (text = "A B", flüssiger Wortlaut) mit der Rolle des Sprechers X. KEINE abgehängten Ein-Wort-Fragmente.
- Fasse direkt aufeinanderfolgenden Text DERSELBEN Rolle zu EINEM Turn zusammen. Reihenfolge = exakte Textreihenfolge.
- Der Wortlaut der Rede bleibt UNVERÄNDERT (nur Anführungszeichen entfernen und unterbrochene Zitate zusammenfügen).
- Ordne jede Rede der richtigen Rolle zu (an der Redebegleitung erkennbar: sagt Oma → erwachsener; fragt Nico → kind).
- setze szene=true beim ersten Turn eines neuen Absatzes/Schauplatzwechsels, sonst false.

VORTRAG / EMOTION (Feld "emotion", kurzer deutscher Hinweis 1–4 Wörter, sonst ""):
- Gib pro Sprech-Turn (kind/erwachsener) einen Vortrags-Hinweis, abgeleitet aus Redebegleitsatz UND Kontext: z. B. "lächelnd", "amüsiert", "aufgeregt", "leise, geheimnisvoll", "ernst, behutsam", "staunend", "traurig". Neutral → "".
- Beschreibt eine UNMITTELBAR davorstehende Handlung die Stimmung der folgenden Rede ("Oma Rina lacht." vor Omas Satz), übernimm sie in das emotion-Feld dieses Sprech-Turns (z. B. "amüsiert, lachend").
- Passt der ernste/fröhliche Charakter des INHALTS (z. B. ein trauriges Thema), darf das die emotion mitbestimmen.
- erzähler-Turns: "emotion" meist "".

Bestimme außerdem den CAST: Name + Geschlecht (m/w) des Kindes und der erwachsenen Person.

Antworte NUR als JSON: {"cast":{"kind":{"name":"...","geschlecht":"m|w"},"erwachsener":{"name":"...","geschlecht":"m|w"}},"turns":[{"rolle":"erzähler|kind|erwachsener","text":"...","szene":true|false,"emotion":"..."}]}"""

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
            "type": "object", "required": ["rolle", "text", "szene", "emotion"],
            "properties": {"rolle": {"type": "string"}, "text": {"type": "string"},
                           "szene": {"type": "boolean"}, "emotion": {"type": "string"}}}},
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


def _style_for(rolle: str, turn: dict) -> str:
    """Rollen-Grundstil + optionaler Vortrags-Hinweis (emotion) aus der Segmentierung."""
    base = STYLE.get(rolle, STYLE["erzähler"])
    emo = (turn.get("emotion") or "").strip()
    return f"{base} Sprich diesen Satz {emo}." if emo else base


# ── TTS + Schnitt ──────────────────────────────────────────────────────────────
def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(round(seconds * SAMPLE_RATE))


def _loudnorm(pcm: bytes, sr: int = SAMPLE_RATE) -> bytes:
    """Gleicht die Lautheit eines Turns an (I=-16 LUFS). Wichtig, wenn Kind-Turns
    aus der Voice-Conversion und Erwachsenen-/Erzähler-Turns aus Flash gemischt
    werden — sonst springen die Pegel. Fällt bei ffmpeg-Fehler auf das Original zurück."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
             "-af", "loudnorm=I=-16:TP=-1.5", "-f", "s16le", "-ar", str(sr), "-ac", "1", "pipe:1"],
            input=pcm, capture_output=True)
        return r.stdout or pcm
    except Exception:
        return pcm


def _tts_call(client, voice: str, content: str):
    """Ein einzelner TTS-Aufruf. Gibt (pcm|None, block_reason|None) zurück.
    Wirft bei echten API-Fehlern (Timeout/5xx) — die fängt synth_pcm ab."""
    from google.genai import types
    resp = client.models.generate_content(
        model=TTS_MODEL, contents=content,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))),
    )
    pf = getattr(resp, "prompt_feedback", None)
    block = getattr(pf, "block_reason", None) if pf else None
    cand = resp.candidates[0] if resp.candidates else None
    parts = cand.content.parts if (cand and cand.content) else None
    pcm = parts[0].inline_data.data if (parts and getattr(parts[0], "inline_data", None)) else None
    return pcm, block


def synth_pcm(client, voice: str, style: str, text: str, retries: int = 3) -> bytes | None:
    """Rendert Text als PCM — robust gegen den Safety-False-Positive.

    Flash blockt deterministisch die Kombination (Stil-Präfix + kurzes/heikles
    Fragment) mit block_reason=PROHIBITED_CONTENT, obwohl der Text harmlos ist
    (z. B. „Das", „so wie er"). Erneutes Senden desselben Prompts hilft NIE.
    Fallback: denselben Wortlaut OHNE Stil-Präfix senden — der nackte Text
    liefert zuverlässig Audio. Wortlaut und Reihenfolge bleiben UNVERÄNDERT;
    nur die feine Stilsteuerung entfällt bei dem einen betroffenen Clip
    (Timbre/Charakter trägt bei Nico ohnehin Stimme + Voice-Conversion)."""
    full = f"{style}\n\n{text}"
    for attempt in range(retries):
        try:
            pcm, block = _tts_call(client, voice, full)
            if pcm is not None:
                return pcm
            if block is not None:                       # deterministischer Block → Präfix weglassen
                print(f"      TTS-Block ({block}) — Fallback ohne Stil-Präfix")
                pcm2, block2 = _tts_call(client, voice, text)
                if pcm2 is not None:
                    return pcm2
                print(f"      ! Fallback weiter blockiert ({block2}) — Turn übersprungen")
                return None                             # nackter Text blockt praktisch nie
            print(f"      TTS leer (kein Block) — Retry {attempt+1}")   # transient
        except Exception as e:
            print(f"      TTS-Retry {attempt+1}: {str(e)[:60]}")
        time.sleep(6)
    return None


def vertone(seg: dict, out_wav: Path, nico_converter=None, normalize: bool | None = None) -> dict:
    """Rendert alle Turns und schneidet sie zu einer WAV. Gibt ein Manifest zurück.

    nico_converter: optionaler Callable ``(pcm: bytes, sr: int) -> bytes``. Wenn gesetzt,
        werden KIND-Turns durch diese Voice-Conversion geschickt (Flash-Quellstimme →
        Klangfarbe des Sohnes). Standard None = unveränderte Prebuilt-Stimme.
    normalize: Turn-Pegel per loudnorm angleichen. Standard = an, sobald ein Converter
        aktiv ist (Kind-VC und Flash-Turns stammen dann aus verschiedenen Quellen)."""
    import os
    from google import genai
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    if normalize is None:
        normalize = nico_converter is not None

    cast, turns = seg.get("cast", {}), seg.get("turns", [])
    print(f"  Cast: Kind={cast.get('kind')} · Erwachsener={cast.get('erwachsener')} · {len(turns)} Turns"
          f"{' · Nico-VC AN' if nico_converter else ''}{' · loudnorm' if normalize else ''}")
    chunks: list[bytes] = []
    manifest = []
    for i, t in enumerate(turns):
        rolle = t.get("rolle", "erzähler")
        text  = (t.get("text") or "").strip()
        if not text:
            continue
        voice = _voice_for(rolle, cast)
        style = _style_for(rolle, t)
        print(f"    [{i+1:02}/{len(turns)}] {rolle:12} {voice:12} \"{text[:48]}…\"")
        pcm = synth_pcm(client, voice, style, text)
        if pcm is None:
            print(f"      ! Turn {i+1} fehlgeschlagen — übersprungen")
            continue
        vc = False
        if rolle == "kind" and nico_converter is not None:
            try:
                conv = nico_converter(pcm, SAMPLE_RATE)
                if conv:
                    pcm, vc = conv, True
            except Exception as e:
                print(f"      ! Nico-VC fehlgeschlagen ({str(e)[:60]}) — Flash-Kind behalten")
        if normalize:
            pcm = _loudnorm(pcm)
        if chunks:                                   # Pause VOR diesem Turn (nur wenn schon Audio da ist)
            chunks.append(_silence(GAP_SCENE if t.get("szene") else GAP_TURN))
        chunks.append(pcm)
        manifest.append({"i": i, "rolle": rolle, "voice": voice, "vc": vc,
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
    # Nico-Voice-Conversion (optional, braucht GPU + OpenVoice; siehe nico_vc.py)
    ap.add_argument("--nico-ref", help="Ordner mit Sohn-Referenz-WAVs → Kind-Turns per VC umfärben")
    ap.add_argument("--nico-ckpt", help="OpenVoice-converter-Checkpoint-Ordner (config.json + checkpoint.pth)")
    ap.add_argument("--nico-tau", type=float, default=0.7, help="VC-Stärke (Standard 0.7)")
    ap.add_argument("--openvoice-path", help="Pfad zum geklonten OpenVoice-Repo (für den Import)")
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

    nico_converter = None
    if args.nico_ref:
        if not args.nico_ckpt:
            sys.exit("--nico-ref braucht auch --nico-ckpt (OpenVoice-converter-Ordner).")
        from nico_vc import OpenVoiceNicoConverter
        print(f"Nico-VC aktiv (ref={args.nico_ref}, tau={args.nico_tau}) …")
        nico_converter = OpenVoiceNicoConverter(
            args.nico_ref, args.nico_ckpt, tau=args.nico_tau, openvoice_path=args.openvoice_path)

    out_dir = Path(args.out_dir)
    safe = re.sub(r"[^\w]+", "_", args.titel).strip("_")
    wav = out_dir / f"{safe}.wav"
    print(f"Vertone → {wav}")
    info = vertone(seg, wav, nico_converter=nico_converter)

    (out_dir / f"{safe}_manifest.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFERTIG: {info['n_rendered']}/{info['n_turns']} Turns · "
          f"{info['total_sec']} s · {wav}")


if __name__ == "__main__":
    main()
