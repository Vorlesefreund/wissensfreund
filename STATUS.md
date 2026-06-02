# Wissensfreund — STATUS
<!-- updated: 2026-06-02T12:56:39Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-02 — TTS-Seek + Scroll-Bugs)

### Bugfixes in dieser Session

- **Endlosschleife stimmt_das** (AnimatedCrossFade → _jumpToTopSentence Schleife): `currentChunkIsBox`-Guard
- **Box-Highlighting**: `isActive`-Parameter in `CalloutBox`, Highlight beim Vorlesen
- **TTS 5s-Pausen**: `_chunkIsStimmtExpl`-Alignment-Bug behoben (alle Chunks müssen `false` eintragen)
- **Screen-Dimming**: `FLAG_KEEP_SCREEN_ON` per Window-Attribut; "reading"=Flag setzen, "awake"=clearFlags
- **Box-Zentrierung**: `_smartScrollToBox` zentriert Box jetzt korrekt: `boxTopInContent - vpH/2 + boxHeight/2`
- **Box-Koordinaten-Tracking**: `_chunkBoxSectionMap`/`_chunkBoxInSectionMap` für aktive Box-Hervorhebung
- **Doppel-Vorlesen "Elefantenbabys"-Satz** (Root Cause: Heading-Gap):
  - Abschnittsüberschriften ohne Satzzeichen werden in `_splitSentences` mit dem ersten Satz gemergt
  - berechneter `charOffset` landete im Heading-Gap → Seek ging auf falschen Satz zurück
  - **Fix**: nach `charOffset`-Berechnung `\n` in `sentences[topIdx]` suchen; falls vorhanden, `charOffset += nl + 1`
- **Snap-Back nach Box-Bereich scrollen** (topIdx = -1):
  - Wenn User über alle Sätze hinausscrollt, wurde `_userScrolling = false` gesetzt → Consumer scrollte zurück
  - **Fix**: `topIdx < 0` → `_seekResumeTimer` 2 s setzen, `_userScrolling` bleibt true
- **Seek zu spät** (Folgesatz wird noch gelesen):
  - `seekAfterCurrentChunk` wartet auf aktuellen Chunk-Abschluss
  - **Fix**: neues `seekNow()` in Provider — stoppt TTS sofort, springt direkt zum Ziel
  - Debounce 800 ms → 300 ms reduziert
- **Seek-Genauigkeit** (Mode A+B): `seekAfterCurrentChunk` → `seekNow`, 3s → 2s _seekResumeTimer

Geänderte Dateien:
- `lib/providers/wissensfreund_provider.dart`: `seekNow()` Methode, `_chunkIsStimmtExpl`-Fix, Screen-Mode
- `lib/screens/article_screen.dart`: Mode A+B `_jumpToTopSentence` komplett, `_smartScrollToBox` Zentrierung
- `lib/widgets/callout_box.dart`: `isActive` Highlighting
- `android/.../MainActivity.kt`: `setScreenMode` (reading/awake/dim/off)

APK gebaut + installiert ✅

---

## 🟡 Noch nicht getestet (zum Testen)

- Scroll past boxes → kein Doppel-Vorlesen mehr
- Seek springt sofort (nicht nach Folgesatz)
- Zweite Box ist korrekt zentriert
- Box-Highlight beim Vorlesen sichtbar
- Kein Screen-Dimming während TTS

---

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Manuell testen** (alle Bugfixes aus dieser Session)
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
