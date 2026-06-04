# Wissensfreund — STATUS
<!-- updated: 2026-06-04T15:38:04Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Vollbild-Viewer — komplett, auf main gemergt (e0906eb → merge)**

- PhotoViewGallery (photo_view_plus 1.1.1) ersetzt InteractiveViewer — Pinch-Arena gelöst
- 3-Stufen-Doppeltipp: Basis → Stufe1 (minScale×2.5) → Max (covered×4) → Basis, deterministisch
- Caption: an Bildunterkante verankert (Letterbox vs. Overlay, je nach freiem Raum)
- Pinch-Fix: Doppeltipp in Future.microtask — 2-Finger-Geste kann nicht mehr als Tap fehlgedeutet werden
- Wischen/Panning, Rotation, Blur-Hintergrund, Lautsprecher ohne Flackern — alles auf S23 getestet ✅
- Branch spike/photo-view-plus gelöscht

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Bilder-Patch** (`patch_article_images_v1.py` in wissensfreund_repo): Artikel von R2
  laden (`rclone sync r2:wissensfreund-articles/articles/ articles_production/`),
  Patch laufen lassen, zurück nach R2. (ANTHROPIC_API_KEY in GitHub Secrets)
- **Selbst produzierte Artikel** — neue JSON-Artikel mit echten Inhalten, Quiz-Checkpoint
  löschen + Run neu starten

### Mittel
- **Epoch-Guard TTS-Callbacks**: `_ttsStopPending` hat Zeitfenster auf langsamen Geräten.
  Lösung: Generations-Zähler (Closure capturt Epoch-ID) bei jedem `speak()`. ~5 Stellen.
- **Mode B Lupe**: Bold entfernen + `_ttsCursor` erst im progressHandler updaten
- **Sound-Thumbnails**: Audio-Infrastruktur fertig; wartet auf Audio-Pipeline-Run-Ergebnis

### Niedrig (große Architekturaufgaben)
- **ZIM→JSON Decode-Auflösungs-Cap**: Bilder beim Decode auf sinnvolle Max-Größe begrenzen
- **Kiosk → Screen Pinning**: DevicePolicyManager durch Android Screen Pinning ersetzen
- **STT-Routing**: Mikrofon-Eingabe robuster (AudioFocus, verschiedene Geräte)
- **Fire-OS-Entscheidung**: App auf Fire-Tablets testen / Entscheidung ob Support
- **Bild-Tier-Werte vereinheitlichen**: thumb/standard/pro-Pixel-Werte in einer Konstanten-Datei

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
- Links/Gemini/Topic-Tree, Upgrade-Dialog, Plus/Premium-Design
