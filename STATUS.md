# Wissensfreund — STATUS
<!-- updated: 2026-07-24T07:42:37Z -->
<!-- Ältere Stände (verbatim, inkl. TTS-Woche 16.-18.07. + Stufen-Umbau 19.07.) → STATUS_ARCHIV.md · `git log STATUS.md` · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder. Profil 3-stufig (4–6/7–9/10–12, steuert Modi), **Inhalt 2-typig**:
Hörspiel (4–9) + Erzähltext (10–12, = altes S3). KI streng aus geladenem Quelltext (nie Trainingswissen).
**Zwei getrennte Text-Motoren** (bewusst) → [[project_zwei_textmotoren]].

## Zuletzt abgeschlossen (2026-07-23) — S3 wiederhergestellt + Hörspiel-Plan-Split

- **S3-Wiederherstellung (Kern):** Der Erzähltext lief seit dem Stufen-Umbau (19.07.) versehentlich über den
  Einzel-Call statt über das gute 6-Schritt-System — das war die Ursache der schlechteren Prosa. `generate_one_level`
  verzweigt jetzt für `content_type=="erzaehltext"` (nur Gemini, nicht Claude) in `_generate_erzaehltext_6pass()`
  → ruft `pipeline_new.generate_article_new` (pass1-6). Nur der Text-Motor getauscht; Naming, Meta, Kompass,
  Bild-nach-Text, Nachtlauf, Docx bleiben. Hörspiel unberührt. Import-Dreieck zirkelfrei (lazy).
- **Hörspiel-Plan-Split (neue Mechanik, NEU heute):** Überträgt die 6-Schritt-Lehre aufs Hörspiel — SCHRITT 1
  (Planung) läuft in einem EIGENEN Gemini-Aufruf vorab (`_hoerspiel_story_plan`), der fertige `<planung>`-Block
  geht als STORY_PLAN in den Schreib-Aufruf (SCHRITT 2). Steht im variablen Suffix (artikelspezifisch, kein
  Cache-Eingriff). **KEIN Qualitäts-Fallback (PO 2026-07-23):** scheitert der Plan-Aufruf (503/leer/kein
  `<planung>`), gilt das Hörspiel als NICHT erzeugt (`generate_one_level`→`None`) → Nachtlauf läuft es off-peak
  neu an, statt still im schwächeren Einzel-Call zu landen. `call_gemini` wiederholt intern schon 5× (Ausfall
  selten). Prompt-Regel „SCHRITT 1 überspringen, wenn STORY_PLAN da" ergänzt. Offline getestet.
- **DEFER_IMAGES (Bilder nach dem Text):** Bildpool geht NICHT mehr in den Schreib-Call; `assign_images_pass`
  ordnet Bilder dem fertigen Text zu (Rückkehr des pass4-Prinzips). Behebt Erzähler-als-Figur + Stakkato.
- **Companion-Bild-Garantie:** `select_images_for_stufe` sichert 1 Bild je Quelle VOR dem Relevanz-Cap →
  behebt „Archaeopteryx fehlt" (Pool hatte 6, Cap schnitt den ganzen Companion weg).
- **Bild-Platzierung:** `images[].placement = inline|galerie` — 4–8 textbegleitend, Rest als Galerie ans Ende.
  SVG beim Hörspiel raus, sonst Galerie. (App rendert `placement` noch NICHT — Handy-Modus unangetastet.)
- **Box-Redundanz:** `find_redundant_boxes` (Overlap Box↔ganzer Fließtext ≥0.60) + `regenerate_redundant_boxes`
  (Box mit NEUEN Quellfakten neu statt löschen — PO will die Boxen behalten). Behebt Vulkan-Wiederholungs-Boxen.
- **Sprecherwechsel-Wächter:** `_split_double_speech_lines` misst Sprecher-Turns (regex), nicht Zeilenzahl —
  lange Einzel-Monologe lösen keinen Fehlalarm mehr aus. Ersetzt die untaugliche Zeilen-Schranke [15,60].
- **Kleinfixe:** But→Aber/And→Und (`fix_language_slips`), Querformat-Hero (`enforce_landscape_hero`),
  „Tiefe vor Breite" im Prompt geschärft, Kompass-Companion-Wahl geschärft.

## Gerade in Arbeit / Nächster Schritt

- **Lauf erfolgreich (2026-07-24 ~09:40, Tageslauf nach Guthaben-Auffüllung):** 6/6 Artikel. Beide Umbauten
  liefen ERSTMALS real durch — 6× 6-Schritt-System (Erzähltext), 3× Story-Plan-Split (Hörspiel, Plan 4,9–7,6k Z.).
  Auto-Checks grün: 0× Erzähler-als-Figur, 0 Engl.-Slips, Archaeopteryx-Bild bei beiden Dino-Artikeln, Hörspiel
  0 Boxen / Erzähltext je 3. Docx im Desktop-Ordner `2026-07-24_Review2` (Review + 3× `<Thema>_alt_vs_neu`, je 2 ★NEU).
- **Der 03:00-Nachtlauf war reines Billing** (Prepaid-Guthaben leer, 429 — NICHT 503): 0/6, 5,5 h Retry verheizt.
  Fixes: `gemini_client.is_billing_depleted` bricht in allen 4 Retry-Stellen sofort ab; `gemini-2.5-flash`-
  Kompass-Fallback ersatzlos entfernt (PO-Regel). `--pause` im Nachtlauf wird bei Guthaben-leer nicht mehr abgewartet.
- **PO prüft jetzt am Text:** liest sich der restaurierte S3-Text wie der gute 10.07.-Vulkan-Text? Bringt der
  Plan-Split bessere Fenster-Struktur? (Optional offen: 10.07.-Baseline fest in die alt↔neu-Docx einpinnen.)
- **Automatischer Vergleich alt↔neu** hängt der Nachtlauf nach der Review-Docx an (`historie_uebersicht.py
  --fokus 4`): frische Fassungen ★NEU-markiert + 4 jüngste alte, chronologisch mit Pipeline-Label.

## Offen nach Priorität

1. **Task D — Vertonungs-Test:** `tts_story.py` auf den festen 16-Figuren-Cast ([[project_story_cast]])
   erweitern (Stimme + Stil je Figur), ein v2-Hörspiel echt vertonen → „überleben die Charakterstimmen?".
2. **Stufen-Umbau Rest (Plan §7):** §7.3 Upload/Index (age_floor, 2 Typen), §7.4 App (ID-Mapping/Filter
   `_hoerspiel`/`_erzaehltext`).
3. **TTS-Produktion in Serie:** Batch temp 0.3 + 10 Runden + QA; VC auf EINEM Pod → [[project_tts_produktions_pipeline]].
4. **CI-Migration (KNOWN_OPEN):** Workflow ruft noch Legacy `generate_articles.py` statt `run_batch.py`.
5. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button, TEMP-Prints in `_prepareNarration` (`home_screen.dart`).
6. **Tablet-Pass** (eigener Chat!): tablet-zentrieren. **Handy-Modus bleibt unangetastet** — vorher absprechen.

<!-- Detail-Historie (TTS-Woche, Stufen-Umbau, Wal-Läufe) verbatim in STATUS_ARCHIV.md. -->
