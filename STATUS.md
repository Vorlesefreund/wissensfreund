# Wissensfreund — STATUS
<!-- updated: 2026-06-01T13:55:38Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 abends)

### Bilder + Kapitel-Pfeile Modus C — Bug behoben

**Root-Cause:** Test-Button hat dynamisch `'elefant_l$level'` gebaut (Altersstufe 1 oder 3).
Nur `elefant_l2.json` existiert. Stufe 1 oder 3 → 404 → `loadAndSpeakJsonArticle` bricht ab →
`_articleImages = []`, `_sectionChunkStarts = []` → keine Bilder, keine Pfeile.

**Fixes:**
- `home_screen.dart`: Test-Button jetzt hardcoded `'elefant_l2'` (Label: "JSON Test (Elefant L2)")
- `json_article_service.dart`: Bundled-Asset-Fallback eingebaut — wenn R2 fehlschlägt → `rootBundle.loadString('assets/test/$id.json')`
- `pubspec.yaml`: `assets/test/` Eintrag ergänzt
- `assets/test/elefant_l2.json`: 5-Abschnitt-Elefant-Artikel als Bundled-Asset eingefügt
- `flutter build apk --debug` + `adb install -r` ✅

**Weiterhin bekannt:** JSON-Bilder brauchen WiFi — `mobileAllowed=false` default → auf Mobilfunk geblockt.
ZIM-Bilder kommen aus lokaler ZIM-Datei, brauchen kein Netzwerk.

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 nachmittags)

### Scroll-Sync-Bugs Mode A + B — alle drei behoben

- **Bug 1 — Mode B scroll DOWN**: `_sentenceTopCache` veraltet (fontSize-Wechsel aktiv/inaktiv) →
  falsches `topIdx` → kein Seek. **Fix**: live `findRenderObject()` statt Cache.
- **Bug 2 — Mode B scroll UP**: `_userScrolling = false` zu früh → Auto-Scroll überschreibt Seek.
  **Fix**: `_seekResumeTimer` (3000 ms) hält `_userScrolling = true` bis Seek greift.
- **Bug 3 — Mode A liest zu lang**: Debounce 1500 ms → 800 ms reduziert.

---

## 🔴 Gerade in Arbeit / Unterbrochen

### Quiz-Generierung — Checkpoint-Problem

- Run `26741537309` lief 2h7m, manuell abgebrochen
- **609 von 3.544 Quizzen** generiert; Artikel-Artefakt NICHT hochgeladen → Quizze verloren
- Checkpoint auf R2 gespeichert → 609 als "erledigt" markiert → werden übersprungen
- **→ Checkpoint MUSS gelöscht werden**, sonst 609 Artikel dauerhaft ohne echte Quizze

### Sofortmaßnahme:
```
aws s3 rm s3://wissensfreund-articles/staging/checkpoints/quiz_checkpoint.json \
  --endpoint-url "https://<CF_ACCOUNT_ID>.r2.cloudflarestorage.com"
```
Dann `quiz_and_upload.yml` manuell triggern. Laufzeit ~8.9h → 2 Runs nötig.

---

## 🟡 Offen — nächste Schritte

### Hoch
- **Quiz-Checkpoint löschen + Run neu starten** (s.o.)
- **Bilder-Patch** nach Quiz-Run: `patch_article_images_v1.py` laufen lassen
- **App-Umbau Schritt B: Renderer** — Quiz-Widget (A/B/C per STT), Callout-Boxen

### Mittel
- **Gemini-Integration** — `_detectQueryType()` vorhanden, `_handleGeminiPlaceholder()` Einstiegspunkt
- **Topic-Tree Kachel-Navigation** in der App (Ebene 1→2→3)

### Niedrig
- Upgrade-Dialog für Free-User bei Rückfrage (wartet auf Gemini)
- Download-Größe dynamisch aus Manifest statt statisch "~2 GB"
- Plus & Premium Dialog: Design-Vorgaben noch ausstehend
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
