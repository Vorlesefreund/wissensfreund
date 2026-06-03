# Wissensfreund — STATUS
<!-- updated: 2026-06-03T15:01:50Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — Phase 2 + Geräte-Kompatibilität)

### photo_view_plus Migration + Kompatibilitäts-Hardening

**Branch:** `spike/photo-view-plus` — APK auf S23 installiert, wartet auf Geräte-Test.

**Flutter/SDK-Check:** Flutter 3.44.0 / Dart 3.12.0 (≥ 3.14.5/3.1.0 ✅). minSdk = 29 (Android 10), unverändert ✅.

**Compat-Fixes in dieser Session:**
- `filterQuality: FilterQuality.high` (PV-Policy droppt auto auf medium während Gesture ✅)
- `bottomInset = MediaQuery.of(ctx).padding.bottom` in `_buildPage`
  → Caption-Gradient `height: 80 + bottomInset`
  → Caption-Zeile `bottom: 12 + bottomInset`
  → Zähler (kein Caption) `bottom: 12 + bottomInset`
  → ⓘ Lizenz `bottom: (hasCaption ? 88 : 12) + bottomInset`
  → Dreh-Hinweis `bottom: MediaQuery.of(context).padding.bottom + 60`
- `_clampPosition(rawPos, targetScale, index)` nach Double-tap-Zoom-in:
  verhindert Bild-außerhalb-Viewport bei Tap nahe am Rand

**Was bereits korrekt war:**
- Keine hartcodierten 390×844-Werte — alle Layout-Maße aus LayoutBuilder ✅
- SafeArea auf Zurück + Speaker (Notch/Punch-hole) ✅
- LimitedCoverScale: rein aus outerSize + childSize (beide Laufzeit) ✅
- `photo_view_plus: 1.1.1` exakt gepinnt ✅
- Predictive Back: nur `Navigator.of(context).pop()`, kein eigener Back-Handler ✅

**LimitedCoverScale Randfall-Analyse:**
- Nahezu quadratisch: sc ≈ sk → verwendet sk (cover, kein Letterbox) ✅
- Querformat-Bild (2:1) in Portrait: ~15% Crop gesamt, kein Letterbox ✅
- Extremes Panorama (3:1) in Portrait: Letterbox unvermeidlich, aber sc*1.18 < cover (83% crop) ✅ (kommentiert)
- Portrait-Bild (1:3) in Portrait: 15% Crop + ~11% Seitenbalken (< 15% gesamt) ✅

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
[ ] Bildquelle korrekt als imageProvider verdrahtet
[ ] Schwarzer Hintergrund
[ ] Randfälle: sehr breites Bild (Panorama), sehr hohes Bild, quadratisch
```

## 🔴 Test-Matrix (Emulator nötig — keine AVDs angelegt)

```
[ ] API 29 (Android 10, niedrigste unterstützte Version) — AVD nötig
[ ] Kleines Phone (kompakter Viewport, z.B. Pixel 4a 360×760dp) — AVD nötig
[ ] Tablet / großes Display — AVD nötig
[ ] Gerät mit Notch/Cutout — AVD nötig
[ ] Quer- und Hochformat-Bild je einmal durch alle Gesten
```

**Hinweis:** AVDs können in Android Studio unter Device Manager erstellt werden.
Alternativ: Test nur auf S23 + Querformat-Rotation akzeptieren.

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
