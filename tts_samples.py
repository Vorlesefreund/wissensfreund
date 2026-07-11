#!/usr/bin/env python3
"""tts_samples.py — kurze Stimmen-Hörproben für den Story-Modus-Cast.
Rendert je Charakter eine WAV mit eigener Prebuilt-Stimme + Style-Vorspann.

  python -X utf8 tts_samples.py
Ausgabe: C:/Users/Andreas/Desktop/_stimmen_proben/NN_Rolle_Stimme.wav
"""
from __future__ import annotations
import os, sys, time, wave
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent / ".env")

TTS_MODEL   = "gemini-3.1-flash-tts-preview"
SAMPLE_RATE = 24000
OUT = Path("C:/Users/Andreas/Desktop/_stimmen_proben")

# (Nr, Rolle, Stimme, Eigenart, Style-Vorspann, Beispielzeile)
CAST = [
    ("01", "Professor (Erzähler)", "Iapetus",
     "warme Rahmung, leises Schmunzeln",
     "Sprich als warmer, kluger Professor und Vorlese-Erzähler: ruhig, deutlich, mit einem leisen Schmunzeln.",
     "Willkommen zu einer neuen Geschichte! Heute gehen wir auf eine kleine Reise. Schnall dich an — es wird spannend."),
    ("02", "Mia (Mädchen, ~7)", "Leda",
     "fragt immer nach dem Warum, staunt laut",
     "Sprich als neugieriges Mädchen von etwa sieben Jahren: helle, lebhafte Kinderstimme, staunend.",
     "Wow! Und warum ist das so, Opa? Das will ich ganz genau wissen!"),
    ("03", "Mio (Junge, ~7)", "Puck",
     "will alles anfassen und ausprobieren",
     "Sprich als aufgewecktes Kind, ein Junge von etwa sieben Jahren: energiegeladen und begeistert.",
     "Zeig mal her! Darf ich das anfassen? Ich will wissen, wie es funktioniert!"),
    ("04", "Oma", "Vindemiatrix",
     "erzählt von früher, sagt mein Schatz",
     "Sprich als herzliche, sanfte Großmutter: warm, ruhig, liebevoll.",
     "Weißt du, mein Schatz, früher, als ich klein war, da war das noch ganz anders."),
    ("05", "Opa", "Gacrux",
     "geduldig, sagt Gute Frage",
     "Sprich als warmer, geduldiger Großvater: ruhig und erklärend, mit einem Lächeln in der Stimme.",
     "Gute Frage! Da muss ich einen Moment überlegen. Also, das ist nämlich so."),
    ("06", "Tierpflegerin Nadia", "Autonoe",
     "kennt jedes Tier beim Namen, leise",
     "Sprich als freundliche junge Tierpflegerin: zugewandt und klar, bei scheuen Tieren leise.",
     "Pssst, ganz leise. Das ist Emma, unsere Robbe. Sie ist heute ein bisschen schüchtern."),
    ("07", "Museums-Forscherin", "Kore",
     "präzise, sagt Faszinierend",
     "Sprich als begeisterte Museums-Forscherin: klar, präzise, voller Faszination für Details.",
     "Faszinierend, nicht wahr? Schau ganz genau hin — jedes kleine Detail erzählt eine Geschichte."),
    ("08", "Werkstatt-Erfinder", "Fenrir",
     "bastelt, probiert alles aus",
     "Sprich als aufgeregter Werkstatt-Erfinder: lebhaft, voller Tatendrang.",
     "Probieren wir's einfach aus! Ein Dreh hier, ein Klick da — und tada, es läuft!"),
    ("09", "Naturführerin", "Aoede",
     "leise, aufmerksam, horcht genau",
     "Sprich als aufmerksame Naturführerin draußen: sanft, leise, achtsam.",
     "Pssst… hörst du das? Ganz still. Da hinten, zwischen den Blättern, bewegt sich etwas."),
    ("10", "Meeresbiologin", "Despina",
     "ruhiger Tiefsee-Ton",
     "Sprich als ruhige Meeresbiologin: weich und gelassen, wie unter Wasser.",
     "Tief unten, wo es dunkel und still ist, leben die allerseltsamsten Tiere des Meeres."),
    ("11", "Sternwarten-Opa", "Charon",
     "blickt in die Ferne, staunt über Größe",
     "Sprich als weiser Sternwarten-Großvater: tief, ruhig, staunend über die Weite des Himmels.",
     "Schau nach oben, in die Nacht. Jeder kleine Punkt da oben ist eine ganze, riesige Sonne."),
]


def synth(client, voice, scene, text, out_wav):
    prompt = f"{scene}\n\n{text}"
    for attempt in range(3):
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
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
            return True
        except Exception as e:
            print(f"    Retry {attempt+1}: {str(e)[:70]}")
            time.sleep(6)
    return False


def main():
    if "GEMINI_API_KEY" not in os.environ:
        sys.exit("GEMINI_API_KEY fehlt (.env).")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    OUT.mkdir(parents=True, exist_ok=True)
    for nr, rolle, voice, eigenart, scene, line in CAST:
        safe = rolle.split("(")[0].strip().replace(" ", "_").replace("/", "-")
        out_wav = OUT / f"{nr}_{safe}_{voice}.wav"
        print(f"[{nr}] {rolle:24} Stimme={voice:14} …")
        ok = synth(client, voice, scene, line, out_wav)
        print(f"    {'OK -> ' + out_wav.name if ok else 'FEHLGESCHLAGEN'}")
        time.sleep(1.5)
    print(f"\nFertig -> {OUT}")


if __name__ == "__main__":
    main()
