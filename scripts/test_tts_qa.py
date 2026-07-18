#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_tts_qa.py — sichert das Qualitäts-Gate (tts_qa) und seine Verdrahtung.

Die reinen Rechenregeln (Pegel, Sprechzeit, Zahl-Normalisierung, Ähnlichkeit) laufen IMMER —
kein Netz, kein Modell. Die Whisper-Prüfungen laufen nur, wenn echte Produktions-PCMs im Repo
liegen (articles/leo_batch_20260716/pcm_cache) — sonst werden sie sauber übersprungen statt
falsch grün zu melden.

    python -X utf8 scripts/test_tts_qa.py

Kalibrierbasis: 24 echte Turns, 2026-07-17. Siehe Modul-Docstring von tts_qa.
"""
import json, sys, tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import tts_qa as Q

fails = []
def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond: fails.append(name)

def ton(sekunden: float, amplitude: int = 3000) -> bytes:
    """Synthetischer „Sprach"-Ton — laut genug, dass der Stille-Trim ihn als Sprache zählt."""
    import array, math
    n = int(Q.SAMPLE_RATE * sekunden)
    a = array.array("h", (int(amplitude * math.sin(2 * math.pi * 220 * i / Q.SAMPLE_RATE))
                          for i in range(n)))
    return a.tobytes()

print("\n1) Pegel + Sprechzeit (ohne Whisper, reine Rechnung)")
check("Stille -> RMS ~0", Q.rms(b"\x00\x00" * 24000) < 1)
check("Ton -> RMS deutlich ueber Schwelle", Q.rms(ton(1.0)) > Q.MIN_RMS * 5, f"{Q.rms(ton(1.0)):.0f}")
check("Stille zaehlt NICHT als Sprechzeit", Q.sprech_sekunden(b"\x00\x00" * 24000 * 3) == 0.0)
check("1s Ton ~= 1s Sprechzeit", abs(Q.sprech_sekunden(ton(1.0)) - 1.0) < 0.1,
      f"{Q.sprech_sekunden(ton(1.0)):.2f}")
# Der Kern des Stille-Trims: 0,5 s Sprache in 5 s Datei -> Sprechzeit 0,5 s, nicht 5 s.
gemischt = ton(0.5) + b"\x00\x00" * int(Q.SAMPLE_RATE * 4.5)
check("Trim: 0,5s Sprache in 5s Datei", abs(Q.sprech_sekunden(gemischt) - 0.5) < 0.1,
      f"{Q.sprech_sekunden(gemischt):.2f}")

print("\n2) Zahl-Normalisierung (sonst Fehlalarm bei jeder Jahreszahl)")
# Whisper schreibt Ziffern, die Quelle schreibt aus — real gemessen an "vor ueber fuenfhundert Jahren".
check("'fünfhundert' == '500'", Q.aehnlichkeit("vor über fünfhundert Jahren",
                                               "vor über 500 Jahren") > 0.95,
      f"{Q.aehnlichkeit('vor über fünfhundert Jahren', 'vor über 500 Jahren'):.2f}")
check("'zwei' == '2'", Q.aehnlichkeit("er hat zwei Hände", "er hat 2 Hände") > 0.95)
check("Interpunktion egal", Q.aehnlichkeit("Das ist die Mona Lisa.", "das ist die mona lisa") > 0.98)
check("verhoerter Eigenname bleibt ueber der Schwelle (kein Fehlalarm)",
      Q.aehnlichkeit("Oma Rina lacht.", "O Marina lacht.") >= Q.MIN_AEHNLICHKEIT,
      f"{Q.aehnlichkeit('Oma Rina lacht.', 'O Marina lacht.'):.2f}")
check("voellig anderer Text faellt durch (der zip-Bug)",
      Q.aehnlichkeit("Warum hat er das gemacht?", "Hat er auch Maschinen gebaut?") < Q.MIN_AEHNLICHKEIT,
      f"{Q.aehnlichkeit('Warum hat er das gemacht?', 'Hat er auch Maschinen gebaut?'):.2f}")

print("\n3) pruefe() faengt die billigen Faelle OHNE Whisper")
ok, g = Q.pruefe(None, "egal", mit_whisper=False)
check("kein Audio -> abgelehnt", not ok and "kein Audio" in g, g)
ok, g = Q.pruefe(b"\x00\x00" * 24000 * 3, "Er hat nicht vier Arme, Theo.", mit_whisper=False)
check("3s Stille -> abgelehnt", not ok, g)
ok, g = Q.pruefe(ton(0.1), "Hallo", mit_whisper=False)
check("zu kurz -> abgelehnt", not ok, g)
# Der reale Defekt vom 16.07.: 54 s Datei, praktisch stumm, gueltiger Audio-Blob.
ok, g = Q.pruefe(b"\x01\x00" * int(Q.SAMPLE_RATE * 54), "Er hat nicht vier Arme, Theo. " * 3,
                 mit_whisper=False)
check("54s Stille (realer Defekt) -> abgelehnt", not ok, g)
ok, g = Q.pruefe(ton(4.0), "Dies sind sieben Woerter in Folge", mit_whisper=False)
check("plausibler Ton+Text -> durch", ok, g)
ok, g = Q.pruefe(ton(40.0), "Drei kurze Woerter", mit_whisper=False)
check("40s fuer 3 Woerter -> abgelehnt (Dehnungs-Schleife)", not ok, g)

print("\n4) Verdrahtung: durchgefallenes Audio wird NICHT gecacht")
import tts_story as T
import tts_batch as B
cache = Path(tempfile.mkdtemp())
req = B.TtsRequest.build(voice="Puck", text="Hallo Welt", temperature=0.3)
T.synth_pcm = lambda *a, **kw: b"\x00\x00" * 2400          # immer Ausschuss (Stille)
pcm = T._sync_pcm_cached(None, cache, req, "Puck", "", "Hallo Welt", 0.3,
                         qa=lambda p, t: (False, "Testausschuss"))
check("Ausschuss -> kein PCM zurueck", pcm is None)
check("Ausschuss -> NICHTS im Cache (kein vergifteter Cache)",
      not (cache / f"{req.key}.pcm").exists())
gut = ton(1.0)
T.synth_pcm = lambda *a, **kw: gut
pcm = T._sync_pcm_cached(None, cache, req, "Puck", "", "Hallo Welt", 0.3,
                         qa=lambda p, t: (True, ""))
check("sauberes Audio -> gecacht", (cache / f"{req.key}.pcm").exists())
rufe = []
T.synth_pcm = lambda *a, **kw: rufe.append(1) or gut
T._sync_pcm_cached(None, cache, req, "Puck", "", "Hallo Welt", 0.3, qa=lambda p, t: (True, ""))
check("Cache-Treffer -> kein neuer Call", len(rufe) == 0, str(len(rufe)))

print("\n5) Whisper gegen ECHTE Produktions-Turns")
CD = REPO / "articles" / "leo_batch_20260716" / "pcm_cache"
idx_p = CD / "_index.json"
if not idx_p.exists():
    print("  uebersprungen — keine echten PCMs im Repo (articles/leo_batch_20260716/pcm_cache)")
else:
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    paare = [(k, v) for k, v in idx.items() if (CD / f"{k}.pcm").exists()]
    echte = [(k, v) for k, v in paare if Q.rms((CD / f"{k}.pcm").read_bytes()) > 500]
    kaputt = [(k, v) for k, v in paare if Q.rms((CD / f"{k}.pcm").read_bytes()) <= 500]
    print(f"  ({len(echte)} intakte + {len(kaputt)} defekte Turns gefunden)")
    # "Echt" heisst hier nur RMS>500. Der alte Cache enthaelt auch stille-lastige Turns (z.B.
    # "Wer ist das?" 80% Stille) — die DUERFEN abgelehnt werden, SOLANGE der Trim sie rettet.
    # Ein echter Fehlalarm waere: abgelehnt UND auch nach Trim noch kaputt.
    fehlalarme = []
    for k, v in echte[:8]:
        pcm = (CD / f"{k}.pcm").read_bytes()
        ok, g = Q.pruefe(pcm, v["text"])
        if not ok:
            ok2, g2 = Q.pruefe(Q.trim_stille(pcm), v["text"])
            if not ok2: fehlalarme.append((v["text"][:40], g, g2))
    check("KEIN echter Fehlalarm (abgelehnt UND Trim rettet nicht)", not fehlalarme, str(fehlalarme[:2]))
    for k, v in kaputt:
        ok, g = Q.pruefe((CD / f"{k}.pcm").read_bytes(), v["text"])
        check(f"realer Defekt erkannt ({v['text'][:28]}…)", not ok, g)
    if len(echte) >= 2:
        (k1, v1), (k2, v2) = echte[0], echte[1]
        ok, g = Q.pruefe((CD / f"{k2}.pcm").read_bytes(), v1["text"])
        check("vertauschtes Audio erkannt (zip-Bug)", not ok, g)

# ── 6) Zuordnung Request→Antwort (der zip-Bug) ────────────────────────────────
print("\n6) Zuordnung per metadata statt per Reihenfolge (zip-Bug an der Wurzel)")
import tts_batch as B2
from types import SimpleNamespace as NS

r1 = B2.TtsRequest.build(voice="Iapetus", text="Turn eins")
r2 = B2.TtsRequest.build(voice="Puck",    text="Turn zwei")
r3 = B2.TtsRequest.build(voice="Gacrux",  text="Turn drei")
offen = [r1, r2, r3]

# Fall A: API antwortet in ANDERER Reihenfolge → metadata rettet die Zuordnung.
resp = [NS(metadata={"key": r3.key}, response="C", error=None),
        NS(metadata={"key": r1.key}, response="A", error=None),
        NS(metadata={"key": r2.key}, response="B", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
zuordnung = {r.key: rw.response for r, rw in paare}
check("vertauschte Reihenfolge -> per metadata korrekt zugeordnet",
      zuordnung == {r1.key: "A", r2.key: "B", r3.key: "C"}, str(zuordnung))
check("nichts faelschlich als fehlend gemeldet", ohne == [])

# Fall B: der eigentliche Bug — mittlere Antwort FEHLT. zip haette r3 das Audio von r2 gegeben.
resp = [NS(metadata={"key": r1.key}, response="A", error=None),
        NS(metadata={"key": r3.key}, response="C", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
zuordnung = {r.key: rw.response for r, rw in paare}
check("fehlende Antwort -> KEIN Verrutschen (r3 behaelt C)",
      zuordnung == {r1.key: "A", r3.key: "C"}, str(zuordnung))
check("fehlender Request kommt in die naechste Runde", [r.key for r in ohne] == [r2.key])

# Fall C: kein metadata, Anzahl passt -> Reihenfolge ist vertretbar.
resp = [NS(metadata=None, response="A", error=None),
        NS(metadata=None, response="B", error=None),
        NS(metadata=None, response="C", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
check("ohne metadata + Anzahl passt -> Reihenfolge", [rw.response for _, rw in paare] == ["A","B","C"])

# Fall D: kein metadata UND Anzahl passt nicht -> raten ist verboten.
resp = [NS(metadata=None, response="A", error=None),
        NS(metadata=None, response="B", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
check("ohne metadata + Anzahl falsch -> NICHTS zuordnen", paare == [])
check("ohne metadata + Anzahl falsch -> alles in die naechste Runde", len(ohne) == 3)

# ── 7) Eskalationsleiter ──────────────────────────────────────────────────────
print("\n7) Eskalationsleiter (statt 10x denselben Request zu schicken)")
L = B2.eskalationsleiter(0.3)
check("10 Runden bei Basis 0.3", len(L) == 10, str(len(L)))
check("Runde 1+2: unveraendert 0.3 mit Stil", L[0] == (0.3, False) and L[1] == (0.3, False), str(L[:2]))
check("Runde 3+4: 0.3 OHNE Stil (Betonung bleibt!)", L[2] == (0.3, True) and L[3] == (0.3, True), str(L[2:4]))
check("Runde 5+6: temperature 0.5", L[4] == (0.5, False) and L[5] == (0.5, False), str(L[4:6]))
check("Runde 7+8: temperature 0.6", L[6] == (0.6, False) and L[7] == (0.6, False), str(L[6:8]))
check("Runde 9+10: default (laeuft nachweislich immer)", L[8] == (None, False) and L[9] == (None, False), str(L[8:]))
check("Bare-Stufe kommt VOR jeder temperature-Aenderung (PO-Kriterium zuletzt opfern)",
      L.index((0.3, True)) < min(i for i, s in enumerate(L) if s[0] != 0.3))
L06 = B2.eskalationsleiter(0.6)
check("Basis 0.6: keine Stufe unter/gleich 0.6 doppelt", (0.5, False) not in L06 and (0.6, False) not in L06[2:], str(L06[:6]))
Ld = B2.eskalationsleiter(None)
check("Basis default: nichts zu eskalieren", set(Ld) == {(None, False)}, str(set(Ld)))

# Emotions-Turn: der Stil-Präfix TRÄGT die Emotion (Lachen, ernster Ton). Deshalb erst die
# temperature hochziehen (Präfix behalten) und den Präfix ganz zuletzt opfern — umgekehrt zur
# emotionslosen Leiter. Belegt am 17.07.: „Oma Rina lacht" verlor sonst ihr Lachen.
Le = B2.eskalationsleiter(0.3, hat_emotion=True)
check("Emotion: 10 Runden bei Basis 0.3", len(Le) == 10, str(len(Le)))
check("Emotion Runde 1+2: 0.3 MIT Stil (Emotion + Betonung)", Le[0] == (0.3, False) and Le[1] == (0.3, False), str(Le[:2]))
check("Emotion Runde 3+4: temperature 0.5, Präfix bleibt", Le[2] == (0.5, False) and Le[3] == (0.5, False), str(Le[2:4]))
check("Emotion Runde 5+6: temperature 0.6, Präfix bleibt", Le[4] == (0.6, False) and Le[5] == (0.6, False), str(Le[4:6]))
check("Emotion Runde 7+8: JETZT erst 0.3 ohne Stil", Le[6] == (0.3, True) and Le[7] == (0.3, True), str(Le[6:8]))
check("Emotion Runde 9+10: default", Le[8] == (None, False) and Le[9] == (None, False), str(Le[8:]))
check("Emotion: Präfix-Opfer kommt NACH jeder temperature-Anhebung (Emotion so lang wie möglich halten)",
      Le.index((0.3, True)) > max(i for i, s in enumerate(Le) if s[0] in (0.5, 0.6)))
check("Ohne vs. mit Emotion: gegenläufige Reihenfolge des Präfix-Opfers",
      B2.eskalationsleiter(0.3, hat_emotion=False).index((0.3, True))
      < B2.eskalationsleiter(0.3, hat_emotion=True).index((0.3, True)))

print("\n7d) batch_synthesize: JEDER Turn folgt SEINER Leiter (Fehler 2, 17.07.)")
# Zwei Turns in EINEM Lauf, die beide Runde 1 scheitern, aber verschieden gerettet werden müssen:
#   - Emotions-Turn („Oma lacht") darf den Präfix NICHT verlieren → muss über temperature 0.5 kommen.
#   - Erzähler (keine Emotion) darf temperature NICHT ändern → muss über „ohne Präfix" bei 0.3 kommen.
# Vor dem Fix folgten beide derselben globalen Stufe — der Emotions-Turn verlor sein Lachen.
r_erz  = B2.TtsRequest.build(voice="Iapetus", text="Theo schaut auf das Bild.",
                             style="STILMARKE_ERZ Sprich ruhig.", temperature=0.3, hat_emotion=False)
r_emo  = B2.TtsRequest.build(voice="Vindemiatrix", text="Oma Rina lacht herzlich.",
                             style="STILMARKE_LACH Sprich amüsiert und lachend.", temperature=0.3,
                             hat_emotion=True)

def _resp_fuer(ireq):
    """Entscheidet je gesendetem Versuch, ob er 'durchkommt' — nach Identität + Stufe."""
    md = ireq.metadata or {}
    contents = ireq.contents or ""
    temp = getattr(ireq.config, "temperature", None)
    ist_bare = "STILMARKE" not in contents          # Präfix wurde weggelassen
    if "Theo schaut" in contents:                   # Erzähler: nur OHNE Präfix (0.3 bleibt)
        gut = ist_bare
    else:                                            # Emotion: nur mit ANGEHOBENER temperature
        gut = (temp is not None and temp >= 0.5) and not ist_bare
    pcm = ton(1.2) if gut else None
    if pcm is None:
        cand = NS(content=NS(parts=None), finish_reason="OTHER")
    else:
        cand = NS(content=NS(parts=[NS(inline_data=NS(data=pcm))]), finish_reason="STOP")
    return NS(metadata=md, error=None, response=NS(prompt_feedback=None, candidates=[cand]))

class _FakeBatches:
    def __init__(self): self._last = None
    def create(self, model=None, src=None):
        self._last = [_resp_fuer(ir) for ir in src]
        return NS(name="fake-job-000000000001")
    def get(self, name=None):
        return NS(state=NS(name="JOB_STATE_SUCCEEDED"),
                  dest=NS(inlined_responses=self._last))

class _FakeClient:
    def __init__(self): self.batches = _FakeBatches()

prot = {}
pcms, offen = B2.batch_synthesize(_FakeClient(), [r_erz, r_emo], Path(tempfile.mkdtemp()),
                                  max_rounds=10, poll_seconds=0, qa=None,
                                  eskalation=True, protokoll=prot)
check("beide Turns vertont (nichts offen)", offen == [] and len(pcms) == 2, f"offen={len(offen)}")
check("Erzähler kam durch", r_erz.key in pcms)
check("Emotions-Turn kam durch", r_emo.key in pcms)
p_erz, p_emo = prot.get(r_erz.key, {}), prot.get(r_emo.key, {})
check("Erzähler: temperature BLIEB 0.3 (keine Betonungsänderung)", p_erz.get("temperature") == 0.3, str(p_erz))
check("Erzähler: per 'ohne Stil-Präfix' gerettet", p_erz.get("ohne_stil") is True, str(p_erz))
check("Emotions-Turn: temperature ANGEHOBEN (>=0.5)", (p_emo.get("temperature") or 0) >= 0.5, str(p_emo))
check("Emotions-Turn: Präfix BEHALTEN (Lachen bleibt)", p_emo.get("ohne_stil") is False, str(p_emo))

print("\n7b) Eskalierte Requests: Hash aendert sich, Wortlaut NICHT")
r_basis = B2.TtsRequest.build(voice="Puck", text="Fuenfhundert Jahre?", style="Sprich ruhig.", temperature=0.3)
r_esk   = B2.TtsRequest.build(voice="Puck", text="Fuenfhundert Jahre?", style="Sprich ruhig.", temperature=0.6)
check("andere temperature -> anderer Cache-Key (kein Vermischen der Stufen)", r_basis.key != r_esk.key)
check("Wortlaut bleibt identisch", r_basis.text == r_esk.text)
check("ohne Stil-Praefix: contents == nackter Text", r_basis.contents(bare=True) == "Fuenfhundert Jahre?")
check("mit Stil-Praefix: Praefix davor", r_basis.contents(bare=False).endswith("Fuenfhundert Jahre?")
      and r_basis.contents(bare=False) != "Fuenfhundert Jahre?")

print("\n7c) Manifest meldet die eskalierten Turns (die Liste fuer das PO-Ohr)")
cache2 = Path(tempfile.mkdtemp())
SEG2 = {"cast": {"kind": {"name": "Theo", "geschlecht": "m"},
                 "erwachsener": {"name": "Oma", "geschlecht": "w"}},
        "turns": [{"rolle": "erzähler", "text": "Theo schaut auf das Bild."},
                  {"rolle": "kind", "text": "Warum ist die Farbe so blass?"}]}

def fake_batch(client, reqs, cache_dir, qa=None, protokoll=None, **kw):
    """Turn 2 kommt angeblich erst per Eskalation (0.6, ohne Stil) durch."""
    for r in reqs:
        if "blass" in r.text and protokoll is not None:
            protokoll[r.key] = {"temperature": 0.6, "ohne_stil": True, "runde": 7}
    return {r.key: ton(1.0) for r in reqs}, []

_echt = B2.batch_synthesize
B2.batch_synthesize = fake_batch
try:
    info = T.vertone(SEG2, cache2 / "x.wav", nico_converter=lambda p, s: ton(1.0),
                     synth_mode="batch", pcm_cache=cache2 / "c", qa=False)
finally:
    B2.batch_synthesize = _echt
check("n_eskaliert == 1", info.get("n_eskaliert") == 1, str(info.get("n_eskaliert")))
check("eskalierte_turns nennt Turn 2", info.get("eskalierte_turns") == [2],
      str(info.get("eskalierte_turns")))
m2 = [m for m in info["turns"] if m["i"] == 1][0]
check("Manifest: Turn 2 traegt die ECHTE temperature 0.6", m2["temp"] == 0.6, str(m2["temp"]))
check("Manifest: Turn 2 als ohne_stil markiert", m2["ohne_stil"] is True)
m1 = [m for m in info["turns"] if m["i"] == 0][0]
check("Manifest: Turn 1 NICHT eskaliert", m1["eskaliert"] is False and m1["temp"] == 0.3,
      str(m1["temp"]))

print("\n8) Stille-Anteil + Trim (Fehler 1 vom 17.07.: korrekte Sprache in einem Meer aus Stille)")
# stille_anteil
check("Ton: fast kein Stille-Anteil", Q.stille_anteil(ton(2.0)) < 0.1, f"{Q.stille_anteil(ton(2.0)):.2f}")
mix = ton(2.0) + b"\x00\x00" * int(Q.SAMPLE_RATE * 4.0)   # 2s Sprache + 4s Stille = 67%
check("2s Ton + 4s Stille ~= 67%", 0.6 < Q.stille_anteil(mix) < 0.72, f"{Q.stille_anteil(mix):.2f}")
# pruefe: >65% Stille faellt durch, obwohl Sprech-Zeit/Tempo/Pegel je einzeln stimmen
ok, g = Q.pruefe(mix, "Dies sind vier Woerter", mit_whisper=False)
check("Turn mit 67% Stille -> abgelehnt (der Blind-Spot)", not ok and "Stille" in g, g)
mix_ok = ton(3.0) + b"\x00\x00" * int(Q.SAMPLE_RATE * 1.0)  # 3s + 1s = 25%, wie echte Turns
ok, g = Q.pruefe(mix_ok, "Dies sind fuenf ganze Woerter", mit_whisper=False)
check("Turn mit 25% Stille (wie echt) -> durch", ok, g)
# trim_stille
leer_vorne = b"\x00\x00" * int(Q.SAMPLE_RATE * 3.0) + ton(2.0) + b"\x00\x00" * int(Q.SAMPLE_RATE * 3.0)
tr = Q.trim_stille(leer_vorne)
check("Trim: 3s Stille + 2s Ton + 3s Stille -> ~2s", 1.8 < len(tr)/Q.BYTES_PER_SEC < 2.6,
      f"{len(tr)/Q.BYTES_PER_SEC:.2f}s")
check("Trim: reine Stille bleibt unangetastet (faengt die QA)",
      Q.trim_stille(b"\x00\x00" * 24000) == b"\x00\x00" * 24000)
mitte = ton(1.0) + b"\x00\x00" * int(Q.SAMPLE_RATE * 0.3) + ton(1.0)  # interne Pause bleibt
tr2 = Q.trim_stille(mitte)
check("Trim: interne Pause bleibt erhalten (kein Inhaltsverlust)",
      2.0 < len(tr2)/Q.BYTES_PER_SEC < 2.6, f"{len(tr2)/Q.BYTES_PER_SEC:.2f}s")

# Der 54-s-Stille-Defekt (Turn 2 des 17.07.-Laufs) wurde am 18.07. durch sauberes Audio ersetzt;
# die Original-Defekt-PCMs liegen als Beleg im Backup. Der Test prüft weiter gegen den echten Defekt.
_BAK8 = REPO / "articles/leo_final_20260717/pcm_cache/_defekt_backup_20260717"
_def8 = sorted(_BAK8.glob("turn02_*.pcm")) if _BAK8.exists() else []
if _def8:
    p3 = _def8[0].read_bytes()
    t3 = "und tippt mit dem Finger auf das Bild."   # Wortlaut dieses Turns (97 % Stille drumherum)
    ok, g = Q.pruefe(p3, t3)
    check("realer 54s-Turn (97% Stille) -> abgelehnt", not ok and "Stille" in g, g)
    tr3 = Q.trim_stille(p3)
    ok2, g2 = Q.pruefe(tr3, t3)
    check("nach Trim -> besteht QA (Sprache war korrekt)", ok2, g2)
    check("nach Trim: Transkript trifft den Soll-Text",
          Q.aehnlichkeit(t3, Q.transkribiere(tr3)) > 0.85)

print("\n" + ("ALLE TESTS OK" if not fails else f"{len(fails)} FEHLER: {fails}"))
sys.exit(1 if fails else 0)
