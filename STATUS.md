# Wissensfreund — STATUS
<!-- updated: 2026-06-04T11:54:01Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 3. Teil)

**Vollbild-Viewer — Doppeltipp + Wischen-nach-Zoom gefixt**
Branch `spike/photo-view-plus`, auf S23 installiert.

### Root Cause (bestätigt durch PV-Source-Analyse)
Nach Zoom-out: `_blindScaleListener` setzt `scaleState = zoomedOut` (invisibly), weil
`controller.scale == initialScale` → `scale > initialScale` false → `zoomedOut`.
- `scaleState = zoomedOut` → `isZooming = true` → `_blindScaleStateListener` blockiert
  Animation beim nächsten Doppeltipp (DTGR → `nextScaleState` → re-arm schlägt fehl)
- Swipe klemmt: `shouldMove` ergibt `true` wenn `position` nicht exakt Offset.zero
  (Floating-Point in `childWidth > outerWidth`)

### Fixes implementiert

**1. Exakter Reset (`_resetController`)**
- `ctrl.updateMultiple(scale: initScale, position: Offset.zero)` — unverändert
- **NEU**: `_pvScaleStateControllers[index]?.reset()` → setzt `scaleState = initial`
  PV erkennt Ruhezustand: shouldMove=false, Doppeltipp-Zyklus re-armt

**2. Manueller Doppeltipp via `onTapDown`-Timing**
- `disableDoubleTap: true` in PageOptions → DTGR gewinnt Arena, ruft aber `nextScaleState`
  NICHT auf (kein Callback) → kein Konflikt mit unserem Handler
- `_onImageTapDown(index, details)`: Zeitfenster 80–300ms zwischen zwei Downs
  Min 80ms filtert Pinch (2 Finger < 40ms auseinander)
- `_handleDoubleTap(index)`: liest `ssCtrl.scaleState` statt `_isPageZoomedIn`:
  - `initial || zoomedOut` → Zoom-in: `ssCtrl.scaleState = covering` → PV animiert
  - sonst → Zoom-out: `ssCtrl.scaleState = initial` → PV animiert + Position → Offset.zero

**3. Pinch-out Reset (`onScaleEnd`)**
- `_onScaleEnd`: wenn `scale ≤ minScale * 1.01` → `ssCtrl.reset()` → `scaleState = initial`
- Behebt `scaleState = zoomedOut` nach Pinch-out ohne Animation-Konflikt

**4. `_pvScaleStateControllers` Map**
- Pro Seite ein `PhotoViewScaleStateController` — extern gehalten
- In `PageOptions`: `scaleStateController: _scaleStateCtrlFor(index)` → PV nutzt unseren
- In `dispose()`: alle Controller disposed

---

## 🔴 Gerätetest erforderlich (S23 — mehrfach hintereinander!)

```
[ ] 1. Doppeltipp: zoom-in → zoom-out → zoom-in → ... (beliebig oft, nie hängen)
[ ] 2. Wischen bei Basis-Scale funktioniert direkt nach Doppeltipp-Zoom-out
[ ] 3. Wischen bei Basis-Scale funktioniert nach Pinch-zoom-in + Pinch-zoom-out
[ ] 4. Pinch greift beim ERSTEN Touch
[ ] 5. Panning im gezoomten Zustand: frei, alle Bildteile erreichbar
[ ] 6. Seitennavigation (Wischen) funktioniert zuverlässig auf frisch geladenem Bild
[ ] Hintergrund-Blur, Lautsprecher, Overlays — keine Regressionen
```

---

## 🔴 Nach bestandenem Test
`spike/photo-view-plus` → `main` mergen, Branch löschen.

---

## 🟡 Zum Testen (ausstehend, niedrigere Prio)
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten (zu frühes Highlight)

---

## 🔴 Offene To-Dos (nach Priorität)

### Mittel
- **Selbst produzierte Artikel**, **Quiz-Checkpoint + Run neu**
- **Bilder-Patch** (patch_article_images_v1.py) nach Quiz-Fertigstellung

### Niedrig
- Epoch-Guard TTS-Seek | Mode-B-ZIM-\n-Loch
- Links/Gemini-Integration/Topic-Tree
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
