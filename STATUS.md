# Wissensfreund — STATUS
<!-- updated: 2026-06-01T18:01:03Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 nacht)

### 3 neue Bugs nach APK-Install behoben

**Bug 1 — Mode A Auto-Scroll dauerhaft gebrochen:**
`_userScrolling = false` an allen 5 Early-Returns + nach `seekAfterCurrentChunk` ergänzt.

**Bug 2 — Mode B Text unter Professor-Widget:**
Scroll-Schwelle auf `viewportH * 0.35`, Bottom-Padding auf `_kProfZone` (220 dp).

**Bug 3 — Bilder zeigen keinen Lade-Zustand:**
`CircularProgressIndicator` (grün, strokeWidth 2.5) während `ConnectionState.waiting`.

Commit `wissensfreund_app`: `d487458` ✅

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 abend — diese Session)

### Modus C — Slider-Navigation + Headings-Fix

**🔊 Taste nach oben verschoben:** Von unterhalb Bild → `top: 90` (knapp oberhalb Titelzeile).

**Pfeile ‹/› ersetzt durch Slider + Skip-Icons:**
- ⏮ (`skip_previous_rounded`) | Slider | ⏭ (`skip_next_rounded`)
- Slider zeigt satzweise Position im Artikel, `divisions = totalChunks - 1`
- `_sliderDragValue`: lokaler State während Drag — verhindert Snap-Back durch Consumer-Rebuilds

**Navigation: sektionsweise → satzweise (chunk-level):**
- `totalChunks` Getter in Provider (`_speechChunks.length`)
- `_prevChunk`/`_nextChunk` statt `_prevSection`/`_nextSection`
- `jumpToSection(offset)` — neue Methode, unterbricht TTS sofort

**Kapitelüberschriften werden jetzt vorgelesen:**
- Heading dem ersten Satz jeder Sektion vorangestellt: `'$heading. ${s.text}'`
- `_chunkOffsets`/`_chunkImgIndices` bleiben korrekt (`s.startChar`)

**`jumpToSection()` vs `seekAfterCurrentChunk()`:**
- `jumpToSection`: sofortiger Interrupt — `_isPaused = true` → stop → seek → speak
- `seekAfterCurrentChunk`: deferred — queued `_pendingSeekOffset`, wirkt erst nach Satz-Ende

**autoCompactWindow** auf 500.000 erhöht.

---

## 🔴 Gerade in Arbeit / Unterbrochen

### Quiz-Generierung — Checkpoint-Problem

- Run `26741537309`: 609 von 3.544 Quizzen generiert, Artikel-Artefakt NICHT hochgeladen → verloren
- Checkpoint auf R2 → 609 als "erledigt" markiert → werden übersprungen
- **→ Checkpoint MUSS gelöscht werden**

```
aws s3 rm s3://wissensfreund-articles/staging/checkpoints/quiz_checkpoint.json \
  --endpoint-url "https://<CF_ACCOUNT_ID>.r2.cloudflarestorage.com"
```
Dann `quiz_and_upload.yml` manuell triggern. Laufzeit ~8.9h → 2 Runs nötig.

---

## 🟡 Offen — nächste Schritte

### Hoch
- **Quiz-Checkpoint löschen + Run neu starten** (s.o.)
- **Bilder-Patch** nach Quiz-Run: `patch_article_images_v1.py`
- **App-Umbau Schritt B: Renderer** — Quiz-Widget, Callout-Boxen

### Mittel
- **Gemini-Integration** — `_detectQueryType()` vorhanden, `_handleGeminiPlaceholder()` Einstiegspunkt
- **Topic-Tree Kachel-Navigation** in der App

### Niedrig
- Upgrade-Dialog für Free-User bei Rückfrage (wartet auf Gemini)
- Plus & Premium Dialog: Design-Vorgaben ausstehend
- Sound-Thumbnails: wartet auf Audio-Pipeline-Run

---

## 🔵 Verschoben auf Version 1.1

- Gallery-Artikel (111 Artikel, 540 Bilder) — braucht eigene UI-Komponente
- Audio-Pipeline — separater GitHub Actions Run

---

## Wissensdokumente (bei Bedarf lesen)

| Datei | Inhalt |
|---|---|
| `WISSEN_BILDER.md` | Bild-Pipeline, R2-Struktur, verworfene Ansätze |
| `WISSEN_ARTIKEL_PIPELINE.md` | JSON-Schema, Altersstufen, Pipeline-Skripte, Related Terms |
| `WISSEN_APP_ARCHITEKTUR.md` | Services, Freemium, Frage-Typen, Navigation+Sync, Designentscheidungen |
