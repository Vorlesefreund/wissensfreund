# Wissensfreund — STATUS
<!-- updated: 2026-06-02T06:53:28Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-02 — Phase 1: Quiz + Callout-Boxen)

- **CalloutBox-Widget** (`lib/widgets/callout_box.dart`)
  - Typen: wow 🤩 / fakt 🔍 / stimmt_das 🤔 / warnung ⚠️
  - stimmt_das mit Reveal-Mechanismus: Tippen deckt ✅/❌ + Erklärungstext auf
- **QuizWidget** (`lib/widgets/quiz_widget.dart`)
  - Schritt-für-Schritt, eine Frage auf einmal
  - Antwort-Feedback: grün/rot; richtige Antwort immer grün markiert
  - Ergebnis-Anzeige: "X von Y richtig" + Emoji (🎉/👍/🤔)
- **WfBox-Modell** erweitert: revealMode (bool), answer (bool?), explanation (String?)
- **RenderedBox + Converter** entsprechend aktualisiert
- **Provider**: articleSections + articleQuiz Getter, populate + clear
- **article_screen.dart**: `_insertSectionBoxes()` Helper; Modus A+B: Boxen nach Abschnittsende, Quiz am Artikelende; Modus C: keine Änderung
- **Test-Asset** `assets/test/elefant_l2.json`: Boxen + Quiz vollständig befüllt (5 Sektionen, 4 Boxen, 4 Quizfragen)
- APK gebaut + installiert ✅

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 — UI-Feinschliff)

- Mode B: Artikelbild 0.32 (clamp 180–300dp), Satz-Anfang bei 30%
- Mode C: Attribution bei _kMicClear=80dp sichtbar
- Mikrofon: Toggle-Funktion
- Mode A: Scroll-Trigger 35%, alignment 0.18
- ZIM-Seek: respektiert startSpeaking-Parameter

---

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Manuell testen** (Checkliste aus CLAUDE_CODE_PHASE1_QUIZ_CALLOUT.md)
- **Selbst produzierte Artikel** (neue JSON-Artikel mit echten Inhalten)

### Mittel (zurückgestellt)
- **Quiz-Checkpoint löschen + Run neu starten**
- **Bilder-Patch** (`patch_article_images_v1.py`)
- **Links in JSON-Artikeln**
- **Gemini-Integration**
- **Topic-Tree Kachel-Navigation**

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1

- Gallery-Artikel (111 Artikel, 540 Bilder)
- Audio-Pipeline
