# Wissensfreund — STATUS
<!-- updated: 2026-06-02T09:23:19Z -->
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
- APK gebaut + installiert ✅ (Phase 1 vollständig)
- **Modus B Quiz** via BottomSheet (`_QuizStartButton` in article_screen.dart)
- **Bilder im Test-JSON** (`elefant_l2.json`): echte Wikimedia-thumb_urls statt Placeholder-PNGs

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 — UI-Feinschliff)

- Mode B: Artikelbild 0.32 (clamp 180–300dp), Satz-Anfang bei 30%
- Mode C: Attribution bei _kMicClear=80dp sichtbar
- Mikrofon: Toggle-Funktion
- Mode A: Scroll-Trigger 35%, alignment 0.18
- ZIM-Seek: respektiert startSpeaking-Parameter

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-02 — Bug-Fix-Runde)

- **Callout-Boxen Modus A** nicht sichtbar → `_insertSectionBoxes` neu: text-content-matching statt startChar-Algo
- **Bilder-Platzhalter** Header: emoji+themeColor aus JSON-Artikel (neu: `articleEmoji`, `articleThemeColor` im Provider)
- **Thumbnail-Platzhalter** sichtbar: neuer `_ThumbTile` + `_ThumbnailRow` direkt von `articleImages` (nicht mediaItems)
- **stimmt_das Reveal**: zentrierter Text, abwechselnde Richtig-Phrasen, Falsch-Prefix "Das ist leider nicht ganz richtig."
- APK gebaut + installiert ✅

## 🟢 Zuletzt abgeschlossen (Session 2026-06-02 — Thumbnail-Bug-Fix)

- **Root Cause gefunden**: `elefant_l2.json` Zeile 132 hatte ein ASCII-`"` (U+0022) inmitten einer JSON-String, was `FormatException` auslöste → `_loadFromAsset` → null → 0 Bilder
- **Fix**: Ersetzt durch typografisches `"` (U+201D): `„Elefanten vergessen nie."`
- **`_ThumbnailRow`** refactored: images/selectedIndex/onTap als Parameter statt innerer Consumer
- **`_ThumbTile`**: zeigt farbigen Placeholder → lädt echte Bild-Bytes via `getImageBytes()`
- **Debug-Prints entfernt**: `article_screen.dart`, `wissensfreund_provider.dart`, `json_article_service.dart` bereinigt
- APK gebaut + installiert ✅ — 5 Thumbnails sollten jetzt in allen 3 Modi sichtbar sein

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Manuell testen** (5 Thumbnail-Kacheln in Modus A/B/C, Boxen Modus A, Reveal-Texte)
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
