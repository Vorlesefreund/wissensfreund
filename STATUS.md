# Wissensfreund — STATUS
<!-- updated: 2026-06-03T14:08:40Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — Spike: photo_view_plus Evaluation)

### Phase 1 Spike — ERGEBNIS: ✅ JA — Bitte Phase 2 Migration genehmigen

Branch: `spike/photo-view-plus` (pubspec.yaml + STATUS.md geändert; main bleibt launchbar)

| Kriterium | Ergebnis | Begründung |
|---|---|---|
| 1. Gesture Arena (PageView vs. Pinch) | ✅ JA | `PhotoViewGestureRecognizer._decideIfWeAcceptEvent`: 2-Pointer (Pinch) gewinnt immer; 1-Pointer (Pan) nur wenn nicht am Rand → PageView bekommt nur Edge-Swipes |
| 2. PhotoViewInteractionPolicy Clamp-Hook | ✅ JA | 3 injectable Callbacks: `clampPosition(metrics, nextPos)` + `onGestureEnd(context)` + filterQuality; Standard-Impl nutzt `metrics.clampPosition()` — korrekt out-of-box |
| 3. Limited Cover max 15% Crop | ✅ JA | `PhotoViewScale` ist abstract → `LimitedCoverScale`-Subklasse: `resolve()` = `min(sk, sc * 1.18)`; PV berechnet childSize intern aus MemoryImage |
| 4. Doppeltipp 1x-2.5x an Tippposition | JA (30 Zeilen) | `disableDoubleTap:true` + `onTapUp` Debounce + eigener AnimController; `newPos = (tap-center)*(1-r) + pos0*r` wobei `r = scale1/scale0` |

**Kriterium 4 ist kein Blocker:** Implementierung einfacher als Matrix4 (scale+position getrennt).

**Zusätzliche Erkenntnisse:**
- `MemoryImage(bytes)` direkt als imageProvider nutzbar — kein manuelles imgRatio-Decode mehr nötig
- PhotoViewGallery wraps intern PageView.builder mit PhotoViewGestureDetectorScope — keine eigene PageView nötig
- `wantKeepAlive: true` verhindert State-Reset beim Blättern
- `strictScale: true` verhindert Zoom unter minScale (= LimitedCoverScale)

---

## 🔴 Warte auf Entscheidung (STOPP bis Claude Chat / Andreas grünes Licht gibt)

- **Phase 2: Migration von InteractiveViewer → photo_view_plus**
  Branch `spike/photo-view-plus` ist vorbereitet. main bleibt launchbar.
  Nach Genehmigung: Migration auf main, spike-Branch löschen.

---

## 🟡 Zum Testen (ausstehend)
- ImageFullscreenOverlay Pinch + Doppeltipp (nach Phase 2)
- Mode B Lupe: Bold entfernen
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten

---

## 🔴 Offene To-Dos (nach Priorität)

### Mittel
- **Selbst produzierte Artikel**, **Quiz-Checkpoint + Run neu**
- **Bilder-Patch** (`patch_article_images_v1.py`) nach Quiz-Fertigstellung

### Niedrig
- Epoch-Guard TTS-Seek (eigener Refactor)
- Mode-B-ZIM-`\n`-Loch
- Links in JSON-Artikeln, Gemini-Integration, Topic-Tree
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
