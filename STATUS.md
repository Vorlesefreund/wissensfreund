# Wissensfreund — STATUS
<!-- updated: 2026-06-03T17:04:29Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — photo_view_plus Migration)

### Vollbild-Zoom: InteractiveViewer → photo_view_plus 1.1.1

**Branch:** `spike/photo-view-plus` — APK auf S23 installiert.

**Was umgesetzt wurde:**
- `InteractiveViewer` + `Matrix4`/`TransformationController` vollständig entfernt
- `PhotoViewGestureDetectorScope(axis: Axis.horizontal)` + `PageView.builder`
  → Pinch gewinnt Gesture-Arena immer; 1-Finger-Pan am Rand → PageView (Seitenwechsel)
- `_LimitedCoverScale extends PhotoViewScale`: `resolve() = min(sk, sc * 1.18)`
- `initialScale/minScale = _limitedCoverScale`, `strictScale: true`, `maxScale = covered * 4`
- Kein eigenes `_clampedMatrix` — `metrics.clampPosition()` out-of-box
- Double-tap: `disableDoubleTap: true` + `onTapUp`-Debounce (300ms/40px) + AnimController
  - Zoom-in: `targetScale = initScale * 2.5`, Fokuspunkt-Formel + `_clampPosition()`
  - Zoom-out: `targetScale = initScale`, `position = Offset.zero`
- `onScaleStart`: laufende Animation stoppen (verhindert Pinch-Konflikt)
- `scaleStateChangedCallback` für `_isZoomed` bei Pinch (mit `index==_currentIndex`-Guard)
- `filterQuality: FilterQuality.high` (PV droppt auto auf `medium` während Gesture)
- `bottomInset = MediaQuery.of(ctx).padding.bottom` für alle Bottom-Elemente
  (Caption, Zähler, ⓘ, Dreh-Hinweis — korrekt für iOS Home Indicator + non-immersive Modus)
- Rand-Swipe-`Listener` + `NeverScrollableScrollPhysics` entfernt — Scope übernimmt das
- Flutter 3.44.0 / Dart 3.12.0 — weit über Mindestanforderung. minSdk = 29 unverändert.

---

## 🔴 Muss am S23 verifiziert werden (Regressions-Checkliste)

```
[ ] PageView Mehrbild-Wisch (links/rechts blättern)
[ ] Pinch sofort nach Öffnen — KERN-BUG, explizit testen!
[ ] Bild lässt sich im Zoom NICHT aus Viewport schieben
[ ] Doppeltipp 1x↔2.5x zentriert auf Tippposition
[ ] Zurück- / Speaker- / ⓘ-Lizenz-Button funktionsgleich
[ ] Bildunterschrift + "1 / 3"-Zähler korrekt (onPageChanged)
[ ] Limited cover max ~15% Crop, kein unerwarteter Letterbox
[ ] Schwarzer Hintergrund
[ ] Seitenverhältnis-Randfälle: breites Bild, hohes Bild, quadratisch
```

**Nach Geräte-Parität:** `spike/photo-view-plus` → `main` mergen, Branch löschen.

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
