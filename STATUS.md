# Wissensfreund — STATUS
<!-- updated: 2026-06-01T09:56:50Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-05-31)

- JSON-Artikel zeigen Bilder: `HiResImageService.fetchUrlBytes()` + `_jsonThumbUrlMap`
- Thumbnail-Strip für JSON-Artikel: `_mediaItems` direkt aus `rendered.images` befüllt
- APK gebaut + getestet auf Galaxy S23 ✅
- Bild-Pipeline komplett: alle 3 ZIPs in R2 (thumb 300px, standard 800px, pro 1600px) ✅
- ZIM-Konvertierung (run 26741429128): 3.544 Artikel → R2 Staging ✅

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

## Wichtige Erkenntnisse aus dieser Session

- **Alle ZIM-Artikel sind age_level=2** (Stufe 2, 7–9 Jahre). Klexikon differenziert nicht nach Alter.
  Stufe 1 + 3 kommen nur aus `generate_articles.py` (separater Pipeline).
- **Quiz-Qualität gut**: 3 Fragen, A/B/C Optionen, TTS-tauglich, testen echten Artikeltext ✓
- **Workflow-Schwachstelle**: Quiz-Run schreibt Artikel nur lokal. Bei Abbruch → Quizze verloren.
  Verbesserung: Artikel nach jeder N-Batch direkt zurück nach R2 schreiben.

---

## 🟡 Offen — nächste Schritte

### Hoch
- **Quiz-Checkpoint löschen + Run neu starten** (s.o.)
- **App-Umbau Schritt B: Renderer** — gemeinsamer JSON-Renderer für ZIM + eigene Artikel
  - `RenderedArticle` internes Format
  - `ZimArticleConverter` + `JsonArticleConverter`
  - Quiz-Widget (A/B/C per STT)
  - Callout-Boxen (wow/fakt/myth/warn)
  - Bild-Wechsel per `imgIndex` pro Satz

### Mittel
- **Gemini-Integration** — `_detectQueryType()` vorhanden aber inaktiv
  - Typ 3 (Vergleichsfrage) + Typ 5 (Fallback) fehlen noch
  - `_handleGeminiPlaceholder()` ist der Einstiegspunkt
- **Topic-Tree Kachel-Navigation** in der App (Ebene 1→2→3)
- **Quiz-Workflow verbessern**: Artikel nach jeder Batch nach R2 zurückschreiben

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
| `WISSEN_APP_ARCHITEKTUR.md` | Services, Freemium, Frage-Typen, Designentscheidungen |
