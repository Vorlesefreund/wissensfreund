# Wissensfreund — STATUS
<!-- updated: 2026-06-02T14:43:05Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-02 — seekWithDelay + Architekturwechsel)

### Neue Seek-Architektur (seekWithDelay)
- **Altes Verhalten**: `seekAfterCurrentChunk` — TTS liest Satz zu Ende, dann Spring zur neuen Stelle → kurzer Snap-Back
- **Neues Verhalten**: `seekWithDelay(1200ms)` — TTS stoppt sofort, 1,2s Pause, liest dann ab neuer Stelle
- **Reversierbar**: `seekAfterCurrentChunk` bleibt erhalten; Revert = 2 Zeilen in `_jumpToTopSentence` + Timer 3000ms

Provider-Änderungen:
- `_seekDelayTimer` + `_stoppedForDelayedSeek` Felder
- `seekWithDelay(charOffset, delay)` — stoppt TTS sofort (Guard gegen Doppel-Stop), startet nach Delay
- `cancelPendingSeek()` — nimmt TTS wieder auf falls durch seekWithDelay gestoppt
- `dispose()` canceliert `_seekDelayTimer`

Screen-Änderungen (Mode A + Mode B `_jumpToTopSentence`):
- `topIdx == activeIdx`: `cancelPendingSeek()` hinzugefügt (stellt TTS wieder her wenn gestoppt)
- `seekAfterCurrentChunk` → `seekWithDelay`
- `_seekResumeTimer` 3000ms → 1400ms (passt zur neuen 1200ms Delay)

APK gebaut ✅ — Gerät nicht verbunden, Installation ausstehend

### Frühere Session-Fixes (2026-06-02)
- `_lastActiveIdx` Premature-Update Bug → Auto-Zentrierung + TTS-Scroll-Hang behoben
- `_smartScrollToBox` Signatur: `(key, boxKey, rawIdx)`

---

## 🟡 Zum Testen

1. Scrolle während TTS liest → Professor hört sofort auf
2. Ca. 1,2s Pause → liest ab neuer Stelle
3. Kurz zurückscroll → TTS nimmt alten Satz wieder auf (cancelPendingSeek)
4. Auto-Zentrierung folgt TTS auch nach Scroll
5. Kein Snap-Back zur alten Stelle

---

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Manuell testen** — seekWithDelay + Zentrierung
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche in Mode A)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten (zu früh springendes Highlight)

### Mittel (zurückgestellt)
- **Selbst produzierte Artikel** (neue JSON-Artikel mit echten Inhalten)
- **Quiz-Checkpoint löschen + Run neu starten**
- **Bilder-Patch** (`patch_article_images_v1.py`)
- **Links in JSON-Artikeln**, **Gemini-Integration**, **Topic-Tree**

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
