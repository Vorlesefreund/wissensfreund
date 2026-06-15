#!/usr/bin/env python3
"""
tts_audio_compare.py  v1  (2026-06-15)
Wissensfreund — TTS-Audio A/B: feste Tag-Palette vs. freie Tag-Wahl

Pipeline je Artikel-Stufe:
  1. Tagging mit FESTER Palette  (wissensfreund_tts_tagging_v1.md)      → Flash
  2. Tagging mit FREIER Wahl     (wissensfreund_tts_tagging_FREE_v1.md) → Flash
  3. Beide getaggten Texte → Gemini 3.1 Flash TTS → zwei .wav-Dateien
  4. HTML mit zwei Audio-Playern nebeneinander + getaggtem Text

Nutzung:
  python tts_audio_compare.py --articles Vulkan Dinosaurier Kühlschrank --stufen 1 2 3
  python tts_audio_compare.py --articles Elefant --stufen 1     # nur S1

Voraussetzung:
  pip install google-genai
  GEMINI_API_KEY in .env
"""

import os, sys, json, re, pathlib, argparse, time, struct, wave
from tts_compose import compose

PROMPT_FIXED = pathlib.Path("wissensfreund_tts_tagging_v1.md")
PROMPT_FREE  = pathlib.Path("wissensfreund_tts_tagging_FREE_v1.md")
OUT_DIR      = pathlib.Path("tts_audio_compare_out")

TAGGING_MODEL = "gemini-3.5-flash"
TTS_MODEL     = "gemini-3.1-flash-tts-preview"
STUFE_LABEL   = {"1": "S1", "2": "S2", "3": "S3"}

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
VOICE_NAME = "Iapetus"


def load_env():
    env = pathlib.Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _decode_json_str(s: str) -> str:
    return (s.replace("\\n", "\n").replace("\\t", "\t")
             .replace('\\"', '"').replace("\\\\", "\\")
             .replace("\\r", "\r").replace("\\/", "/"))


def extract_json(raw: str) -> dict | None:
    t = raw.strip()
    t = re.sub(r"^```[a-z]*\n?", "", t).rstrip("`").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Positional fallback: toleriert unescaped " im tts_text-Wert (z.B. ASCII-Quotes)
    sound_m = re.search(r'"sound_mood"\s*:\s*"([^"]*)"', t)
    tts_key_m = re.search(r'"tts_text"\s*:\s*"', t)
    if tts_key_m and sound_m:
        val_start = tts_key_m.end()
        val_end = t.rfind('"', val_start, sound_m.start())
        if val_end > val_start:
            return {"tts_text": _decode_json_str(t[val_start:val_end]),
                    "sound_mood": sound_m.group(1)}
    return None


def tag_text(client, system: str, text: str, stufe: str) -> dict:
    from google.genai import types
    user = (f"Stufe: {stufe}\n\nArtikeltext (tag-frei):\n{text}\n\n"
            f"Füge Inline-Tags gemäß den Regeln für {stufe} ein und gib das JSON aus.")
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=TAGGING_MODEL, contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=8192, temperature=0.7),
            )
            if resp.text is None:
                raise ValueError("model returned text=None (token budget?)")
            data = extract_json(resp.text)
            if data and data.get("tts_text"):
                return data
        except Exception as e:
            print(f"      Tag-Retry {attempt+1}: {str(e)[:50]}")
            time.sleep(5)
    return {"tts_text": "", "sound_mood": "", "error": "tagging failed"}


def synth_tts(client, tts_text: str, stufe: str, out_wav: pathlib.Path) -> bool:
    from google.genai import types
    prompt = f"{SCENE[stufe]}\n\n{tts_text}"
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
            # Gemini liefert PCM 24kHz mono → in WAV verpacken
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000)
                wf.writeframes(audio_b)
            return True
        except Exception as e:
            print(f"      TTS-Retry {attempt+1}: {str(e)[:60]}")
            time.sleep(5)
    return False


def build_html(results: list[dict]) -> str:
    rows = ""
    for r in results:
        def cell(variant):
            v = r[variant]
            if not v.get("ok"):
                return f'<td class="err">FEHLER</td>'
            tts = (v["tts_text"] or "").replace("[", '<span class="tag">[').replace("]", "]</span>")
            return (f'<td><audio controls src="{v["wav"]}"></audio>'
                    f'<div class="mood">🎵 {v.get("sound_mood","—")}</div>'
                    f'<div class="tts">{tts}</div></td>')
        rows += (f'<tr><td class="meta"><b>{r["thema"]}</b><br>{r["stufe"]}</td>'
                 f'{cell("fixed")}{cell("free")}</tr>')
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>TTS Audio A/B — Feste vs. Freie Tags</title><style>
body{{font-family:Arial,sans-serif;margin:16px;background:#f5f5f5}}
h1{{color:#1F4E79}} table{{border-collapse:collapse;width:100%;background:white}}
th,td{{border:1px solid #ddd;padding:12px;vertical-align:top;font-size:.85em}}
th{{background:#1F4E79;color:white}} td.meta{{width:90px;background:#fafafa}}
.tag{{color:#2E7D32;font-weight:bold}} audio{{width:100%;margin-bottom:6px}}
.mood{{color:#666;font-size:.8em;font-style:italic;margin-bottom:6px}}
.tts{{line-height:1.6;max-height:200px;overflow:auto;font-size:.9em}}
.err{{color:#c00}}
</style></head><body>
<h1>🎙️ TTS Audio-Vergleich — Feste Palette vs. Freie Tag-Wahl (beide Flash)</h1>
<p>Beide Spalten getaggt mit Gemini Flash, vertont mit {TTS_MODEL}. Stimme: {VOICE_NAME}.</p>
<table><thead><tr><th>Artikel</th>
<th>FESTE Palette (~13 Tags)</th><th>FREIE Tag-Wahl (volles Vokabular)</th>
</tr></thead><tbody>{rows}</tbody></table></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="Verzeichnis mit *.json Artikeln (aus dem Generator)")
    ap.add_argument("--articles", nargs="+", help="Themennamen für legacy .md Betrieb")
    ap.add_argument("--stufen", nargs="+", default=["1", "2", "3"])
    args = ap.parse_args()

    if not args.dir and not args.articles:
        sys.exit("FEHLER: --dir <verzeichnis> oder --articles <themen...> angeben.")

    load_env()
    if "GEMINI_API_KEY" not in os.environ:
        sys.exit("FEHLER: GEMINI_API_KEY nicht gesetzt.")
    OUT_DIR.mkdir(exist_ok=True)

    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    sys_fixed = PROMPT_FIXED.read_text(encoding="utf-8")
    sys_free  = PROMPT_FREE.read_text(encoding="utf-8")

    # Artikel sammeln
    tasks = []  # [(thema_slug, stufe_label, composed_text), ...]
    if args.dir:
        for jf in sorted(f for f in pathlib.Path(args.dir).glob("*.json")
                         if not f.name.endswith("_report.json")):
            article = json.loads(jf.read_text(encoding="utf-8"))
            level = article.get("meta", {}).get("age_level", 2)
            stufe = f"S{max(1, min(3, int(level)))}"
            thema = jf.stem  # filename stem as unique label (avoids collisions in --dir)
            text  = compose(article, stufe)
            if text.strip():
                tasks.append((thema, stufe, text))
            else:
                print(f"  übersprungen (kein Text): {jf.name}")
    else:
        # Legacy: .md-Dateien aus pilot_output3
        pilot_dir = pathlib.Path("pilot_output3")
        for thema in args.articles:
            for s in args.stufen:
                f = pilot_dir / f"{thema}_S{s}.md"
                if f.exists():
                    tasks.append((thema, STUFE_LABEL[s], f.read_text(encoding="utf-8")))
                else:
                    print(f"  übersprungen (nicht gefunden): {f.name}")

    print(f"\n{len(tasks)} Artikel-Stufen × 2 Varianten = {len(tasks)*2} TTS-Generierungen\n")

    results = []
    for thema, stufe, text in tasks:
        print(f"  {thema} {stufe}")
        entry = {"thema": thema, "stufe": stufe}
        for variant, system in [("fixed", sys_fixed), ("free", sys_free)]:
            print(f"    [{variant}] tagging …", end=" ", flush=True)
            tagged = tag_text(client, system, text, stufe)
            if not tagged.get("tts_text"):
                entry[variant] = {"ok": False}
                print("TAGGING-FEHLER")
                continue
            slug = re.sub(r"[^a-z0-9]", "_", thema.lower())[:20]
            wav = OUT_DIR / f"{slug}_{stufe}_{variant}.wav"
            print("→ TTS …", end=" ", flush=True)
            ok = synth_tts(client, tagged["tts_text"], stufe, wav)
            entry[variant] = {
                "ok": ok, "wav": wav.name,
                "tts_text": tagged["tts_text"], "sound_mood": tagged.get("sound_mood", ""),
            }
            print("OK" if ok else "TTS-FEHLER")
            time.sleep(2)
        results.append(entry)

    (OUT_DIR / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    html = OUT_DIR / "tts_audio_compare.html"
    html.write_text(build_html(results), encoding="utf-8")
    print(f"\nVergleich: {html.resolve()}")
    print("→ Im Browser öffnen, beide Audio-Varianten je Artikel anhören.")


if __name__ == "__main__":
    main()
