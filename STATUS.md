# Wissensfreund — STATUS
<!-- updated: 2026-06-01T20:58:25Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Nur die letzten 2 Sessions + aktuell Offenes bleibt hier. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 — UI-Feinschliff)

- Mode B: Artikelbild 0.32 (clamp 180–300dp), Satz-Anfang bei 30% vom Viewport-Top
- Mode C: Attribution bei _kMicClear=80dp sichtbar, Thumbnails auf 112dp
- Mikrofon: Toggle-Funktion (zweites Tippen schaltet ab)
- Mode A: Scroll-Trigger 35%, localY<0-Prüfung, alignment 0.18
- Pause+Scroll: _jumpToTopSentence überspringt Seek wenn isPaused (A+B)
- Scroll-Zurücksprung: _userScrolling=true vor ageLevel-Check (A+B)
- ZIM-Seek: _seekToChunkForOffset respektiert startSpeaking-Parameter

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-01 — R2-Bestandsaufnahme)

### Ergebnis der Inventur

- **3.544 Artikel** in `staging/articles_zim/`
- **Bilder:** `license` + `license_author` überall befüllt ✅ — `thumb_url` überall leer ❌
- **img_index:** 100% der Sätze haben Bild-Zuweisung ✅
- **Quiz:** Alle 3.544 Artikel haben formal 3 Fragen — aber alle sind **Platzhalter** (`"Antwort A/B/C"`) ❌
- **Checkpoint:** Existiert mit 609 Einträgen (müsste vor Quiz-Run gelöscht werden)

**Entscheidung:** Quiz-Run und Bilder-Patch werden zurückgestellt.
Nächster Fokus: selbst produzierte Artikel.

---

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Selbst produzierte Artikel** — nächste Session

### Mittel (zurückgestellt)
- **Quiz-Checkpoint löschen + Run neu starten** — erst wenn Quiz-Run wieder priorisiert
- **Bilder-Patch** (`patch_article_images_v1.py`) — nach Quiz-Run
- **Links in JSON-Artikeln** — Python: Link-Positionen in WfSentence, dann Flutter-Seite
- **App-Umbau Schritt B: Renderer** — Quiz-Widget, Callout-Boxen
- **Gemini-Integration**
- **Topic-Tree Kachel-Navigation**

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1

- Gallery-Artikel (111 Artikel, 540 Bilder)
- Audio-Pipeline

---

## Wissensdokumente (bei Bedarf lesen)

| Datei | Inhalt |
|---|---|
| `WISSEN_BILDER.md` | Bild-Pipeline, R2-Struktur, verworfene Ansätze |
| `WISSEN_ARTIKEL_PIPELINE.md` | JSON-Schema, Altersstufen, Pipeline-Skripte, R2-Bestand |
| `WISSEN_APP_ARCHITEKTUR.md` | Services, Freemium, Frage-Typen, Navigation+Sync, Designentscheidungen |
