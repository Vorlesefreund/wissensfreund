# Wissensfreund — STATUS
<!-- updated: 2026-07-31T21:05:08Z -->
<!-- Ältere Stände (Rückbau 29.07, Review4, S3-Wiederherstellung, TTS-Woche, Stufen-Umbau) → git log STATUS.md · STATUS_ARCHIV.md · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder. Profil 3-stufig (4–6/7–9/10–12, steuert Modi), **Inhalt 2-typig**:
Hörspiel (4–9) + Erzähltext (10–12, = altes S3). KI streng aus geladenem Quelltext (nie Trainingswissen).
**Zwei getrennte Text-Motoren** (bewusst) → [[project_zwei_textmotoren]].

## Zuletzt abgeschlossen (2026-07-31) — GPT als Generator getestet & VERWORFEN, sauberer Stand

- **Entscheidung (PO, final): Wir bleiben bei Flash.** Bakeoff `gpt-5.6-terra` vs. `gemini-3.5-flash`
  (Dino-Hörspiel, identische Pipeline + Prompt, nur Generator getauscht). Objektiver Rubrik-Score
  (Claude-Sonnet-5-Judge): **Flash 3.64 vs. GPT 3.18**. GPT erzählt enzyklopädisch/„Museumsführung"
  (lange Erklärblöcke, unerklärte Fachbegriffe), weniger Story-Sog; Flash hat den stärkeren Hook +
  mehr „show, don't tell". Detail + Grund im Entscheidungs-Log (PROJEKTDOKUMENT.md, 31.07.).
- **GPT-Scaffolding restlos entfernt:** `scripts/openai_client.py` gelöscht, GPT-Zweige in
  `generate_grounded.py` per `git restore` zurückgerollt, GPT-Preiszeilen aus `cost_tracker.py` raus.
  **Produktion unverändert:** Gemini Flash, Rückbau-Default **BASE + v2_B** (29.07.) bleibt maßgeblich.
- **Committet (offene Arbeit, u.a. aus Parallel-Chat):** App-Feature Absatzumbrüche (`para_break`) im
  Reader (3 Dart-Dateien); `cost_tracker` per-Prozess-Log via `WF_COST_LOG` (Parallelitäts-Härtung).
- **Review-Docx** beider Hörspiele: `Desktop/Wissensfreund_Review/2026-07-31_bakeoff_gpt_vs_flash/`.

## Gerade in Arbeit / Nächster Schritt

- **Nachtlauf geplant (Scheduler, 01.08. 02:30):** 5 Themen (Fußball, Hänsel und Gretel,
  Afrika, Alexander der Große, Auto) × 2 Typen (hoerspiel+erzaehltext) × **2 Varianten A/B**
  = 20 Texte, mit Bildern+Quiz+Lektorat, Prompt v2_B, gemini-3.5-flash. Runner
  `_nightly_5themen.py` (lokal/ignored), Task `Wissensfreund_Nachtlauf_5Themen`.
  Ausgabe: `Desktop/Wissensfreund_Review/2026-08-01_Nachtlauf_5Themen/` — je Variante
  eine Review-Docx (2-spaltig, Korrekturspalte). **Morgen früh prüfen/lesen.**
- **Sauberer Stand hergestellt — Arbeitsbaum komplett clean (0 modifiziert, 0 untracked).**
  Kein offener Code-Umbau; Produktion = Gemini Flash (BASE + v2_B).
- **Aufräumen abgeschlossen (Teil 2, e987ff8):** untracked-Artefakte gebändigt.
  Behalten+getrackt: 3 TTS-Cast-Skripte, 6 `scripts/`-Tools, 9 Wortbudget-/Ergiebigkeits-XLSX,
  `scripts/bewertung.py` (Rubrik-Scorer, bleibt für Flash-A/B). `.gitignore`: `articles/` pauschal
  (nur Experiment-Output; 88 echte Artikel bleiben getrackt) + Ausgabeordner + Archiv.
  Alte Prompt-Versionen/Architektur-Notizen → lokal `archiv/aufraeumen_2026-07/` (aus Git verborgen,
  nicht hart gelöscht). Reine Maschinen-Dumps (audit_*, test_*, Caches) gelöscht.

## Offen nach Priorität

1. **Vertonung (Task D):** `tts_story.py` auf den festen 16-Figuren-Cast ([[project_story_cast]]) erweitern,
   ein gutes Hörspiel echt vertonen → „überleben die Charakterstimmen?".
2. **Handy/Tablet-Ansicht** des guten Stands prüfen (Absatzlängen, Bild-Platzierung). Handy-Modus vorher absprechen.
3. **Bild-Auswahl-Tiefe:** überflüssige Bilder droppen + fehlende Motive — Vision-Pool/Filter-Arbeit, nach dem Text.
4. **Stufen-Umbau Rest (Plan §7):** §7.3 Upload/Index (age_floor, 2 Typen), §7.4 App (ID-Mapping/Filter).
5. **CI-Migration (KNOWN_OPEN):** Workflow ruft noch Legacy `generate_articles.py` statt `run_batch.py`.
6. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button, TEMP-Prints in `_prepareNarration` (`home_screen.dart`).

<!-- Detail-Historie verbatim in STATUS_ARCHIV.md. -->
