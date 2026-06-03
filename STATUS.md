# Wissensfreund — STATUS
<!-- updated: 2026-06-03T07:24:22Z -->

---

## Zuletzt abgeschlossen

### Scroll-Navigation: chunk-index-basiertes Anker-System (Commit d38caf4)
- **Problem**: Snap-Back nach User-Scroll, Box-Chunks beim Seek übersprungen,
  charOffset-Summe hatte Off-by-1-Fehler nahe Box-Grenzen
- **Fix**: `seekToChunk(chunkIndex)` — direkter Chunk-Seek ohne charOffset-Mapping
- **Anker-Scan**: `_jumpToTopSentence` Mode B iteriert Sätze UND Boxen,
  wählt das topmost Element mit `localY >= 0` als Anker
- **Symmetrisch**: Satz-Branch und Box-Branch rufen beide `seekToChunk` auf
- **ZIM-Fallback**: `sentenceChunkForOffset == -1` → weiter mit `seekWithDelay`
- **Getestet**: ✅ Scrolling klappt einwandfrei am Gerät

### Frühere Fixes (Session 2026-06-02)
- `_suspendAutoScrollOnce` Helper (9eb5907) — Snap-Back Pfad 1+2
- `seekWithDelay` + `_ttsStopPending` (99115f7) — TTS-Stop nach Scroll

---

## Offen — nach Priorität

### Hoch
- **Epoch-Guard für TTS-Callbacks** (separater Refactor):
  `_ttsStopPending` hat Zeitfenster auf langsamen Geräten: feuert `stop()` sein `onDone`
  erst nach 1200ms, läuft es als „neuer Chunk fertig" durch. Lösung: `setCompletionHandler`
  vor jedem `speak()` neu registrieren (Closure capturt Epoch-ID). Betrifft 5+ Stellen.
- **1-Satz-Toleranz beobachten**: Scroll um einen Satz → sofort Seek + 1,2s Pause.
  Falls ruckelig: Toleranz-Zweig (topIdx == activeIdx+1) wieder einbauen.
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche in Mode A)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten

### Mittel (zurückgestellt)
- Selbst produzierte Artikel, Quiz-Checkpoint, Bilder-Patch, Links, Gemini, Topic-Tree

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
