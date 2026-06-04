# Wissensfreund — STATUS
<!-- updated: 2026-06-04T14:37:26Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Vollbild-Viewer — photo_view_plus Migration + 3-Stufen-Doppeltipp**
Branch `spike/photo-view-plus`, letzter Commit `3ce0359`. Auf S23 getestet: ✅

Was funktioniert:
- Pinch beim 1. Touch (Gesture-Arena-Lösung out-of-box mit PhotoViewGallery)
- 3-Stufen-Doppeltipp: Basis → Stufe1 (minScale×2.5) → Max (covered×4) → Basis — deterministisch
- Wischen/Panning, Seiten-Navigation
- Rotation (Reset auf Basis + Position-Zero)
- Weichgezeichneter Hintergrund-Füller, Lautsprecher-Icon kein Flackern

Root-Cause-Fix (erratischer Doppeltipp): `_onScaleEnd` stoppte Animation bei jedem Finger-Heben
→ `_zoomAnimCtrl.stop()` entfernt; Pinch-Stop in `_onPointerDown` multi-touch branch.

---

## 🔴 Nächste Session — Vollbild-Viewer (in Reihenfolge)

**(a) Caption-Platzierung**
Unter dem Bild wenn Letterbox-Raum darunter (Querformat-Bild im Hochformat-Screen).
Overlay wenn Bild die volle Höhe füllt.

**(b) Pinch-Zoom greift gelegentlich nicht**
Verdacht: 2-Finger-Touch als Doppeltipp missdeutet.
Prüfen: bei `_activePointers >= 2` Tap-State sofort löschen (Timing-Problem?).

**(c) Regressionslauf S23 → merge spike/photo-view-plus → main**
Erst wenn (a) + (b) erledigt.

---

## 🟡 Ausstehend (niedrigere Prio)

- Mode B Lupe: Bold entfernen + `_ttsCursor` erst im progressHandler updaten
- Epoch-Guard TTS-Callbacks (wissensfreund_repo-Branch, separater Refactor)

---

## 🔴 Offene To-Dos

### Mittel
- Selbst produzierte Artikel, Quiz-Checkpoint + Run neu
- Bilder-Patch (patch_article_images_v1.py) nach Quiz-Fertigstellung

### Niedrig
- ZIM→JSON Decode-Cap, Kiosk→Screen Pinning, STT-Routing, Fire-OS-Entscheidung
- Links/Gemini/Topic-Tree, Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
