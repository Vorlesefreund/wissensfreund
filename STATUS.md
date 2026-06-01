# Wissensfreund — STATUS
<!-- updated: 2026-06-01T13:21:49Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 nachmittags)

### Scroll-Sync-Bugs Mode A + B — alle drei behoben

- **Bug 1 — Mode B scroll DOWN (Professor springt nicht)**: Root-Cause: `_sentenceTopCache` veraltet,
  weil aktiver Satz (fontSize 19) vs. inaktiv (fontSize 15) Satzpositionen verschiebt →
  falsches `topIdx` → `topIdx == activeIdx` → kein Seek.
  **Fix**: `_jumpToTopSentence` nutzt jetzt live `findRenderObject()` statt staler Cache.

- **Bug 2 — Mode B scroll UP (Professor springt zurück)**: Root-Cause: `_userScrolling = false` am
  Anfang von `_jumpToTopSentence` → `_smartScrollTo` läuft sofort los für alte TTS-Position.
  **Fix**: `_userScrolling` bleibt `true` nach dem Seek-Aufruf; neuer `_seekResumeTimer` (3000 ms)
  setzt ihn zurück, wenn der Seek gegriffen hat.

- **Bug 3 — Mode A liest zu lang (ein Satz extra)**: Debounce 1500 ms → TTS konnte ganzen Satz
  noch vollständig vortragen + nächsten starten.
  **Fix**: Debounce in Mode A + B auf 800 ms reduziert.

- Elefant L2 Testartikel (5 Bilder, 5 Abschnitte, ~23 Sätze) per `adb push` bereits auf Gerät.
- `flutter build apk --debug` + `adb install -r` ✅

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 morgens)

### Artikel-Screen: Navigation & Bild-Sync nach Altersstufe
- **Mode-Toggle** nach Altersstufe: Stufe 1 → 2 Icons (B/C); Stufe 2/3 → 3 Icons (A/B/C)
  - Auto-Switch: Profil Stufe 1 + Modus A aktiv → sofort auf B wechseln
- **Bild-Sync** (Stufe 2/3 JSON-Artikel): Auto-Bildwechsel per `img_index` im Chunk-Advance-Handler
  - Vorwärts-Wischen → Sync pausiert bis TTS aufholt
  - Rückwärts-Wischen → 10 s Timer, dann Bild auf TTS-Position zurück
- **Scroll-Navigation Modus A** (Stufe 2/3): Debounce → Professor springt zum obersten sichtbaren Satz
- **Kapitel-Pfeile Modus C** (Stufe 2/3): `‹`/`›` neben Thumbnails, springt zu nächstem/vorherigem Abschnitt
- Provider: `seekAfterCurrentChunk`, `pauseImageSync`, `setViewMode`, `sectionChunkStarts`, `chunkCharOffset`

---

## 🔴 Gerade in Arbeit / Unterbrochen

### Quiz-Generierung — teilweise erledigt, Checkpoint-Problem

- Run `26741537309` lief 2h7m, dann manuell abgebrochen
- **609 von 3.544 Quizzen** generiert (A–D alphabetisch: "1. FC Union Berlin" → "Deutsche Kolonien")
- **Checkpoint auf R2 gespeichert** (`staging/checkpoints/quiz_checkpoint.json`, 609 Einträge)
- **ABER: Quizze sind verloren** — Artikel-Artefakt wurde nicht hochgeladen (Job abgebrochen)
- R2 Staging hat für ALLE 3.544 Artikel noch Placeholder-Quizze (`review_flag=true`)
- Checkpoint markiert 609 als "erledigt" → werden beim nächsten Run übersprungen
- **→ Checkpoint MUSS gelöscht werden**, sonst bleiben 609 Artikel permanent ohne echte Quizze

### Sofortmaßnahme:
```
aws s3 rm s3://wissensfreund-articles/staging/checkpoints/quiz_checkpoint.json \
  --endpoint-url "https://<CF_ACCOUNT_ID>.r2.cloudflarestorage.com"
```
Dann `quiz_and_upload.yml` manuell triggern. Laufzeit ~8.9h → braucht 2 Runs (Checkpoint-Mechanismus hält Fortschritt).

---

## 🟡 Offen — nächste Schritte

### Hoch
- **Quiz-Checkpoint löschen + Run neu starten** (s.o.)
- **Bilder-Patch** nach Quiz-Run: `patch_article_images_v1.py` laufen lassen (s. CLAUDE_CHAT_NOTIZEN.md)
- **App-Umbau Schritt B: Renderer** — gemeinsamer JSON-Renderer für ZIM + eigene Artikel
  - Quiz-Widget (A/B/C per STT)
  - Callout-Boxen (wow/fakt/myth/warn)

### Mittel
- **Gemini-Integration** — `_detectQueryType()` vorhanden aber inaktiv
  - Typ 3 (Vergleichsfrage) + Typ 5 (Fallback) fehlen noch
  - `_handleGeminiPlaceholder()` ist der Einstiegspunkt
- **Topic-Tree Kachel-Navigation** in der App (Ebene 1→2→3)

### Niedrig
- Upgrade-Dialog für Free-User bei Rückfrage (wartet auf Gemini)
- Download-Größe dynamisch aus Manifest statt statisch "~2 GB"
- Plus & Premium Dialog: Design-Vorgaben noch ausstehend
- Sound-Thumbnails: Audio-Infrastruktur fertig, wartet auf Audio-Pipeline-Run

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
