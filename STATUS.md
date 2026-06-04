# Wissensfreund — STATUS
<!-- updated: 2026-06-04T08:29:23Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟡 Gerade in Arbeit (Session 2026-06-04 — F1/F2 Restfehler)

**Branch:** `spike/photo-view-plus` — APK auf S23 installiert, wartet auf Gerätetest.

### Fixes implementiert (lib/widgets/image_fullscreen_overlay.dart)

**Vorherige Session (R1/R2/R3):**
- R1→covered überkorrigiert (>50% Crop)
- R2: `onTapUp` entfernt → kein TapGestureRecognizer in Arena
- R3: `Listener(onPointerDown:)` für Double-tap (kein Arena-Konflikt)

**Session 2026-06-04 (Feinschliff F1/F2-Diagnose):**

**F1 (Crop → Contained):** `contained * 1.18` → `PhotoViewComputedScale.contained`
für `initialScale`+`minScale`. Faktor 1.18 entfernt — jedes Überstehen verhindert
Wischen. Letterbox bei abweichendem Seitenverhältnis bewusst akzeptiert.
`_initialScaleFor()` gibt `min(w/W, h/H)` zurück (Zoom-out-Ziel numerisch konsistent).

**F2-Diagnose (Pinch 2. Touch):** Listener-Schicht (eigene Doppeltipp-Erkennung)
temporär entfernt. PV-DTGR mit null-Callback (`disableDoubleTap:true`) bleibt.
→ Wartet auf Gerätetest: greift Pinch jetzt beim ERSTEN Touch?
  JA → Listener war die Ursache → Doppeltipp via PV-native Callbacks lösen.
  NEIN → DTGR(null) ist das Problem → PhotoViewGallery-Refactor besprechen.

---

## 🔴 Diagnose-Test auf S23 (Antwort erforderlich!)

```
[ ] PINCH beim ERSTEN Touch — funktioniert es jetzt?
[ ] Bild steht NICHT horizontal über (vollständig sichtbar)
[ ] Wischen ohne Zoom wechselt Bild direkt
[ ] Aus gezoomtem Bild wischen → nächste Seite in Basis-Scale
[ ] Zurück- / Speaker- / ⓘ-Button | Caption | Schwarzer Hintergrund
```
Doppeltipp ist in dieser Diagnose-Version NICHT implementiert (Listener entfernt).

**Nächster Schritt nach Rückmeldung:**
- Pinch OK → Listener-freie Doppeltipp-Lösung implementieren (PV-native)
- Pinch NOK → PhotoViewGallery-Refactor (Rückmeldung abwarten)

**Nach Geräte-Parität:** `spike/photo-view-plus` → `main` mergen, Branch löschen.

---

## Kompatibilitäts-Audit 2026-06-03

Zielboden: Android 10 (API 29), 3 GB RAM, ~2016-Hardware.

**1. Build**
compileSdk=36 | targetSdk=flutter.targetSdkVersion (Flutter 3.44.0 → 35) | minSdk=29
NDK 28.2.13676358 | KEIN abiFilters/splits.abi → universelles APK (arm64-v8a + armeabi-v7a)

**2. ZIM-Reader**
Eigener Kotlin-Parser (RandomAccessFile) — KEINE libzim. Zstd-Cluster: native JNI
libzim_zstd.so (C-zstd 1.5.6 via CMake). XZ: org.tukaani:xz pure Java.
ABIs: Flutter-Default (arm64-v8a + armeabi-v7a) — 32-Bit dabei, kein Problem.

**3. On-Device-LLM**
Nicht implementiert — _handleGeminiPlaceholder() ist Stub mit TODO-Kommentar (Z. 1389).
Kein mediapipe/tflite/llama/gemma-Package in pubspec.

**4. 3D-Charakter**
Nicht vorhanden — professor_widget.dart ist 2D Flutter-Widget (AnimationController).
Kein filament/WebView/OpenGL-ES. Kein Fallback nötig.

**5. Google-Play-Services-Kopplung**
HART: BillingService (billing:6.2.1) → Play Store required. Bricht auf Fire OS/AOSP.
  Graceful Degradation: bei Verbindungsfehler → "free" (kein Crash).
STT: Android SpeechRecognizer (kein ML Kit) — funktioniert ohne Google-Services wenn
  Gerät eigene Erkennungs-Engine hat; fällt auf Cloud-Recognizer zurück (Retry-Logik).
TTS: flutter_tts → Android TTS (gerätenativ, Manifest fragt com.google.android.tts).
Firebase/Firestore/FCM/ML Kit: NICHT vorhanden.
→ Einzige harte Play-Kopplung: Billing.

**6. TTS**
flutter_tts → Android TTS-Engine (gerätenativ). Sprache: de-DE.
Wenn de-DE fehlt: flutter_tts fällt auf Gerätestandard zurück; kein App-seitiger Fallback.
Keine vorproduzierten Dateien für Professor-Sprache (ZIM-Audio ist separat).

**7. Eltern-Kiosk**
3 Mechanismen: Overlay (SYSTEM_ALERT_WINDOW + ForegroundService + onStop()),
DeviceAdmin (force-lock only), BiometricPrompt (ParentalUnlockActivity).
Blockiert: Home, Recents, Wischgesten, Notification-Tap.
NICHT blockiert: ADB, Accessibility-Service-Umweg (bekannte Einschränkung, doc. in Memory).
Screen Pinning (startLockTask) NICHT verwendet.

**8. Bild-Tier-Diskrepanz (nur vermerkt — nicht aufgelöst)**
App (asset_config.dart): thumb=300px | standard=800px | pro=1200px
Pipeline (download_images.py / CLAUDE_CHAT_NOTIZEN): thumb=300px | standard=800px | pro=1600px
→ pro-Tier Diff: App erwartet 1200px, Pipeline erzeugt 1600px. Auflösung ausstehend.

---

## 🟡 Zum Testen (ausstehend)
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche)
- Mode B Lupe: _ttsCursor erst im progressHandler updaten (zu frühes Highlight)

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
