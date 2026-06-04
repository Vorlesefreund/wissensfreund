# Wissensfreund — STATUS
<!-- updated: 2026-06-04T09:55:09Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 2. Teil)

**Vollbild-Viewer fertiggestellt** — `image_fullscreen_overlay.dart` + Provider, Branch `spike/photo-view-plus`

### P1 — contained (kein Crop)
- `initialScale` + `minScale`: `contained * 1.18` → `PhotoViewComputedScale.contained`
- `_initialScaleFor()`: `sc * 1.18` → `sc` (konsistent mit PV-Scale)
- Basis-Scale: Bild ganz sichtbar, kein Überstehen → Wischen zuverlässig

### P2 — Weichgezeichneter Hintergrund-Füller
- `const _kBlurredBackdrop = true;` — abschaltbar mit einer Zeile
- `ImageFiltered(blur: 24)` + `Image.memory(cacheWidth: 96)` als 96px-Thumbnail
- Schwarzer Scrim `0x44000000` (27%) für Caption-Lesbarkeit
- Gallery `backgroundDecoration: Colors.transparent` damit Blur durchscheint
- Liegt im Stack unter der Gallery, keine Gesten

### P3 — Doppeltipp-Fix
- Root Cause: `_blindScaleStateListener` prüft `isZooming = zoomedIn|zoomedOut` →
  überspringt Animation wenn Zielstate `zoomedOut`. Zoom-out animierte nie.
- Fix: `_scaleStateCycle` gibt jetzt `initial` statt `zoomedOut` zurück.
  Gleiche Scale (= initialScale = contained), aber `initial ∉ isZooming` → Animation läuft.
- Cycle korrekt: initial→covering→initial→covering (beliebig oft)

### P4 — Lautsprecher-Button-Regression
- `_speakerUsed`-Flag entfernt (blieb bis Seitenwechsel aktiv)
- `bool get isCaptionPlaying => _isCaptionPlaying;` in WissensfreundProvider ergänzt
- Button `dimmed: provider.isCaptionPlaying` → reaktiv auf TTS-Ende

### Commit auf S23 installiert: 2026-06-04

---

## 🔴 Gerätetest erforderlich (S23 — alle 4 Muss-Punkte + Extras!)

```
[ ] 1. Pinch greift beim ERSTEN Touch
[ ] 2. Doppeltipp: zoom-in (covering) → nochmals: zoom-out (contained)
       Mehrfach hintereinander testen — jeder Doppeltipp muss reagieren
[ ] 3. Bei Basis-Scale: Wischen wechselt Bild direkt
[ ] 4. Gezoomt: frei panbar, alle Bildteile erreichbar
[ ] Hintergrund-Blur sieht gut aus (weichgezeichnet, kein harter Rand)
[ ] _kBlurredBackdrop = false → schwarzer Hintergrund ohne Blur
[ ] Lautsprecher: dimmt nur WÄHREND Vorlesen; danach wieder aktiv
[ ] Overlays korrekt (Zurück, Speaker, ⓘ, Caption, Zähler)
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
