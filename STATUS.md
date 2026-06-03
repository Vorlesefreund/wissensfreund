# Wissensfreund — STATUS
<!-- updated: 2026-06-03T13:54:57Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — Mode A: Anker-Scan + Box-Seek)

### Mode A: vollständiger Port von Mode B's Scroll-/Seek-Logik
- `_boxKeys` + `_lastBoxKey` in `_ModeAContentState` ergänzt
- `_insertSectionBoxes` in Mode A nun mit `boxKeys: _boxKeys` → Boxen haben GlobalKeys
- `_jumpToTopSentence` komplett ersetzt: Live-Scan (Sätze + Boxen, `localY >= 0`)
  - charOffset via `_splitSentenceStarts()` statt alter Längen-Summe
  - `seekToChunk` für JSON, `seekWithDelay` + `\n`-Fix als ZIM-Fallback
  - Box-Anker-Logik + `seekToChunk(topBoxChunkIdx)` — exakte Spiegelung Mode B
  - „1–2 Sätze voraus"-Toleranz entfernt (A/B-Konsistenz)
  - `!_cacheBuilt`-Guard entfernt (Live-Scan braucht keinen Cache)
- `_smartScrollToBox` hinzugefügt (TTS-Auto-Scroll zu Boxen)
- `_suspendAutoScrollOnce` mit Box-Tracking (wie Mode B)
- `build()`: `rawIdx`/`scrollIdx`-Split, Box-Auto-Scroll-Block, `_boxKeys.clear()` bei Artikel-Reset
- Getestet auf S23 ✅ — Satz-Seek, Box-Seek, Snap-Back-Szenarien alle bestanden

---

## 🟡 Zum Testen (noch ausstehend)
- Manuell testen — ImageFullscreenOverlay (aus voriger Session)
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche in Mode A)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten (zu früh springendes Highlight)

---

## 🔴 Offene To-Dos (nach Priorität)

### Hoch — eigener Refactor nötig
- **Epoch-Guard für TTS-Seek**: `_ttsStopPending`-Mirror hat auf sehr langsamen Geräten
  ein Zeitfenster — feuert `stop()` sein `onDone` erst nach den 1200 ms, läuft es als
  „neuer Chunk fertig" durch und der frische Satz wird abgeschnitten.
  Echte Cross-Device-Lösung: Epoch-/Generations-Zähler (oder `awaitSpeakCompletion(true)`
  + `await` statt globalem `setCompletionHandler`).
  Betrifft 5+ Seek-Stellen im Provider — eigener Refactor.

### Mittel
- **Mode-B-ZIM-`\n`-Loch**: Mode B's `seekWithDelay`-Fallback (Zeile ~2670) hat keinen
  `\n`-Fix für heading-merged Sätze, Mode A schon. Für A/B-Konsistenz angleichen.
- **1-Satz-Toleranz**: Ohne die alte „1–2 Sätze voraus"-Toleranz löst jeder kleine
  Korrektur-Scroll Unterbrechen+Seek aus. Falls ruckelig: 1-Element-Toleranz zurückbauen.
- **Selbst produzierte Artikel** (neue JSON-Artikel mit echten Inhalten)
- **Quiz-Checkpoint löschen + Run neu starten**
- **Bilder-Patch** (`patch_article_images_v1.py`)

### Niedrig
- **Links in JSON-Artikeln**, **Gemini-Integration**, **Topic-Tree**
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
