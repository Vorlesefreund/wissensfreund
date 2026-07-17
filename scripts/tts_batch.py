#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tts_batch.py — TTS-Synthese über die Gemini Batch-API, mit Cache und Runden-Schleife.

WOZU: Die synchrone API ist für Produktionsläufe untauglich. Belegt am 2026-07-16 auf einer
gemieteten GPU: Flash lieferte 504/503 im Minutentakt, 7 von 23 Turns fielen aus, ein Turn
blockierte 3 Minuten. Bei 50 Themen × 2 Stufen ist das aussichtslos. Batch stellt sich IN die
Warteschlange statt dagegen anzurennen — und kostet die Hälfte.

DIE DREI BEFUNDE, DIE DIESES MODUL FORMEN (alle empirisch, s. [[reference_tts_gotchas]]):

1. **Batch kann Audio.** `batches.create(model=<tts>, src=[InlinedRequest(...)])` wird akzeptiert
   und liefert `mime_type='audio/l16; rate=24000; channels=1'` — genau unser PCM-Format.

2. **`JOB_STATE_SUCCEEDED` heißt NICHT „alles da".** Von 2 Requests kam einer leer zurück:
   `finish_reason=OTHER`, `content.parts=None`, `error=None`, kein Safety-Grund. Der Job galt
   trotzdem als erfolgreich. Wer das Ergebnis ungeprüft einsammelt, baut sich still Löcher ins
   Audio — derselbe Fehler, den wir in tts_story.vertone gerade geschlossen haben.
   → Jede Antwort wird EINZELN auf echtes Audio geprüft; Leere kommen in die nächste Runde.

3. **Stil-Präfix + kurzes/heikles Fragment triggert PROHIBITED_CONTENT** (deterministisch —
   erneutes Senden hilft NIE). → Ab Runde 2 wird ein geblockter Request OHNE Stil-Präfix
   nachgereicht (nackter Text läuft zuverlässig). Wortlaut bleibt unverändert.

WEITER: Der Cache (Inhalts-Hash → PCM) macht das Vollständigkeits-Gate erst bezahlbar. Ohne ihn
würde ein Wiederholungslauf alles neu synthetisieren; mit ihm nur die Lücken. Nebeneffekt (in
leo_build2.py bewährt): derselbe Text liefert dieselbe Audio — kein Stimm-Drift beim Rebuild,
weil nicht bei jedem Lauf neu gewürfelt wird.

NICHT hier drin: die Voice-Conversion. Synthese und VC sind bewusst getrennt — die VC braucht
eine GPU, die Synthese nicht. Sie zusammen laufen zu lassen heißt, eine gemietete GPU dabei
zuzusehen, wie sie auf API-Timeouts wartet (16.07.: ~75 Min Miete für 23 Turns).

    from tts_batch import TtsRequest, batch_synthesize
    reqs = [TtsRequest.build(voice="Puck", style=STYLE["kind"], text="Wer ist das?", temperature=0.3)]
    pcms, fehlend = batch_synthesize(client, reqs, cache_dir=Path("pcm_cache"))
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

TTS_MODEL = "gemini-3.1-flash-tts-preview"
SAMPLE_RATE = 24000

# Batch-Endzustände (SUCCEEDED heißt nur "Job fertig", NICHT "alle Antworten brauchbar" — s. oben).
DONE_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}

# Runde 1 + 9 Nachreich-Runden. Danach: laut abbrechen statt still liefern.
# Warum 10: mit temperature=0.3 haengt rund jeder 2.-3. Call (gemessen 2026-07-17: 19/32 OK; die
# Quote schwankt mit der Tageslast). Der Hänger ist pro Call zufaellig — derselbe Text kommt beim
# naechsten Versuch meist durch. Bei ~40 % Ausfall bleiben nach 3 Runden ~6 % uebrig (= die 7 Loecher
# vom 16.07.), nach 10 Runden Promille. Leere Antworten kosten keine Output-Tokens → Runden sind
# faktisch gratis, sie kosten nur Wartezeit. Siehe auch RETRY-Kommentar in tts_story.synth_pcm.
MAX_ROUNDS = 10
POLL_SECONDS = 30
POLL_TIMEOUT = 6 * 3600  # Batch darf lange dauern (2 Sätze brauchten 15 Min) — aber nicht ewig.


@dataclass(frozen=True)
class TtsRequest:
    """Eine zu vertonende Einheit. ``key`` ist ein reiner Inhalts-Hash → cachefähig."""
    key: str
    voice: str
    text: str
    style: str | None = None
    temperature: float | None = None
    meta: dict = field(default_factory=dict, compare=False)

    @staticmethod
    def build(voice: str, text: str, style: str | None = None,
              temperature: float | None = None, **meta) -> "TtsRequest":
        # Der Hash MUSS alles enthalten, was den Klang bestimmt — sonst liefert der Cache
        # bei geänderten Parametern altes Audio zurück.
        raw = f"{TTS_MODEL}|{voice}|{style or ''}|{temperature}|{text}"
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return TtsRequest(key=key, voice=voice, text=text, style=style,
                          temperature=temperature, meta=meta)

    def contents(self, bare: bool = False) -> str:
        """Prompt. ``bare`` = ohne Stil-Präfix (Ausweg aus dem PROHIBITED_CONTENT-Block)."""
        if bare or not self.style:
            return self.text
        return f"{self.style}\n\n{self.text}"


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.pcm"


def load_cached(cache_dir: Path, reqs: list[TtsRequest]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for r in reqs:
        p = _cache_path(cache_dir, r.key)
        if p.exists() and p.stat().st_size > 0:
            out[r.key] = p.read_bytes()
    return out


def _build_inlined(reqs: list[TtsRequest], bare_keys: set[str]):
    from google.genai import types
    out = []
    for r in reqs:
        cfg = dict(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=r.voice))),
        )
        if r.temperature is not None:
            cfg["temperature"] = r.temperature
        out.append(types.InlinedRequest(
            contents=r.contents(bare=r.key in bare_keys),
            config=types.GenerateContentConfig(**cfg),
            metadata={"key": r.key},
        ))
    return out


def _extract(resp) -> tuple[bytes | None, str | None]:
    """(pcm|None, grund|None). Prüft JEDE Antwort einzeln — SUCCEEDED sagt nichts über den Inhalt."""
    if resp is None:
        return None, "response=None"
    pf = getattr(resp, "prompt_feedback", None)
    block = getattr(pf, "block_reason", None) if pf else None
    if block:
        return None, f"BLOCK:{block}"
    cands = getattr(resp, "candidates", None)
    if not cands:
        return None, "keine candidates"
    cand = cands[0]
    content = getattr(cand, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        # Der reale Hauptausfall: finish_reason=OTHER, parts=None, kein Fehler, kein Safety-Grund.
        return None, f"leer (finish_reason={getattr(cand, 'finish_reason', None)})"
    blob = getattr(parts[0], "inline_data", None)
    data = getattr(blob, "data", None) if blob else None
    if not data:
        return None, "part ohne inline_data"
    return data, None


def poll_batch(client, name: str, poll_seconds: int = POLL_SECONDS,
               timeout: int = POLL_TIMEOUT) -> tuple[object, str]:
    t0 = time.time()
    job = None
    while time.time() - t0 < timeout:
        job = client.batches.get(name=name)
        state = job.state.name if hasattr(job.state, "name") else str(job.state)
        if state in DONE_STATES:
            log.info("  Batch %s → %s (nach %.0f s)", name[-12:], state, time.time() - t0)
            return job, state
        log.info("  Batch %s → %s (%.0f s)", name[-12:], state, time.time() - t0)
        time.sleep(poll_seconds)
    return job, "TIMEOUT"


def _zuordnen(offen: list[TtsRequest], responses: list
              ) -> tuple[list[tuple[TtsRequest, object]], list[TtsRequest]]:
    """([(request, response)], [requests ohne Antwort]).

    WARUM NICHT ``zip``: Die Reihenfolge ist eine ANNAHME. Lässt der Job eine Antwort aus (statt sie
    leer zu liefern), verrutscht ab dieser Stelle ALLES — Oma Rina bekäme Theos Audio, jeder Turn
    hätte Audio, und das Vollständigkeits-Gate meldete zufrieden „vollständig". Ein stiller
    Datenfehler in einer Datei, die niemand mehr anhört.

    Jeder Request trägt ``metadata={"key": …}``, und die API gibt das Feld zurück → daran wird
    zugeordnet. Fehlt das Feld (SDK-/Backend-Änderung), ist die Reihenfolge nur dann vertretbar,
    wenn die Anzahl exakt passt. Passt sie nicht, wird NICHTS zugeordnet: die ganze Runde gilt als
    offen und geht erneut raus. Lieber eine Runde verlieren als Audio am falschen Turn.
    """
    per_key: dict[str, object] = {}
    for rw in responses:
        md = getattr(rw, "metadata", None) or {}
        k = md.get("key") if isinstance(md, dict) else None
        if k:
            per_key[k] = rw
    if per_key:
        paare = [(r, per_key[r.key]) for r in offen if r.key in per_key]
        ohne = [r for r in offen if r.key not in per_key]
        if ohne:
            log.warning("%d von %d Requests ohne Antwort im Job (per metadata erkannt)",
                        len(ohne), len(offen))
        return paare, ohne
    if len(responses) == len(offen):
        # Kein metadata, aber Anzahl passt → Reihenfolge ist die einzige Information, die es gibt.
        log.info("Antworten ohne metadata — Zuordnung per Reihenfolge (Anzahl stimmt: %d)", len(offen))
        return list(zip(offen, responses)), []
    log.error("Antwortzahl %d != Requestzahl %d UND kein metadata → Zuordnung unmöglich. "
              "Runde verworfen (statt Audio am falschen Turn abzulegen).",
              len(responses), len(offen))
    return [], list(offen)


RUNDEN_JE_STUFE = 2


def eskalationsleiter(basis_temp: float | None, runden_je_stufe: int = RUNDEN_JE_STUFE
                      ) -> list[tuple[float | None, bool]]:
    """[(temperature, ohne_stil_praefix)] je Runde.

    WARUM ESKALIEREN statt nur wiederholen: Bei ``temperature=0.3`` ist die Token-Auswahl fast
    deterministisch — das ist ihr Sinn (sie liefert die kanonische Betonung). Derselbe Text nimmt
    deshalb fast immer denselben Pfad; führt der in eine Degenerations-Schleife, führt er beim
    zehnten Versuch genauso hinein. Gemessen 2026-07-17: Trefferquote je Runde 38 % → 22 % → 5,6 %,
    also praktisch Stillstand. Zehnmal denselben Request zu schicken und ein anderes Ergebnis zu
    erwarten, ist keine Strategie. Erst eine GEÄNDERTE Eingabe ändert den Pfad.

    Reihenfolge ist Absicht — der billigste Verlust zuerst:
      1. temp unverändert (2×)            — reiner Zufallsanteil, kostet nichts.
      2. temp unverändert, OHNE Stil-Präfix (2×) — ändert den Pfad, LÄSST die Betonung bei 0.3.
         Es entfällt nur die feine Stilsteuerung. (Derselbe Hebel wie beim PROHIBITED_CONTENT-Block.)
      3. temp 0.5, dann 0.6 (je 2×)       — ändert die Betonung. Erst hier wird das PO-Kriterium
         angetastet: ein Turn mit anderer Betonung schlägt einen Turn, den es nicht gibt.
      4. Default (2×)                     — läuft nachweislich immer (16/16), letzter Ausweg.

    Eskalierte Turns stehen hinterher im Manifest (``temp`` je Turn) → der PO muss nicht 37 Turns
    hören, sondern nur die Handvoll Ausnahmen.
    """
    if basis_temp is None:
        return [(None, False)] * (runden_je_stufe * 5)      # nichts zu eskalieren
    stufen: list[tuple[float | None, bool]] = [(basis_temp, False), (basis_temp, True)]
    stufen += [(t, False) for t in (0.5, 0.6) if t > basis_temp]
    stufen.append((None, False))
    return [s for s in stufen for _ in range(runden_je_stufe)]


def batch_synthesize(client, reqs: list[TtsRequest], cache_dir: Path,
                     max_rounds: int = MAX_ROUNDS, poll_seconds: int = POLL_SECONDS,
                     qa=None, eskalation: bool = True,
                     protokoll: dict | None = None) -> tuple[dict[str, bytes], list[TtsRequest]]:
    """Synthetisiert alle Requests. Gibt ({key: pcm}, [nicht geschaffte Requests]) zurück.

    Der Aufrufer MUSS die zweite Liste prüfen — ist sie nicht leer, fehlt Audio, und daraus darf
    kein Artefakt gebaut werden (s. Vollständigkeits-Gate in tts_story.vertone).

    qa: ``(pcm, text) -> (ok, grund)``. Durchgefallenes Audio wird wie eine leere Antwort behandelt:
        nicht cachen, nächste Runde. Ohne das kann ein Turn mit gueltigem Blob, aber 54 s Stille
        durchrutschen (real passiert) — "Bytes vorhanden" ist KEIN Qualitaetsmerkmal.
    eskalation: ab Runde 3 die Eingabe ändern statt denselben Request zu wiederholen —
        s. ``eskalationsleiter``. False = altes Verhalten (nur wiederholen).
    protokoll: wird je ERFOLGREICHEM Original-Key gefüllt mit {"temperature", "ohne_stil", "runde"}.
        Damit steht im Manifest, welche Turns eskaliert sind → nur die gehören ans PO-Ohr.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    uniq: dict[str, TtsRequest] = {r.key: r for r in reqs}   # gleicher Inhalt = ein Call
    pcms = load_cached(cache_dir, list(uniq.values()))
    if pcms:
        log.info("Cache: %d/%d Einheiten bereits vorhanden", len(pcms), len(uniq))

    offen = [r for k, r in uniq.items() if k not in pcms]
    bare_keys: set[str] = set()
    basis_temp = offen[0].temperature if offen else None
    leiter = eskalationsleiter(basis_temp) if eskalation else []

    for runde in range(1, max_rounds + 1):
        if not offen:
            break
        # Die Leiter bestimmt, WAS diese Runde rausgeht. Ohne sie: unveränderte Wiederholung.
        temp, ohne_stil = leiter[runde - 1] if runde - 1 < len(leiter) else (basis_temp, False)
        # Neue Requests mit der Stufen-temperature: die geht in den Hash ein → eigener Cache-Eintrag,
        # kein Vermischen von Audio verschiedener Stufen. urspruenglich[versuch.key] = original.key.
        versuche, urspruenglich = [], {}
        for r in offen:
            v = (r if temp == r.temperature else
                 TtsRequest.build(voice=r.voice, text=r.text, style=r.style,
                                  temperature=temp, **r.meta))
            versuche.append(v)
            urspruenglich[v.key] = r.key
        # bare_keys sammelt ORIGINAL-Keys (aus BLOCK-Faellen) — hier auf die Versuchs-Keys
        # uebersetzen, sonst verliert ein geblockter Turn seinen Ausweg, sobald er eskaliert.
        runden_bare = {v.key for v in versuche if urspruenglich[v.key] in bare_keys}
        if ohne_stil:
            runden_bare |= {v.key for v in versuche}
        if runde > 1 and (temp != basis_temp or ohne_stil):
            log.info("Runde %d/%d: %d Einheiten — ESKALATION: temperature=%s%s",
                     runde, max_rounds, len(versuche), temp,
                     " OHNE Stil-Präfix" if ohne_stil else "")
        else:
            log.info("Runde %d/%d: %d Einheiten einreichen …", runde, max_rounds, len(versuche))
        try:
            job = client.batches.create(model=TTS_MODEL, src=_build_inlined(versuche, runden_bare))
        except Exception as e:
            log.error("Batch-Einreichung fehlgeschlagen: %s", e)
            break

        name = job.name
        job, state = poll_batch(client, name, poll_seconds)
        if state != "JOB_STATE_SUCCEEDED":
            log.error("Batch %s endete als %s — Runde verloren", name[-12:], state)
            continue

        responses = getattr(getattr(job, "dest", None), "inlined_responses", None) or []
        # Gegen die VERSUCHE zuordnen, nicht gegen die Originale: die Antworten tragen die metadata
        # der tatsaechlich gesendeten (evtl. eskalierten) Requests.
        original_von = {r.key: r for r in offen}
        paare, ohne_antwort = _zuordnen(versuche, responses)
        naechste: list[TtsRequest] = [original_von[urspruenglich[v.key]] for v in ohne_antwort]
        for v in ohne_antwort:
            log.warning("  %s: keine Antwort im Job → Runde %d", urspruenglich[v.key][:8], runde + 1)
        for v, resp_wrap in paare:
            r = original_von[urspruenglich[v.key]]        # der Turn, um den es geht
            if getattr(resp_wrap, "error", None):
                log.warning("  %s: Fehler %s", r.key[:8], str(resp_wrap.error)[:80])
                naechste.append(r)
                continue
            pcm, grund = _extract(getattr(resp_wrap, "response", None))
            if pcm and qa is not None:
                # Ausschuss verhaelt sich wie eine leere Antwort: NICHT cachen (ein kaputtes PCM im
                # Cache waere fuer immer ausgeliefert — der Hash kennt nur Text/Stimme/Stil/temp,
                # nicht die Qualitaet), sondern in die naechste Runde. Real gefangen: ein Turn kam
                # als 54 s STILLE zurueck, mit gueltigem Audio-Blob und JOB_STATE_SUCCEEDED.
                ok, qa_grund = qa(pcm, v.text)
                if not ok:
                    log.warning("  %s: QA durchgefallen (%s) → Runde %d", r.key[:8], qa_grund, runde + 1)
                    naechste.append(r)
                    continue
            if pcm:
                # Unter dem VERSUCHS-Key cachen (die Stufe steckt im Hash), aber unter dem ORIGINAL-
                # Key zurueckgeben — der Aufrufer kennt nur seine urspruenglichen Requests.
                _cache_path(cache_dir, v.key).write_bytes(pcm)
                pcms[r.key] = pcm
                if protokoll is not None:
                    protokoll[r.key] = {"temperature": v.temperature,
                                        "ohne_stil": v.key in runden_bare, "runde": runde}
                if v.temperature != basis_temp or v.key in runden_bare:
                    log.info("  %s: per ESKALATION geschafft (temperature=%s%s, Runde %d)",
                             r.key[:8], v.temperature,
                             ", ohne Stil-Präfix" if v.key in runden_bare else "", runde)
                continue
            log.warning("  %s: kein Audio (%s) → Runde %d", r.key[:8], grund, runde + 1)
            if grund and grund.startswith("BLOCK:") and r.style:
                # Deterministischer Block: erneut senden bringt nichts, nackter Text schon.
                bare_keys.add(r.key)
            naechste.append(r)
        offen = naechste

    if offen:
        log.error("NICHT VERTONT nach %d Runden: %d Einheiten", max_rounds, len(offen))
        for r in offen[:5]:
            log.error("   %s  \"%s\"", r.voice, r.text[:60])
    return pcms, offen
