#!/usr/bin/env python3
"""tts_cast_round3.py — 3. Justierungsrunde nach PO-Hörfeedback (2026-07-19).

RMS-Stille-Check + keine Gedankenstriche (Gemini-TTS-Leer-Glitch).
  set -a; source .env; set +a
  python -X utf8 tts_cast_round3.py
Ausgabe: C:/Users/Andreas/Desktop/_stimmen_cast_r3_20260719/  (+ LIESMICH.txt)
"""
from __future__ import annotations
import os, sys, time, wave, array, math
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent / ".env")
TTS_MODEL   = "gemini-3.1-flash-tts-preview"
SAMPLE_RATE = 24000
SILENCE_RMS = 150
OUT = Path("C:/Users/Andreas/Desktop/_stimmen_cast_r3_20260719")

JOBS = [
    # Oma Rosa = Vindemiatrix im Leonardo-Erwachsenen-Stil (PO: "Oma Rina war sehr gut")
    ("Oma_Rosa",
     "Sprich warm, geduldig und erklärend, mit einem Lächeln in der Stimme, ruhig und nicht theatralisch, wie eine herzliche Großmutter.",
     ["Weißt du, mein Schatz, als ich so klein war wie du, da gab es das alles noch gar nicht. Wir haben den ganzen Tag draußen gespielt.",
      "Komm, setz dich zu mir. Ich zeig dir etwas Schönes. Siehst du das hier? Das erzähl ich dir jetzt ganz in Ruhe."],
     ["Vindemiatrix"]),
    # Chronist Wilhelm = Algenib, mittleres Tempo (zwischen ganz langsam und der zu schnellen Fassung)
    ("Chronist_Wilhelm",
     "Sprich als alter Chronist und Geschichtenerzähler: feierlich und warm, als läse er aus einem alten Buch, in ruhigem, natürlichem Erzähltempo, eine Spur lebendiger als ganz langsam, aber nicht hastig.",
     ["Vor langer, langer Zeit, so beginnt diese Geschichte, lebte ein Mann, von dem noch heute die ganze Welt spricht. Hör gut zu.",
      "Und in diesem Augenblick, als alle schon aufgegeben hatten, geschah etwas, das niemand für möglich gehalten hätte."],
     ["Algenib"]),
    # Meeresbiologin Ronja = Despina (alte Stimme), geringfügig schneller/lebendiger, nicht verträumt
    ("Meeresbiologin_Ronja",
     "Sprich als Meeresbiologin: ruhig, aber lebendig und zugewandt, klar und freundlich, in etwas zügigerem Tempo, nicht verträumt oder mystisch.",
     ["Schau mal, wer da kommt! Das ist ein junger Tümmler. Der ist heute besonders neugierig und schwimmt ganz nah an unser Boot heran.",
      "Komm, wir tauchen ab. Da unten wartet eine ganze Wunderwelt auf uns, voller Farben und seltsamer Tiere."],
     ["Despina"]),
    # Forscherin Nele = Pulcherrima, 2 frische Szenen (Konsistenz-Check)
    ("Forscherin_Nele",
     "Sprich als begeisterte Museums-Forscherin: klar, präzise, freundlich, voller Faszination für Details.",
     ["Faszinierend, nicht wahr? Schau ganz genau hin. Siehst du diese feinen Linien? Die sind über fünfhundert Jahre alt.",
      "Weißt du, was das Schöne an meiner Arbeit ist? Jedes alte Stück verrät uns ein kleines Geheimnis, wenn man nur genau genug hinschaut."],
     ["Pulcherrima"]),
    # Weltenbummler Tom = cooler/lässiger, weniger aufgedreht
    ("Weltenbummler_Tom",
     "Sprich als weit gereister Weltenbummler: lässig-cool, entspannt und gelassen, freundlich und weltgewandt, aber nicht aufgedreht oder überdreht.",
     ["Na, hast du Lust auf ein Abenteuer? Ich war schon fast überall auf der Welt. Und weißt du was, jeder Ort hat seine eigene kleine Überraschung.",
      "Diese Stadt hier ist echt besonders. Enge Gassen, kleine Brücken über dem Wasser, und mittendrin ein Platz, so groß wie zehn Fußballfelder."],
     ["Zubenelgenubi", "Schedar"]),
]


def _rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    a = array.array("h"); a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    return math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0


def synth(client, voice, scene, text, out_wav):
    prompt = f"{scene}\n\n{text}"
    for attempt in range(6):
        try:
            resp = client.models.generate_content(
                model=TTS_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
                ),
            )
            pcm = resp.candidates[0].content.parts[0].inline_data.data
            r = _rms(pcm)
            if r < SILENCE_RMS:
                print(f"    Versuch {attempt+1}: STUMM (rms {r:.0f}) — neu"); time.sleep(4); continue
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE); wf.writeframes(pcm)
            return r
        except Exception as e:
            print(f"    Versuch {attempt+1}: leer ({str(e)[:40]}) — neu"); time.sleep(4)
    return 0.0


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY fehlt (.env).")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    OUT.mkdir(parents=True, exist_ok=True)
    leg = ["STORY-CAST — Justierungsrunde 3 (PO-Feedback 2026-07-19)",
           "Dateiname: Figur__Stimme_a|b.wav\n"]
    ok = bad = 0
    for figur, scene, szenen, voices in JOBS:
        leg.append(f"### {figur}   (Stil: {scene})")
        for voice in voices:
            for i, txt in enumerate(szenen):
                suf = "ab"[i]
                out_wav = OUT / f"{figur}__{voice}_{suf}.wav"
                print(f"[{figur} / {voice} / {suf}] …")
                r = synth(client, voice, scene, txt, out_wav)
                if r >= SILENCE_RMS:
                    ok += 1; print(f"     OK rms={r:.0f} -> {out_wav.name}")
                else:
                    bad += 1; print("     FEHLGESCHLAGEN")
                leg.append(f"  {voice} {suf}) {txt}")
                time.sleep(1.2)
        leg.append("")
    (OUT / "LIESMICH.txt").write_text("\n".join(leg), encoding="utf-8")
    print(f"\nFertig: {ok} OK, {bad} fehlgeschlagen -> {OUT}")


if __name__ == "__main__":
    main()
