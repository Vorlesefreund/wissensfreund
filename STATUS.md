# Wissensfreund — STATUS
<!-- updated: 2026-06-16T05:18:07Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Anker-Nachträge: 27 Grundstock-Themen bewertet (2026-06-16).** ← AKTUELL
- catalog_rater_anker.py: 1 Opus-Call, alle 27 mit gesperrten Anker-erg-Werten
- 27/27 bewertet | 3 Leuchtturm (Elefant, Indianer, Lego) | 7 sensibel
- erg aus xlsx übernommen: alle 27 hatten Anker-Werte, 0 neu bewertet
- Lemma-Korrekturen: Tell→Wilhelm Tell, Humboldt→Alexander von Humboldt,
  VW→Volkswagen, Chaplin→Charlie Chaplin, Mozart→Wolfgang Amadeus Mozart
- Output: catalog_raw_anker/ (12 Gebiet-JSONs + alle_nachtraege.json)
- NOCH NICHT gemergt — nächster Schritt nach Prüfung

**Anker-134-Abgleich (2026-06-16).**
- 43 von 134 Anker-Themen komplett im Katalog fehlend (anker_gaps.json)
- 5 nur unter anderer Schreibweise vorhanden (Hai~Haie, Schmetterling~Schmetterlinge etc.)
- Achtung: "Verbannung ~ Verbrennung" ist FALSE MATCH — sind verschiedene Themen
- Genuine Lücken (Anker-Grundstock): Mozart, Fossilien, Waldbrand, Trojanischer Krieg,
  Tell, Humboldt, Seefahrer, Pfeil und Bogen, Tinte, Wachs, Vene, Zentripetalkraft,
  Wendekreis, Persischer Golf, Graubünden, Graz, Vevey, Dänische Sprache,
  Bundesrepublik Deutschland, Bundesrepublik Deutschland
- Intentionell/sensibel (erwartbar nicht im Katalog): Erotik, Negerkuss, Nazis,
  Antisemitismus, Zigarette(n), FDP, Linke Politik, Anschlag vom 11. September
- Markennamen/Nische: Lego, VW, Looney Tunes, Science Center, Bunker
- Nebenbefund Abgleich-Pool: 4524 Einträge (full+reserve+audit)

**Audit-Nachbewertung: 393 neue Themen via Opus-Rater (2026-06-15).**
- catalog_rater_audit.py: Opus-Calls pro Themengebiet, Input = audit_include_topics.json
- 393 Themen bewertet: 20 Leuchtturm, 113 sensibel, 0 exclude (alle bleiben include)
- 21 JSON-Dateien in catalog_raw_audit/ (je Gebiet)
- Gebiet-Korrekturen durch Rater: z.B. Eidgenossenschaft/Gorbatschow/Wissenschaft aus Tiere heraus
- essen_alltag.json: manuell gerettet (typografisches „ + gerader " brach JSON-Parse)
- NOCH NICHT in catalog_manual.json gemergt — nächster Schritt: gemeinsame Prüfung

**TTS JSON-Pipeline: tts_compose.py + tts_audio_compare.py v2 (2026-06-15).**
- tts_compose.py: compose() + strip_emoji() — Canonical-JSON → sauberer Vorlesetext
  - Emojis gestrippt, Boxen mit ProfessorPhrasen (wow/fakt/warnung/stimmt_das je S1-S3)
  - stimmt_das: Frage → Absatzpause (\n\n) → Antwort mit Einleitung
  - Überschriften als Sätze (Satzzeichen-Check), Quiz ausgelassen
- tts_audio_compare.py v2: --dir <verzeichnis> nimmt *.json Artikel (report.json gefiltert)
  - from tts_compose import compose — stufe aus meta.age_level abgeleitet
  - SCENE ersetzt (ruhige Professor-Instructions, englisch), VOICE_NAME=Iapetus
  - Legacy --articles .md Betrieb erhalten
- Testlauf --dir articles/test_compare: 12 Artikel × 2 Varianten = 24 TTS-Generierungen
  - 19/24 WAVs OK (5 TAGGING-FEHLER = 503×3 auf gemini-3.5-flash, transient)
  - TTS-Retry-Fallback funktioniert (NoneType → OK auf Retry 1)
  - Vergleich: tts_audio_compare_out/tts_audio_compare.html

**Coverage-Audit + Excel abgeschlossen (2026-06-15).**
- coverage_audit.py: 3-stufiger Audit (Klexikon-Abgleich, Pflichtliste, LLM-Audit pro Gebiet)
- 560 neue Kandidaten: 325 Klexikon, 10 Pflichtliste, 225 LLM (Haiku pro Gebiet)
- Fuzzy-Match: 36 mutmaßliche Dubletten (ratio ≥ 0.85)
- catalog_review_audit.xlsx: Basis=Review-Sheet + NEU-Zeilen alphabetisch eingemischt
  Grün=neue Kandidaten | Orange=mutmaßl. Dublette | Spalten: STATUS_NEU, QUELLE_AUDIT, MUTMASSLICHE_DUBLETTE, AEHNLICH_VORHANDEN
- Top-Lücken-Gebiete: Grundbegriffe 71, Gesellschaft 57, Geschichte 54, Tiere 41, Religion 35
- Gebiet-Klassifikation per Haiku-Batch (211 Klexikon-Items ohne Keyword-Match)
- Diagnose "Indianer": war nie in Rater-Runden → muss manuell in catalog_manual.json

**Tagging-Modell auf gemini-3.5-flash aktualisiert (2026-06-15).**
- gemini-3.1-flash (Text): per 404 verifiziert nicht existent
- gemini-3.5-flash: bestes verfügbares Text-Flash, TAGGING_MODEL in beiden Scripts
- Stabilitätstest 3.5-flash: 3/5 OK bei Kurz-Calls (Thinking-Modell, braucht ≥8192 Token)
- 18-Call-Lauf 3.5-flash: 16/18 OK (2 TAGGING-FEHLER nach je 3 Retries 503)
- Vergleich 2.5-flash-lite: 18/18 OK, schneller (kein Thinking) → stabiler für Prod-Pipeline
- TTS-Modell: gemini-3.1-flash-tts-preview ✅ | Stimme: Sulafat ✅

**TTS-Audio A/B-Vergleich abgeschlossen (2026-06-15).**
- tts_audio_compare.py: feste Tag-Palette vs. freie Tag-Wahl, beide mit Gemini Flash
- TTS: gemini-3.1-flash-tts-preview, Stimme: Sulafat (warme Kinderstimme, validiert)
- Ergebnis 3-Pilot × S1–S3 × 2 Varianten = 18 TTS-Calls
- Audio: tts_audio_compare_out/*.wav (18 Dateien)
- HTML-Vergleich: tts_audio_compare_out/tts_audio_compare.html
- Umlaut-Problem in PowerShell → Wrapper temp/_run_all3.py (sys.argv direkt setzen)

**TTS-Tagging Vergleichs-Harness angelegt (2026-06-15).**
- wissensfreund_tts_tagging_v1.md: System-Prompt "Professor-Stimme", Inline-Tags, sound_mood
- tts_tagging_compare.py: 3 Modelle parallel (Gemini 2.5-flash, Haiku 4.5, Sonnet 4.6), HTML-Report
- Fixes: max_tokens 4000→8192, JSON-Fallback-Extraktion (Anführungszeichen-Problem S3), Gemini-Retry bei 503
- Ergebnis 3-Pilot (Vulkan, Dinosaurier, Kühlschrank × S1–S3):
  Haiku 4.5: 9/9 OK | Sonnet 4.6: 9/9 OK | Gemini Flash: 7/9 OK (2× 503 transient)
- HTML-Vergleich: tts_tagging_compare_out/tts_tagging_compare.html
- Aufruf: `python tts_tagging_compare.py --articles Thema1 Thema2 [--dir Verzeichnis]`
- Gemini-Modell: gemini-2.5-flash (preview, gelegentlich 503)

**sound_compare.py v2 angelegt (2026-06-15).**
- Vergleicht Freesound vs. Openverse auf 100 kuratierten Themen (slug, EN-Query, DE-Label)
- Phase 1: Parallel-Suche (ThreadPool, workers=4), Dauer-Filter 1–15s
- Phase 2: Preview-Download + 4s-Clip via ffmpeg subprocess (Stille am Anfang überspringen, fade-in/out)
- Phase 3: HTML-Report mit eingebettetem `<audio>`-Player (Clips) oder Extern-Link (Fallback)
- pydub NICHT benötigt (Python 3.14-inkompatibel) → ffmpeg direkt per subprocess
- Zapsplat: kein öffentlicher API-Endpunkt → nur notiert, nicht implementiert
- Freesound aktuell rate-limited (429, 2000/day erschöpft)
- Openverse: funktioniert (kein Key, CC0+by, duration manuell in ms gefiltert)
- Aufruf: `python sound_compare.py` (alle 100) | `--limit N` | `--no-freesound` | `--no-clips`
- Voraussetzung ffmpeg: `winget install ffmpeg` (dann Clips aktiv)

**sound_sourcing.py: --phase catalog-scan ergänzt (2026-06-14).**
- 2730 Themen im Scan-Scope (14 Themengebiete, primary, non-exclude)
- Haiku-Batch-Übersetzung (80er-Batches), Resume-fähiger Cache (sound_scan_cache.json)
- Freesound-Suche CC0, 0.5–15s, ★≥3.0 Filter, EN-Fallback auf DE
- HTML-Review: sound_review_catalog.html (gruppiert nach Themengebiet, <details>-Akkordeon)
- --candidates N (default 3) konfigurierbar
- Laufzeit ~15–20 Min für alle 2730 Themen
- Nächster Schritt: FREESOUND_API_KEY + ANTHROPIC_API_KEY setzen, dann `python sound_sourcing.py --phase catalog-scan`

**sound_sourcing.py v1 angelegt (2026-06-14).**
- 40 Ambient + 30 Spot Kategorien, HTML-Review-Workflow
- Nächster Schritt nach catalog-scan: sound_review_catalog.html im Browser öffnen, auswählen, finalize

**generate_grounded.py: eignung_verdicts.json vollständig verdrahtet (2026-06-14).**
- Bug 1 gefixt: `_load_eignung()` normiert Keys auf `.lower()` → Lookup trifft jetzt
- Bug 2 gefixt: `eignung_for()` liest neues Schema (`exclude:true` statt `eignung:"exclude"`)
- Dry-Run bestanden: exclude/age_floor=3/framing_note alle korrekt

**eignung_verdicts.json + categories_backlog.json (2026-06-14): 738 Verdicts (42 exclude, 231 age_floor>1, 529 framing_note). 118 categories_backlog.**

**Round-3 + Merge (2026-06-14): 3968 primary / 162 reserve / 27 exclude / 479 sensibel / 194 Leuchtturm.**

Gebiets-Breakdown (primary):
Tiere 807 | Berühmte Personen 294 | Länder 250 | Naturwiss 246 | Pflanzen 239 |
Technik 221 | Geschichte 217 | Sport 212 | Kunst 184 | Essen 180 |
Körper 167 | Gesellschaft 147 | Erde 126 | Grundbegriffe 120 | Deutsche Städte 110 |
Märchen 102 | Naturräume 100 | Weltstädte 100 | Religion 83 | Weltall 63

### Pipeline-Zustand (generate_grounded.py, Stand 2026-06-14)
Ergiebigkeit verdrahtet ✅ | resolve_lemma im Hauptloop ✅ | Doppelbedeutungs-Direktive ✅
Wortzahl-Guard ✅ | Box-Verteilungs-Guard ✅ | Eignungs-Gate ✅ (vollständig)
eignung_verdicts.json: 738 Verdicts, exclude+age_floor+framing_note alle aktiv
System-Prompt: v3.23b-production | Modell: gemini-3.5-flash

### Ergiebigkeits-Modell (Detail → WISSEN_ARTIKEL_PIPELINE.md)
`target_S = Wlo + frac·(Whi−Wlo), frac = clamp((score−2)/6, 0, 1)`
Bänder: S1[50,250] S2[80,400] S3[100,650]. Rater = Opus per API, Anker: 134 Themen.

---

## 🔴 Nächster Schritt

**Pilot-Bulk-Lauf** (z.B. 50–100 Themen aus catalog_full.json) mit der vollständigen Pipeline:
generate_grounded.py aus catalog_full.json → exclude-Filter, age_floor, framing_note aktiv.

---

## 🔴 Offene Punkte (nach Priorität)

Pilot-Bulk-Lauf (50–100 Themen, vollständige Pipeline) — nächster Chat
categories_backlog.json → categories-Array je Artikel (spätere Phase)
Dedup (Hai=Haie, Deutschland 3×; eigenständige Dino-Arten) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); Flutter WfArticleListScreen
