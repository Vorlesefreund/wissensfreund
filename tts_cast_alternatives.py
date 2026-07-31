#!/usr/bin/env python3
"""tts_cast_alternatives.py — Alternativ-Stimmen nach PO-Hörfeedback (2026-07-19).

Rendert je Figur mehrere Stimm-KANDIDATEN in 2 Szenen, mit RMS-Stille-Check
(stille/leere Antworten werden neu versucht) und OHNE Gedankenstriche (die den
Gemini-TTS-Leer-Glitch auslösen können).

  set -a; source .env; set +a
  python -X utf8 tts_cast_alternatives.py
Ausgabe: C:/Users/Andreas/Desktop/_stimmen_cast_alt_20260719/  (+ LIESMICH.txt)
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
SILENCE_RMS = 150   # unter diesem RMS gilt der Clip als stumm/kaputt
OUT = Path("C:/Users/Andreas/Desktop/_stimmen_cast_alt_20260719")

# figur, scene(style), [szene_a, szene_b], [kandidaten-stimmen]
JOBS = [
    ("Oma_Rosa",
     "Sprich als herzliche, sanfte Großmutter mit etwas tieferer, voller Stimme: warm, ruhig, liebevoll.",
     ["Weißt du, mein Schatz, als ich so klein war wie du, da gab es das alles noch gar nicht. Wir haben den ganzen Tag draußen gespielt.",
      "Komm, setz dich zu mir. Ich zeig dir etwas Schönes. Siehst du das hier? Das erzähl ich dir jetzt ganz in Ruhe."],
     ["Sulafat", "Achernar"]),
    ("Opa_Karl",
     "Sprich als sehr gutmütiger, älterer Herr mit tiefer, ruhiger Stimme: warm, geduldig, gelassen.",
     ["Gute Frage, mein Junge. Da muss ich einen Moment überlegen. Also, das ist nämlich so. Es fängt ganz von vorne an.",
      "Nicht so schnell. Lass uns das in Ruhe anschauen, Schritt für Schritt. Dann verstehst du es ganz bestimmt."],
     ["Enceladus", "Rasalgethi"]),
    ("Meeresbiologin_Ronja",
     "Sprich als warmherzige, lebendige Meeresbiologin: zugewandt und begeistert, klar und freundlich, nicht mystisch.",
     ["Schau mal, wer da kommt! Das ist ein junger Tümmler. Der ist heute besonders neugierig und schwimmt ganz nah an unser Boot heran.",
      "Komm, wir tauchen ab. Da unten wartet eine ganze Wunderwelt auf uns, voller Farben und seltsamer Tiere."],
     ["Callirrhoe", "Laomedeia"]),
    ("Forscherin_Nele",
     "Sprich als begeisterte Museums-Forscherin: klar, präzise, voller Faszination für Details.",
     ["Faszinierend, nicht wahr? Schau ganz genau hin. Siehst du diese feinen Linien? Die sind über fünfhundert Jahre alt.",
      "Jedes Stück hier erzählt eine Geschichte. Man muss nur genau hinsehen, dann verrät es sein Geheimnis."],
     ["Pulcherrima"]),
    ("Erfinder_Rudi",
     "Sprich als aufgeregter Werkstatt-Erfinder mit tieferer Männerstimme: lebhaft, voller Tatendrang, aber nicht hoch.",
     ["Probieren wir's einfach aus! Ein Dreh hier, eine Schraube da, und dann schauen wir, ob es läuft!",
      "Ha, siehst du das? Es funktioniert! Genau so hab ich mir das vorgestellt. Wusste ich's doch!"],
     ["Algieba", "Zubenelgenubi"]),
    ("Weltenbummler_Tom",
     "Sprich als reiselustiger Weltenbummler: lebhaft und weltgewandt, immer bereit für das nächste Abenteuer.",
     ["Komm, wir reisen hin! Meine Karte hab ich schon dabei. Von hier sind es viele tausend Kilometer, aber die Reise lohnt sich, versprochen!",
      "Diese Stadt ist etwas ganz Besonderes. Überall enge Gassen, kleine Brücken über dem Wasser, und mittendrin ein riesiger Platz."],
     ["Umbriel", "Orus"]),
    ("Chronist_Wilhelm",
     "Sprich als alter Chronist und Geschichtenerzähler: feierlich und warm, als läse er aus einem alten Buch, in zügigem, lebendigem Tempo, nicht schleppend.",
     ["Vor langer, langer Zeit, so beginnt diese Geschichte, lebte ein Mann, von dem noch heute die ganze Welt spricht. Hör gut zu.",
      "Und in diesem Augenblick, als alle schon aufgegeben hatten, geschah etwas, das niemand für möglich gehalten hätte."],
     ["Algenib"]),
    ("Naturfuehrerin_Hanna",
     "Sprich als aufmerksame Naturführerin draußen: sanft, leise, achtsam.",
     ["Schau mal hier unten, ganz vorsichtig. Diese kleine Pflanze gibt es nur an ganz wenigen Orten auf der ganzen Welt."],
     ["Aoede"]),
]


def _rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    a = array.array("h"); a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


def synth(client, voice, scene, text, out_wav):
    """Rendert; verwirft stille/leere Antworten und versucht erneut (bis 6x)."""
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
                print(f"    Versuch {attempt+1}: STUMM (rms {r:.0f}) — neu")
                time.sleep(4); continue
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
            return r
        except Exception as e:
            print(f"    Versuch {attempt+1}: leer ({str(e)[:40]}) — neu")
            time.sleep(4)
    return 0.0


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY fehlt (.env).")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    OUT.mkdir(parents=True, exist_ok=True)
    leg = ["STORY-CAST — Alternativ-Stimmen (PO-Feedback 2026-07-19)",
           "Dateiname: Figur__Stimme_a|b.wav\n"]
    ok = bad = 0
    for figur, scene, szenen, voices in JOBS:
        leg.append(f"### {figur}")
        for voice in voices:
            leg.append(f"  Stimme {voice}:")
            for i, txt in enumerate(szenen):
                suf = "ab"[i]
                out_wav = OUT / f"{figur}__{voice}_{suf}.wav"
                print(f"[{figur} / {voice} / {suf}] …")
                r = synth(client, voice, scene, txt, out_wav)
                if r >= SILENCE_RMS:
                    ok += 1; print(f"     OK rms={r:.0f} -> {out_wav.name}")
                else:
                    bad += 1; print("     FEHLGESCHLAGEN")
                leg.append(f"    {suf}) {txt}")
                time.sleep(1.2)
        leg.append("")
    (OUT / "LIESMICH.txt").write_text("\n".join(leg), encoding="utf-8")
    print(f"\nFertig: {ok} OK, {bad} fehlgeschlagen -> {OUT}")


if __name__ == "__main__":
    main()
