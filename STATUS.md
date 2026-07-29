# Wissensfreund — STATUS
<!-- updated: 2026-07-29T06:05:12Z -->
<!-- Ältere Stände (Review4, S3-Wiederherstellung, TTS-Woche, Stufen-Umbau) → git log STATUS.md · STATUS_ARCHIV.md · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder. Profil 3-stufig (4–6/7–9/10–12, steuert Modi), **Inhalt 2-typig**:
Hörspiel (4–9) + Erzähltext (10–12, = altes S3). KI streng aus geladenem Quelltext (nie Trainingswissen).
**Zwei getrennte Text-Motoren** (bewusst) → [[project_zwei_textmotoren]].

## Zuletzt abgeschlossen (2026-07-29) — KEHRTWENDE: Rückbau auf den letzten guten Stand (PO)

- **Kernentscheidung (PO):** Die Prompt-Iteration v4→v8 (25.–28.07.) hat die Qualität NICHT verbessert,
  sondern verschlechtert (Stakkato, „durcheinander", Theo nimmt Fakten vorweg, schwacher Schluss). PO:
  „Es wird nicht besser." → Rückbau auf die guten Stände: **Hörspiel = `nacht_review2` (24.07),
  Erzähltext = `bakeoff_BASE` (25.07)**. Gold-Referenz in `articles/_GOLD_dino_baseline/`.
- **Ursache (eindeutig, git-belegt):** Die Experiment-Runner `_v7/_v8_nightly.cmd` erzwangen
  `WF_PROMPT_VARIANT=pro` → die **PRO-Prompts** (ab 25.07, `7109798`/`6e30287`) = degradiert. Das Hörspiel
  degradierte separat über die externen `--hoerspiel-prompt`-Dateien (v4–v8). **Die guten Prompts lagen die
  ganze Zeit im Code:** BASE (`_pick()`, pipeline_new.py) + Default-Hörspiel `wissensfreund_hoerspiel_prompt_v2_B.md`.
- **Rückbau = KEINE funktionale Code-Änderung:** Der Produktions-Runner `_nightly_rerun.ps1` (via `run_batch.py`)
  nutzte nie `pro`/`--hoerspiel-prompt` → er war **schon immer** auf dem guten Stand. Nur die Experiment-Runner
  `_v7`/`_v8` entfernt (forcierten den schlechten Pfad). PRO-Prompt-Code bleibt dormant hinter dem Default-off-Schalter.
- **Validierung (off-peak `WF_Restore_Test`, 29.07. 03:00, kein 503):** Dino/Vulkan/Spielzeug auf Plain-Config
  (BASE + v2_B) neu erzeugt → `articles/restore_20260729/`. Dino gegen Gold geprüft: **gut, auf Niveau/darüber** —
  kein Stakkato, geordnete Kohärenz, Theo maßvoll, starker Schluss, „Wettstreit" statt „Wettwahn", keine
  zerschnittenen Zitate. Review-Docx: `Desktop/Wissensfreund_Review/2026-07-29_restore/Review_Restore.docx`.
- **Behaltene echte Fixes:** Zitat-Splitter-Bugfix (`_split_double_speech_lines` über `_line_ranges`, `1d5f822`) —
  reiner Gewinn, bleibt drin. Lektorat 8a/8b/8c + Alters-Leitplanke bleiben (additiv, nur bei Problemfällen).

## Gerade in Arbeit / Nächster Schritt

- **Rückbau festgeschrieben + gepusht** (`1d5f822` + Restore-Commit). Produktions-Default = BASE + v2_B.
- **PRO-Prompts + v4–v8-Hörspiel-Prompts sind deprecated** — nicht wieder `WF_PROMPT_VARIANT=pro` setzen,
  kein `--hoerspiel-prompt vX` mehr. Wer neu läuft: schlicht `run_batch.py`/`generate_grounded.py` ohne diese Schalter.
- **Nächster Produktionslauf** kann über `_nightly_rerun.ps1` (Datum/Themen anpassen) oder direkt gefahren werden.

## Offen nach Priorität

1. **Vertonung (Task D):** `tts_story.py` auf den festen 16-Figuren-Cast ([[project_story_cast]]) erweitern,
   ein gutes Hörspiel echt vertonen → „überleben die Charakterstimmen?".
2. **Handy/Tablet-Ansicht** des guten Stands prüfen (Absatzlängen, Bild-Platzierung). Handy-Modus vorher absprechen.
3. **Bild-Auswahl-Tiefe:** überflüssige Bilder droppen + fehlende Motive — Vision-Pool/Filter-Arbeit, nach dem Text.
4. **Stufen-Umbau Rest (Plan §7):** §7.3 Upload/Index (age_floor, 2 Typen), §7.4 App (ID-Mapping/Filter).
5. **CI-Migration (KNOWN_OPEN):** Workflow ruft noch Legacy `generate_articles.py` statt `run_batch.py`.
6. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button, TEMP-Prints in `_prepareNarration` (`home_screen.dart`).

<!-- Detail-Historie verbatim in STATUS_ARCHIV.md. -->
