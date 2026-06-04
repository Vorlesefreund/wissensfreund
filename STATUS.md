# Wissensfreund — STATUS
<!-- updated: 2026-06-04T09:11:07Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04)

**PhotoViewGallery-Refactor** — `image_fullscreen_overlay.dart`, Branch `spike/photo-view-plus`:

- `PhotoViewGallery` (non-builder) ersetzt manuelles `PageViewGestureDetectorScope + PageView.builder + PhotoView`
- Gallery verwaltet `PageViewGestureDetectorScope` intern → Swipe-vs-Pinch-Arena korrekt gelöst
- `disableDoubleTap` entfernt → `scaleStateCycle` (initial/zoomedOut → covering → zoomedOut)
- Kein eigener Tap-Detektor mehr in der Arena — PV-nativer Doppeltipp
- `_startLoading` + `_loadedBytes` Cache — keine Byte-Duplizierung, kein Flackern
- Spinner via `PhotoViewGalleryPageOptions.customChild`, Bild via `PhotoViewGalleryPageOptions`
- Alle Overlays im äußeren Stack (Zurück, Speaker, ⓘ, Caption, Zähler, Dreh-Hinweis)
- `_resetController` nutzt `MediaQuery.sizeOf(context)` + `contained * 1.18`
- Import `photo_view_plus_gallery.dart` separat (nicht in `photo_view_plus.dart` exportiert)
- Entfernt: `_pvAnimControllers`, `_outerSizes`, `_futures`, `_lastTap*`, `_handleDoubleTap`, `_clampPosition`, `_trackPointerDown`
- APK gebaut + auf S23 installiert (2026-06-04)

---

## 🔴 Gerätetest erforderlich (S23 — alle 4 Muss-Punkte!)

```
[ ] 1. Pinch greift beim ERSTEN Touch (kein Warten auf 2. Finger-Aufsetzen)
[ ] 2. Doppeltipp zoomt rein → deckt Bildschirm (covering), nochmals → zurück zu Basis
[ ] 3. Bei Basis-Scale: horizontales Wischen wechselt Bild direkt (kein Hängen)
[ ] 4. Gezoomt: frei panbar, alle Bildteile erreichbar
[ ] Zusatz: Crop-Test — ~15% Letterbox bei Basis-Scale sichtbar? (contained*1.18)
[ ] Overlays (Zurück, Speaker, ⓘ, Caption, Zähler) korrekt
[ ] Hintergrund schwarz | Spinner beim Laden
```

**Fallback falls Muss-3 bricht (Wischen blockiert trotz Gallery-Arena):**
`contained * 1.18` → `contained` in `PhotoViewGalleryPageOptions` (beide Scale-Werte, Z. 198-199)

**Nach bestandenem Test:** `spike/photo-view-plus` → `main` mergen, Branch löschen.

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
