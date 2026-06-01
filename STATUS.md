# Wissensfreund — STATUS
<!-- updated: 2026-06-01T10:00:00Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-05-31)

- JSON-Artikel zeigen Bilder: `HiResImageService.fetchUrlBytes()` + `_jsonThumbUrlMap`
- Thumbnail-Strip für JSON-Artikel: `_mediaItems` direkt aus `rendered.images` befüllt
- APK gebaut + getestet auf Galaxy S23 ✅
- Bild-Pipeline komplett: alle 3 ZIPs in R2 (thumb 300px, standard 800px, pro 1600px) ✅

---

## 🔴 Gerade in Arbeit

- **Artikel-Generator läuft** (`generate_articles.py` via GitHub Actions)
  - Alte Artikel in R2-Cache haben `"images": []` → müssen neu generiert werden
  - `_filename_from_title()` gibt lowercase aus — Wikimedia-Filenames sind case-sensitiv
    (macht für Map-Key nichts, aber für Display beachten)

---

## 🟡 Offen — nächste Schritte

### Hoch
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
- **Pageviews-Abfrage** in `prepare_articles.py` (Wikimedia REST API)

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
