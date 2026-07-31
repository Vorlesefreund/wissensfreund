#!/usr/bin/env python3
"""tts_cast_samples.py — je 2 mittellange Hörproben pro Story-Cast-Figur.

Rendert für jede feste Figur ZWEI Szenen (unterschiedliche Situationen) mit
derselben Prebuilt-Stimme + Eigenart-Style, damit der PO die Person in
verschiedenen Lagen hört und Stimme/Charakter beurteilen kann.

Namen fixiert 2026-07-19; Stimmen der 5 neuen Figuren sind KANDIDATEN (PO
entscheidet per Ohr — Stimme in CAST tauschen und neu rendern).

  set -a; source .env; set +a
  python -X utf8 tts_cast_samples.py
Ausgabe: C:/Users/Andreas/Desktop/_stimmen_cast_20260719/NN_Name_Stimme_a|b.wav  (+ LIESMICH.txt)
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
OUT = Path("C:/Users/Andreas/Desktop/_stimmen_cast_20260719")

# nr, name, voice, kandidat?, eigenart, style-scene, [szene1, szene2]
CAST = [
    ("01", "Professor", "Iapetus", False, "Erzähler — warme Rahmung, leises Schmunzeln",
     "Sprich als warmer, kluger Professor und Vorlese-Erzähler: ruhig, deutlich, mit einem leisen Schmunzeln.",
     ["Willkommen zu einer neuen Geschichte! Heute reisen wir tief hinunter ans dunkle Ende des Meeres. Halt dich gut fest — es wird spannend.",
      "Und während die Sonne langsam unterging, wusste der kleine Theo: Diesen Tag würde er nie vergessen. Aber das ist eine Geschichte für morgen."]),
    ("02", "Mia", "Leda", False, "Mädchen ~7 — fragt Warum, staunt laut",
     "Sprich als neugieriges Mädchen von etwa sieben Jahren: helle, lebhafte Kinderstimme, staunend.",
     ["Wow! Ist der echt so groß? Größer als ein ganzes Haus? Das gibt's doch gar nicht!",
      "Aber warum macht der das denn, Oma? Und woher weiß der das? Das will ich ganz genau wissen!"]),
    ("03", "Theo", "Puck", False, "Junge ~7 — will alles anfassen, „Zeig mal!“",
     "Sprich als aufgewecktes Kind, ein Junge von etwa sieben Jahren: energiegeladen und begeistert.",
     ["Zeig mal her! Darf ich das anfassen? Wie fühlt sich das an — ganz glatt oder kratzig?",
      "Cool! Das will ich auch mal ausprobieren! Komm, machen wir das nochmal, bitte, bitte!"]),
    ("04", "Oma_Rosa", "Vindemiatrix", False, "erzählt von früher, „mein Schatz“",
     "Sprich als herzliche, sanfte Großmutter: warm, ruhig, liebevoll.",
     ["Weißt du, mein Schatz, als ich so klein war wie du, da gab es das alles noch gar nicht. Wir haben den ganzen Tag draußen gespielt.",
      "Komm, setz dich zu mir. Ich zeig dir was Schönes. Siehst du das hier? Das erzähl ich dir jetzt ganz in Ruhe."]),
    ("05", "Opa_Karl", "Gacrux", False, "geduldig, „Gute Frage!“",
     "Sprich als warmer, geduldiger Großvater: ruhig und erklärend, mit einem Lächeln in der Stimme.",
     ["Gute Frage! Da muss ich einen Moment überlegen. Also, das ist nämlich so: Es fängt ganz von vorne an.",
      "Nicht so schnell, mein Junge. Lass uns das Schritt für Schritt anschauen, dann verstehst du es ganz bestimmt."]),
    ("06", "Tierpflegerin_Nadia", "Autonoe", False, "kennt jedes Tier, bei scheuen leise",
     "Sprich als freundliche junge Tierpflegerin: zugewandt und klar, bei scheuen Tieren leise.",
     ["Pssst, ganz leise. Das ist Emma, unsere Robbe. Sie ist heute ein bisschen schüchtern, also bewegen wir uns langsam.",
      "So, jetzt gibt's Frühstück! Jeder hier bekommt genau das, was er braucht. Schau, wie vorsichtig sie den Fisch nimmt."]),
    ("07", "Forscherin_Nele", "Kore", False, "präzise, „Faszinierend!“",
     "Sprich als begeisterte Museums-Forscherin: klar, präzise, voller Faszination für Details.",
     ["Faszinierend, nicht wahr? Schau ganz genau hin. Siehst du diese feinen Linien? Die sind über fünfhundert Jahre alt.",
      "Jedes Stück hier erzählt eine Geschichte. Man muss nur genau hinsehen — dann verrät es sein Geheimnis."]),
    ("08", "Erfinder_Rudi", "Fenrir", False, "bastelt, „Probieren wir's aus!“",
     "Sprich als aufgeregter Werkstatt-Erfinder: lebhaft, voller Tatendrang.",
     ["Probieren wir's einfach aus! Ein Dreh hier, eine Schraube da — und dann schauen wir, ob es läuft!",
      "Ha! Siehst du das? Es funktioniert! Genau so hab ich mir das vorgestellt. Wusste ich's doch!"]),
    ("09", "Naturfuehrerin_Hanna", "Aoede", False, "leise, „Hörst du das?“",
     "Sprich als aufmerksame Naturführerin draußen: sanft, leise, achtsam.",
     ["Pssst… hörst du das? Ganz still jetzt. Da hinten, zwischen den Blättern, bewegt sich etwas.",
      "Schau mal hier unten, ganz vorsichtig. Diese kleine Pflanze — die gibt es nur an ganz wenigen Orten auf der Welt."]),
    ("10", "Meeresbiologin_Ronja", "Despina", False, "ruhiger Tiefsee-Ton",
     "Sprich als ruhige Meeresbiologin: weich und gelassen, wie unter Wasser.",
     ["Tief unten, wo es dunkel und still ist, leben die allerseltsamsten Tiere des Meeres. Manche leuchten sogar von ganz allein.",
      "Sieh nur, wie ruhig er durchs Wasser gleitet. Er hat es nicht eilig — hier unten hat niemand es eilig."]),
    ("11", "Astronom_Aris", "Charon", False, "staunt über Größe und Weite",
     "Sprich als weiser Astronom an der Sternwarte: tief, ruhig, staunend über die Weite des Himmels.",
     ["Schau nach oben, in die Nacht. Jeder kleine Punkt da oben ist eine ganze, riesige Sonne. Und viele davon sind längst erloschen.",
      "Das Licht dieses Sterns war so lange unterwegs, dass es losflog, als es die Dinosaurier noch gab. Kannst du dir das vorstellen?"]),
    ("12", "Arzt_Dr_Samir", "Sadaltager", True, "ruhig-beruhigend, Stethoskop",
     "Sprich als ruhiger, freundlicher Arzt: warm und beruhigend, nimmt jede Sorge ernst.",
     ["Keine Sorge, das tut gar nicht weh. Ich hör nur ganz kurz mit meinem Stethoskop, wie dein Herz schlägt. Ganz ruhig.",
      "Dein Körper ist wie eine kleine, kluge Maschine. Alles darin hat eine Aufgabe — und jetzt schauen wir uns an, wie das funktioniert."]),
    ("13", "Lehrerin_Clara", "Erinome", True, "macht Abstraktes greifbar, ermutigend",
     "Sprich als freundliche, klare Lehrerin: geduldig und ermutigend, macht schwierige Dinge einfach.",
     ["Zahlen sind gar nicht schwer. Stell dir drei Äpfel vor. Kommen zwei dazu — wie viele sind es dann? Genau, wir zählen zusammen.",
      "Fast! Ganz nah dran. Kein Problem, das üben wir einfach nochmal. Ich weiß genau, dass du das schaffst."]),
    ("14", "Chronist_Wilhelm", "Algenib", True, "erzählt wie aus einem alten Buch (STATUS: PO offen)",
     "Sprich als alter Chronist und Geschichtenerzähler: feierlich und warm, als läse er aus einem dicken alten Buch.",
     ["Vor langer, langer Zeit — so beginnt diese Geschichte — lebte ein Mann, von dem noch heute die ganze Welt spricht. Hör gut zu.",
      "Und in diesem Augenblick, als alle schon aufgegeben hatten, geschah etwas, das niemand für möglich gehalten hätte."]),
    ("15", "Weltenbummler_Tom", "Sadachbia", True, "Karte dabei, „Komm, wir reisen hin!“",
     "Sprich als reiselustiger Weltenbummler: lebhaft und weltgewandt, immer bereit für das nächste Abenteuer.",
     ["Komm, wir reisen hin! Meine Karte hab ich schon dabei. Von hier sind es viele tausend Kilometer — aber die Reise lohnt sich, versprochen!",
      "Diese Stadt ist etwas Besonderes: überall enge Gassen, kleine Brücken über dem Wasser — und mittendrin ein Platz, so groß wie zehn Fußballfelder."]),
    ("16", "Nachbar_Toni", "Achird", True, "universell, „da weiß ich was!“",
     "Sprich als freundlicher, kluger Nachbar: unkompliziert und neugierig, weiß zu fast allem etwas.",
     ["Na, was habt ihr denn da für eine Frage? Wartet mal — da weiß ich doch was! Kommt rüber, ich zeig's euch.",
      "Übrigens, wusstet ihr das schon? Das ist wirklich verblüffend, wenn man einmal versteht, wie es zusammenhängt. Passt auf…"]),
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
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY fehlt (.env).")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    OUT.mkdir(parents=True, exist_ok=True)

    legende = ["STORY-CAST — Hörproben (je 2 Szenen, 2026-07-19)",
               "Stimmen mit (Kandidat) sind noch nicht per Ohr bestätigt.\n"]
    ok_n = fail_n = 0
    for nr, name, voice, kandidat, eigenart, scene, szenen in CAST:
        tag = " (Stimm-KANDIDAT)" if kandidat else ""
        legende.append(f"[{nr}] {name}  ·  Stimme {voice}{tag}  ·  {eigenart}")
        for i, txt in enumerate(szenen):
            suffix = "ab"[i]
            out_wav = OUT / f"{nr}_{name}_{voice}_{suffix}.wav"
            print(f"[{nr}{suffix}] {name:24} {voice:14} …")
            if synth(client, voice, scene, txt, out_wav):
                ok_n += 1; print(f"     OK -> {out_wav.name}")
            else:
                fail_n += 1; print("     FEHLGESCHLAGEN")
            legende.append(f"    {suffix}) {txt}")
            time.sleep(1.2)
        legende.append("")
    (OUT / "LIESMICH.txt").write_text("\n".join(legende), encoding="utf-8")
    print(f"\nFertig: {ok_n} OK, {fail_n} fehlgeschlagen -> {OUT}")


if __name__ == "__main__":
    main()
