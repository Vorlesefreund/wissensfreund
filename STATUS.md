# Wissensfreund — STATUS
<!-- updated: 2026-06-04T16:58:42Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Vollbild-Viewer — komplett, auf main gemergt (e0906eb → merge)**
- PhotoViewGallery (photo_view_plus 1.1.1) ersetzt InteractiveViewer — Pinch-Arena gelöst
- 3-Stufen-Doppeltipp: Basis → Stufe1 (minScale×2.5) → Max (covered×4) → Basis, deterministisch
- Caption an Bildunterkante verankert; Pinch-Fix via Future.microtask
- Getestet auf S23 ✅; Branch spike/photo-view-plus gelöscht

**Repo-Hygiene — beide Klone auf main vereint (2026-06-04)**
- Uncommitted work aus wissensfreund_app gesichert + nach main gemergt (profile_creation_screen,
  quiz_widget, profile_management_screen, network_service, license_cache_db,
  MainActivity, ZimReader, professor_phrases.dart, device_admin.xml, image_index.json,
  test-images, Pipeline-Skripte, System-Prompt v3.4, Referenz-Testartikel)
- Arbeitsverzeichnis/Keeper: **C:\Users\Andreas\wissensfreund_repo**
- CLAUDE.md: absoluter STATUS.md-Pfad → ./STATUS.md; Arbeitsverzeichnis-Regel ergänzt

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. 30-Sek-Check: `git status` + `git status --ignored` in wissensfreund_app
3. Dann Ordner löschen

**C:\Users\Andreas\Wissensfreund\CLAUDE.md + STATUS.md** — verwaiste Nicht-Git-Kopien,
können nach Entfernung von wissensfreund_app ebenfalls gelöscht werden.

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Bilder-Patch** (`patch_article_images_v1.py`): Artikel von R2 laden, Patch laufen lassen,
  zurück nach R2. (ANTHROPIC_API_KEY in GitHub Secrets)
- **Selbst produzierte Artikel** — Quiz-Checkpoint löschen + Run neu starten

### Mittel
- **Epoch-Guard TTS-Callbacks**: Generations-Zähler statt `_ttsStopPending` (~5 Stellen)
- **Mode B Lupe**: Bold entfernen + `_ttsCursor` erst im progressHandler updaten
- **Sound-Thumbnails**: wartet auf Audio-Pipeline-Run-Ergebnis

### Niedrig (große Architekturaufgaben)
- **ZIM→JSON Decode-Auflösungs-Cap**: Bilder beim Decode auf sinnvolle Max-Größe begrenzen
- **Kiosk → Screen Pinning**: DevicePolicyManager durch Android Screen Pinning ersetzen
- **STT-Routing**: Mikrofon-Eingabe robuster (AudioFocus, verschiedene Geräte)
- **Fire-OS-Entscheidung**: App auf Fire-Tablets testen / Entscheidung ob Support
- **Bild-Tier-Werte vereinheitlichen**: thumb/standard/pro-Pixel-Werte in Konstanten-Datei

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
- Links/Gemini/Topic-Tree, Upgrade-Dialog, Plus/Premium-Design
