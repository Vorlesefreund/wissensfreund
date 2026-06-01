# Wissensfreund — STATUS
<!-- updated: 2026-06-01T20:05:08Z -->
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

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 — UI-Feinschliff)

### UI-Korrekturen & Bug-Fixes

**Mode B Artikelbild größer:** `0.22→0.32`, Clamp `140–220 → 180–300dp` (~220dp auf S23).

**Mode C Attribution sichtbar:** War bei `_kMicClear-10=70dp` hinter Mic-Overlay versteckt.
Fix: Attribution `bottom: _kMicClear=80dp`, Thumbnails `bottom: _kMicClear+32=112dp`.

**Mode B Scroll-Position:** Satz-Anfang jetzt bei 30% vom Viewport-Top (war: vertikal zentriert).
Fade-Zone endet bei 18% → 30% = sicherer Puffer, erste Zeile immer sichtbar.

**Mikrofon Toggle:** Zweites Tippen schaltet Mikrofon ab (`stopListening()` wenn `isListening`).

**Mode A Scroll verbessert:** Trigger `localY > 35%` (war 50%) + `localY < 0` (Satz oberhalb).
Alignment 0.18 (war 0.15).

**Pause+Scroll Bug:** `_jumpToTopSentence` prüft jetzt `provider.isPaused` — kein Seek bei Pause.
Betrifft Mode A + B, beide Pfade gesichert.

**Scroll-Zurücksprung alte ZIM-Artikel:** `_userScrolling = true` stand nach `if (ageLevel < 2) return`.
Fix: `_userScrolling = true` VOR dem ageLevel-Check, Reset-Timer auch für Level 0/1.

**ZIM Seek-Bug:** `_seekToChunkForOffset` ignorierte `startSpeaking`-Parameter für ZIM-Artikel.
Fix: `else { if (startSpeaking) _startSpeakingFrom() else { _ttsCursor/resumeOffset setzen } }`.

**Diagnose Links im JSON-Artikel:** `WfSentence` hat kein Link-Feld → `WfArticleConverter` setzt
`links: const []`. Muss in Python-Pipeline ergänzt werden (Backlog, nach Quiz-Run).

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

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Quiz-Checkpoint löschen + Run neu starten** (s.o.)
- **Bilder-Patch** nach Quiz-Run: `patch_article_images_v1.py`

### Mittel
- **Links in JSON-Artikeln** — Python-Pipeline: Link-Positionen in `WfSentence` ergänzen,
  dann `WfArticleConverter` + Provider befüllen. Vor App-Umbau Schritt B angehen.
- **App-Umbau Schritt B: Renderer** — Quiz-Widget, Callout-Boxen
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
