# Wissensfreund — STATUS
<!-- updated: 2026-07-19T20:24:49Z -->
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
  `wissensfreund_hoerspiel_prompt_v2_B.md` (einzige Fassung; A geloescht 2026-07-22, v1 verworfen: war Fakten-Katalog). Erbt die story_mode_v2-DNA
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

Wal run3: 815 W, Cast Ronja/Theo, Fluss statt Stakkato, Zahlen mit Vergleichen, Grounding sauber.

### Nachgeschärft (run4–6, PO-Feedback am Wal-Output)

- **Fenster-Prinzip statt „Tiefe in einem Bereich"** (Leo-Vorbild): Hörspiel-Prompt v2 auf „mehrere lebendige
  Fenster, jedes eine Mini-Szene" umgestellt + Companion-Priorität (erzählerisch Reiches zuerst) +
  Rahmen-als-Reise + Anti-Füllwort. Grund: run1–4 blieben biologielastig, ließen reiche Companions (Moby
  Dick, Delfine) liegen.
- **ROOT CAUSE + Fix — Kompass-Plan wurde nicht an die Generierung übergeben.** Kompass plante Moby Dick/
  Delfine als Höhepunkte, Flash bekam nur die Companion-*Texte* (Plan war Sackgasse) → schrieb Default-
  Biologie. Fix: `get_last_kompass_plan()` an die Jobs hängen + in `build_grounded_user_message` in den
  stabilen (typ-agnostischen) Prefix injizieren. **run5/6: Moby Dick + Delfine + Walfang landen jetzt.**
- **Sprach-Pass (2. leichter Lektorat-Durchgang)** in `lektorat_common.py` (`run_sprachpass_sync`, via
  `call_claude_json` → thinking-robust): fängt Wort-Schnitzer (gewandelt→gewandert) UND un-kindgerechten
  Jargon — entfernt/vereinfacht „Graysches Paradoxon"/„Spongiosaknochen"/„Osedax", schützt zentrale
  Begriffe (Barten/Fluke/Krill/Walsturz). Verdrahtet in generate_grounded (merge → ein Prüfbericht).
- **Einbau-Bug (Hörspiel) gefunden + gefixt:** `_apply_auto_correction` nahm 1 Satz/Eintrag an; Hörspiel-
  Turns sind Mehrsatz-Einträge → jeder Turn-Einbau scheiterte („bitte prüfen"). Ganz-Turn-Fall (Jaccard≥0.9)
  ergänzt → greift für Sprach-Pass UND Grounding-Lektorat (run6: silent=1 auto-eingebaut, 0 Flags).
- **Erzähler-Regel:** kein „Der Erzähler lächelt" mehr (keine Selbst-Handlung; warmer Tonfall bleibt erlaubt).

- **Redebegleitsatz-Split BEHOBEN (Post-Merge):** `_merge_split_speech_tags` in generate_grounded.py zieht vor
  validate zusammen: (A) wörtl. Rede + „ruft Theo" wieder in EINEN Turn, (B) über mehrere Einträge offene
  Reden. Läuft nur für hoerspiel. run7–9: 0 danglende Rede-Kommas, 0 unbalancierte Anführungszeichen.
- **Zwei Lektorat-Einbau-Klassen gefixt** (`_apply_auto_correction`, greifen für Grounding UND Sprach-Pass):
  (1) Schwanz-Teilstring — Korrektur trifft nur den Schwanz eines Mehrsatz-Turns → in-place-Ersatz (führender
  Satz + Redebegleitsatz bleiben). (2) Turn-Grenze — Dialog-Claim über Frage+Antwort (\n-verbunden) wird pro
  Turn eingebaut, unveränderte Turns übersprungen. run9: alle Korrekturen gelandet (0 prüfen, 0 eskaliert).

Offene Feinschliff-Punkte (nicht-blockierend): nackte Maße („33 Meter"/„200 Tonnen") als Vergleich (Zahl-
Regel); Kompass kürzt „Moby-Dick"→„Moby" (Bindestrich-Split, Text landet trotzdem — kosmetisch); 76 Dialog-
Turns triggern Validator-Bereich [15,60] (für alte Stufe 2 — für Typ hoerspiel Bereich anpassen).

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
