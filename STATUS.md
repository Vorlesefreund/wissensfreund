# Wissensfreund — STATUS
<!-- updated: 2026-07-24T14:43:55Z -->
<!-- Ältere Stände (verbatim, inkl. TTS-Woche 16.-18.07. + Stufen-Umbau 19.07.) → STATUS_ARCHIV.md · `git log STATUS.md` · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder. Profil 3-stufig (4–6/7–9/10–12, steuert Modi), **Inhalt 2-typig**:
Hörspiel (4–9) + Erzähltext (10–12, = altes S3). KI streng aus geladenem Quelltext (nie Trainingswissen).
**Zwei getrennte Text-Motoren** (bewusst) → [[project_zwei_textmotoren]].

## Zuletzt abgeschlossen (2026-07-24) — Review4-Feedback umgesetzt (PO)

- **Theo = 8-Jähriger, präzise** (Hörspiel-Prompt §C, `6c0a4f5`): vier Achsen *denkt/fühlt/spricht/fragt* +
  „Vermeide 3–5-Jährigen-Verhalten" + verschärftes **„Redeanteil klein"** (pro Fenster ≤1 Reaktion, Fenster
  ganz ohne ihn, jede Zeile prüfen). Behebt: zu großer Theo-Anteil + unnötige/blöde Fragen (Dino-/Spielzeug-HS).
- **PASS1 Gegenwartsbezug** (`6c0a4f5`): Erzähltext-Plan bevorzugt heute bekannte, ikonische Vertreter (die
  gelieferten Begleitartikel = Anker) statt trockener Chronologie/Herstellung/Zölle/Prüfsiegel. Behebt
  Spielzeug-S3 (Steinzeit→CE-Siegel statt Lego/Steiff/Teddy). Allgemein, kein Themen-Hardcoding.
- **Lektorat wieder AN + erweitert** (`6c0a4f5`, [[project_lektorat_off]]): Nachtlauf ohne `--skip-lektorat`
  (Default AN). `LEKTORAT_SYSTEM` prüft zusätzlich **Sinn/Plausibilität/Kontinuität** (Quellen-Widerspruch:
  Eifel=Kaltwasser-Geysir; innerer Widerspruch: Hühnerknochen→Schnitzelknochen; unplausible Requisite:
  „immer ein großes Buch dabei"; Register/Jargon: Oma spricht Fachsprache) + **Dezimalregel** (4,4 cm → „knapp
  viereinhalb"). Entlastet den Flash-Prompt (Konsistenzarbeit statt weitere Frankenstein-Zeile).
- **Bild-Caption nutzt Originaltitel** (`4380a15`): Caption (beide Motoren) darf Eigenname/Ort des Exponats aus
  dem Commons-Originaltitel nennen (Metadaten ≠ erfundenes Detail); Anti-Halluzinations-Guard bleibt.
- **Nächster Lauf terminiert:** Task `Wissensfreund_Nachtlauf_Review5`, 2026-07-25 02:30, 4 Anläufe, Lektorat AN.

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

- **Review5-Nachtlauf abwarten (2026-07-25 02:30):** erster Lauf mit Theo-8J-Profil + Gegenwartsbezug +
  reaktiviertem/erweitertem Lektorat + Originaltitel-Captions. Review-Docx morgen früh im Desktop-Ordner
  `2026-07-25_Review5` (inkl. Prüfbericht, da Lektorat AN). PO prüft: weniger Fehler, lebendiger, Theo kleiner?
- **Erweitertes Lektorat beobachten:** über-/unterkorrigiert die neue Sinn/Plausibilitäts-Prüfung? Erste Läufe
  gegenlesen (Grounding-Charakter bewusst konservativ gehalten, aber neue Dimension ist ungetestet an echten Läufen).
- **Flash-Beratung offen** (503 tagsüber): „wie Geschichten lebendiger/flüssiger" — off-peak neu anlaufen,
  Antwort dann in PASS2/Sprachhandwerk einarbeiten (Skript `scratchpad/flash_advice.py`). Kein 2.5-flash-Ausweich.
- **Bild-Auswahl-Tiefe (Folgerunde):** überflüssige Bilder aggressiver droppen + fehlende Motive (T-Rex) —
  das ist Vision-Pool/Filter-Arbeit, bewusst NACH dem Text-/Lektorat-Stand, nicht vor dem Nachtlauf.

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
