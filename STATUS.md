# Wissensfreund — STATUS
<!-- updated: 2026-07-19T17:07:46Z -->
<!-- Ältere Stände (verbatim, inkl. TTS-Woche 16.-18.07.) → STATUS_ARCHIV.md · `git log STATUS.md` · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder. Profil 3-stufig (4–6/7–9/10–12, steuert Modi), **Inhalt 2-typig**:
Hörspiel (4–9, alt S1+S2) + Erzähltext (10–12, = alt S3). KI streng aus geladenem Quelltext (nie
Trainingswissen). Umbau-Plan: `STUFEN_UMBAU_PLAN.md`. Hörspiel-Genre-Spec: `HOERSPIEL_GENRE_SPEC.md`.

## Zuletzt abgeschlossen (2026-07-19) — Stufen-Umbau Pipeline (Plan §7.2) + Hörspiel-Genre

- **Paket A (Mechanik) fertig+verifiziert:** `generate_grounded.py` Achse Lesestufe→`content_type`
  (`hoerspiel`/`erzaehltext`); `--stufen`→`--typen`; age_floor → Anbietezeit-Filter (Hörspiel-Drop nur bei
  floor 3); `image_stufe_for`; Bänder beide (225,975). CI-Guards in `verify_project_facts.py` nachgezogen.
- **Paket B — Hörspiel-Prompt v2 (Story-first) geschrieben + über 3 Wal-Läufe validiert.**
  `wissensfreund_hoerspiel_prompt_v2.md` (v1 verworfen: war Fakten-Katalog). Erbt die story_mode_v2-DNA
  (keine großen Zahlen, ikonisches Beispiel/Moby Dick, Tiefe vor Breite, Erzähler ohne Sachwissen,
  EISERNE-Regel-Split) + „mit-Tags"-JSON-Gerüst. Verdrahtet via `content_type` (Cache je Typ), Guards grün.
- **PO-Tuning eingebaut (per Ohr an Wal-Output):** Zahlen → höchstens EINE pro *Antwort*, Maße als
  Vergleiche, kein Stakkato-Zerhacken; kulturelle Anker (Moby Dick) als erfundener Rahmen erlaubt.
- **Kompass geschärft** (PO: geteilt lassen, nicht pro Typ trennen): harte Vielfaltsgrenze (max. 2 Vertreter
  derselben Kategorie — vorher 4 Walarten), kultureller Anker Pflicht-wenn-vorhanden, „Breite"-Sog entschärft.
  Phase 1 läuft weiter EINMAL für beide Typen (geteilter Quell-Cache).
- **Zwei Lektorat-Bugs gefixt** (pipeline-weit, blockierten JEDES Lektorat): (1) `temperature=0` → 400
  „deprecated for this model" entfernt; (2) `content[0].text` traf ThinkingBlock → echten Text-Block picken.
  `lektorat_common.py` sync+batch. Run3-Lektorat lief sauber durch (0 silent/korrigiert/prüfen).
- **Story-Cast festgezurrt (PO-Abnahme „alle Stimmen passen"):** 16 Figuren, feste Gemini-Stimme+Stil je
  Figur → [[project_story_cast]] (FINAL-Tabelle; einige weichen von tts_samples.py ab). Kind = Theo|Mia.

Wal run3 (zeigbar, Desktop `_wal_hoerspiel_v2_review.txt`): 815 W, Cast Ronja/Theo, Fluss statt Stakkato,
Zahlen mit Vergleichen, Grounding sauber. Rest-Feinschliff (nicht-blockierend): vereinzelt nackte Zahl
(200 t/1000 m), Verschreiber „Vorlagen"→„Vorfahren", CO2→Kohlendioxid, Rahmen neigt zu „Buch auf Tisch".

## Gerade in Arbeit / Nächster Schritt

- **Task D — Vertonungs-Test:** `tts_story.py` von 3 Rollen-Stimmen auf den festen 16-Figuren-Cast erweitern
  (Stimme + Stil-Vorspann je Figur, [[project_story_cast]]), dann ein v2-Hörspiel echt vertonen → PO-Frage
  „überleben die Charakterstimmen die Produktion (bleibt z.B. Rudi lebendig)?". Heute NICHT nötig gewesen.

## Offen nach Priorität

1. **Stufen-Umbau Rest (Plan §7):** §7.3 Upload/Index (age_floor in Metadaten, Index 2 Typen), §7.4 App
   (ID-Mapping/Filter `_hoerspiel`/`_erzaehltext`), Datenrebuild `ergiebigkeit_scores` (§9).
2. **Optionaler Feinschliff Hörspiel-Prompt:** nackte Zahlen (200t/1000m) als Vergleich erzwingen, Rahmen-
   Vielfalt gegen „Buch auf dem Tisch", CO2→Kohlendioxid. (PO-Fork offen — kein Blocker.)
3. **TTS-Produktion in Serie** (aus TTS-Woche): Batch mit temp 0.3 + 10 Runden + QA über Katalog; VC-Stufe
   getrennt auf EINEM Pod (~1–3 $/Lauf). Reproduzierbares Tooling steht → [[project_tts_produktions_pipeline]].
4. **`verify_project_facts.py`:** 1 Hart-FAIL = Verify-Drift (Vision-Regel erwartet `claude-sonnet-5`,
   `stage_models.py` bewusst `gemini-2.5-flash-lite`) — Regel angleichen, unabhängig vom Umbau.
5. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button „Leonardo (Vorlese-Test)", TEMP-Prints in
   `_prepareNarration` (`home_screen.dart`).
6. **Tablet-Pass** (eigener Chat!): Kinderschutz/Plus/Menü/Profile tablet-zentrieren, dann Lesemodi A/B/C.
   **Handy-Modus bleibt unangetastet** — jede Handy-Änderung vorher absprechen.

<!-- Detail-Historie (TTS-Woche, QA-Gate, Batch-Durchbruch, Stimme eingefroren) verbatim in STATUS_ARCHIV.md. -->
