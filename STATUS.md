# Wissensfreund — STATUS
<!-- updated: 2026-06-02T21:37:38Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen

### Problem 1 — TTS stoppt nach User-Scroll (Commit 99115f7)
- **Ursache**: `_ttsStopPending` blieb `true` nach `seekWithDelay`, weil Android-TTS `stop()` kein `onDone` feuert
- **Fix**: `_ttsStopPending = false` in `_seekDelayTimer`-Callback in `wissensfreund_provider.dart`
- **Getestet**: ✅ bestätigt funktionierend

---

## 🔴 Gerade offen — Problem 2: Snap-Back nach User-Scroll

### Was eingebaut ist (article_screen.dart, noch nicht committed)
- Neues Feld `bool _skipNextAutoScroll = false` in `_ModeAContentState` + `_ModeBContentState`
- 2s-Timer-Callbacks (Mode A + B): `_skipNextAutoScroll = true` vor `_userScrolling = false`
- Consumer Mode A + B: `_smartScrollTo` nur wenn `!_skipNextAutoScroll`, sonst `_lastActiveIdx` synchen
- Mode B Artikel-Reset: `_skipNextAutoScroll = false`

### Warum der Fix unwirksam ist — zwei Snap-Back-Pfade identifiziert

**Pfad 1 — `currentChunkIsBox`-Early-Return (article_screen.dart Zeile 2538)**
Wenn TTS während der ~600ms (Scroll-Debounce) von Satz N in Box wechselt:
- `_jumpToTopSentence` → `currentChunkIsBox = true` → `_userScrolling = false; return;`
- Consumer Box-Branch: `_smartScrollToBox()` → Snap zur Box
- `_skipNextAutoScroll` nie gesetzt (2s-Timer wurde von `_onScroll` via `_seekResumeTimer?.cancel()` abgebrochen)

**Pfad 2 — `topIdx == activeIdx + 1/2`-Zweig (Zeile 2582)**
Wenn Satz M (Ziel-Scroll) nur 1–2 Sätze nach Box liegt:
- 3s-Timer ohne `_skipNextAutoScroll = true`
- Consumer Satz-Branch: `_smartScrollTo(currentTTSIdx)` → Snap zur TTS-Stelle

### Nächster Schritt (für Opus)
Vollständige Code-Analyse aller Pfade in `_onScroll`, `_jumpToTopSentence` und Consumer-Block,
dann gezielter Fix für beide Snap-Back-Pfade:
- Pfad 1: `currentChunkIsBox`-Early-Return: entweder entfernen oder durch Timer+`_skipNextAutoScroll` ersetzen
- Pfad 2: `topIdx == activeIdx + 1/2`-Timer: `_skipNextAutoScroll = true` ergänzen

---

## 🟡 Weitere offene Punkte (nach Priorität)

### Hoch
- **Problem 3**: Snap-Back während Box-Playback — User scrollt während Box → nach Box Snap zu Satz N+1
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche in Mode A)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten (zu früh springendes Highlight)

### Mittel (zurückgestellt)
- Selbst produzierte Artikel, Quiz-Checkpoint, Bilder-Patch, Links, Gemini, Topic-Tree

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
