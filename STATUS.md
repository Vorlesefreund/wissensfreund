# Wissensfreund — STATUS
<!-- updated: 2026-06-01T14:24:57Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 nacht)

### 3 neue Bugs nach APK-Install behoben

**Bug 1 — Mode A Auto-Scroll dauerhaft gebrochen:**
`_ModeAContentState._jumpToTopSentence()` hat `_userScrolling` an keinem Return-Pfad zurückgesetzt.
Nach erstem manuellen Scroll → `_userScrolling = true` für immer → `_smartScrollTo` always blocked.
Fix: `_userScrolling = false` an allen 5 Early-Returns + nach `seekAfterCurrentChunk`.
Mode A sicher: `_sentenceTopCache` stabil (keine Font-Size-Änderungen wie in Mode B).

**Bug 2 — Mode B Text unter Professor-Widget:**
- Scroll-Schwelle `viewportH * 0.5` zu hoch → aktiver Satz noch im Professor-Bereich (218 dp).
  Fix: Schwelle auf `viewportH * 0.35` gesenkt.
- Bottom-Padding `_kMicClear` (80 dp) << Professor-Höhe (218 dp).
  Fix: Padding auf `_kProfZone` (220 dp) erhöht.

**Bug 3 — Bilder zeigen keinen Lade-Zustand:**
`FutureBuilder` zeigte während `ConnectionState.waiting` denselben Fallback wie bei Fehler.
Fix: `CircularProgressIndicator` (grün, strokeWidth 2.5) während Waiting-State.

Commit `wissensfreund_app`: `d487458` ✅

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 abends)

### Bilder + Kapitel-Pfeile Modus C — Bug behoben

- Test-Button hardcoded auf `'elefant_l2'` (war dynamisch → Level 1/3 → 404 → keine Bilder)
- `json_article_service.dart`: Bundled-Asset-Fallback (`assets/test/$id.json`)
- `pubspec.yaml`: `assets/test/` ergänzt; `elefant_l2.json` als Asset eingebettet
- Commit `wissensfreund_app`: `4baa030` ✅

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
