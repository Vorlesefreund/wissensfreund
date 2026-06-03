# Wissensfreund — STATUS
<!-- updated: 2026-06-03T14:43:29Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — Phase 2: photo_view_plus Migration)

### Migration image_fullscreen_overlay.dart → photo_view_plus 1.1.1

**Branch:** `spike/photo-view-plus` — APK installiert auf S23, wartet auf Geräte-Test.

**Was geändert wurde:**
- `InteractiveViewer` + `TransformationController` + `Matrix4`-Logik vollständig entfernt
- `photo_view_plus: 1.1.1` (exakt gepinnt, kein `^`) in pubspec.yaml
- `_LimitedCoverScale extends PhotoViewScale` — `resolve()` = `min(sk, sc * 1.18)`
- `PhotoViewGestureDetectorScope(axis: Axis.horizontal)` wraps `PageView.builder`
  → Pinch gewinnt Gesture-Arena immer; PageView bekommt nur Edge-Swipes
- `PhotoView` pro Seite: `initialScale/minScale = _limitedCoverScale`, `strictScale: true`
- `maxScale: PhotoViewComputedScale.covered * 4.0`
- Kein eigenes `_clampedMatrix` mehr — `metrics.clampPosition()` out-of-box
- Double-tap: `disableDoubleTap: true` + `onTapUp` Debounce (300ms/40px) + AnimController
  - Zoom-in: `targetScale = initScale * 2.5`, Fokuspunkt-Formel: `(tapPos - center)*(1-r) + pos0*r`
  - Zoom-out: `targetScale = initScale`, `position = Offset.zero`
- `scaleStateChangedCallback` für Pinch-Zoom-State (mit `index == _currentIndex` Guard)
- `onScaleStart`: laufende Double-tap-Animation stoppen (verhindert Konflikt)
- `_imageSizes` Map für Double-tap initScale-Berechnung (aus `ui.decodeImageFromList`)
- `_outerSizes` Map aus `LayoutBuilder` — outerCenter für Fokuspunkt-Formel
- Rand-Swipe via `Listener` entfernt — `PhotoViewGestureDetectorScope` übernimmt das
- `NeverScrollableScrollPhysics` entfernt — Scope regelt es
- Kein `_tcInitialized`, kein `_imageRatios`-Block-Guard mehr nötig
- `_imageRatios` nur noch für Dreh-Hinweis

**Was NICHT geändert wurde (Regressions-Check vorbereitet):**
- Byte-Loading via `_futureFor` + FutureBuilder — identisch
- Spinner während Ladevorgang — identisch
- Caption-Gradient, Caption-Text, Zähler "1/3" — identisch
- Zurück-Button, Speaker-Button — identisch
- Dreh-Hinweis — identisch
- ⓘ Lizenz-Button (nur ungezoomt) — identisch
- Orientierung Portrait + Landscape in initState/dispose — identisch

---

## 🔴 Muss am S23 verifiziert werden (Checkliste)

```
[ ] PageView Mehrbild-Wisch (links/rechts blättern)
[ ] Pinch sofort nach Öffnen — KERN-BUG, explizit testen!
[ ] Bild lässt sich im Zoom NICHT aus Viewport schieben
[ ] Doppeltipp 1x↔2.5x zentriert auf Tippposition
[ ] Zurück- / Speaker- / ⓘ-Lizenz-Button funktionsgleich
[ ] Bildunterschrift + "1 / 3"-Zähler korrekt (onPageChanged)
[ ] Limited cover max ~15% Crop, kein unerwarteter Letterbox
[ ] Bildquelle (on-demand Commons / R2 / Fallback) als imageProvider korrekt
[ ] Schwarzer Hintergrund
```

---

## 🟡 Zum Testen (ausstehend)
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
