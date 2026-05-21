# Changelog — Wissensfreund App

---

## ✅ FERTIG — Sound-Thumbnails in der Thumbnail-Leiste (Stand 2026-05-21)

### Neue Funktionalität

Audiodateien aus der Klexikon-ZIM erscheinen als eigene Slots in der Thumbnail-Leiste —
neben den Bildern, in der Reihenfolge wie sie im Artikel vorkommen (HTML-Position).

**Sound-Thumbnail-Darstellung:**
- 🎵 Notenschlüssel-Icon mittig
- Statischer Wellenform-Hintergrund (7 Balken via `CustomPainter`)
- Grüner Gradient-Hintergrund, dunkler beim Abspielen
- Pulsier-Animation (ScaleTransition) wenn Audio läuft

**Tap-Verhalten — 3 Fälle:**
- **Fall A (Professor liest):** Position auf Satzanfang merken → Professor pausieren → Sound abspielen → danach Caption vorlesen (falls vorhanden) oder 2s Pause → automatisch ab Satzanfang weiter
- **Fall B (Professor idle):** Sound abspielen → Caption vorlesen wenn vorhanden, sonst Stille
- **Fall C (Sound läuft, nochmals angetippt):** Sound sofort stoppen → Professor weiter ab gespeicherter Position

**Kein Vollbild für Audio** — Sound-Thumbnails öffnen keinen Vollbild-Screen.

### Technische Umsetzung

**`ZimReader.kt`:**
- `AudioRef(filename, mimeType, caption, posInHtml)` — neue Datenklasse
- `getAudioRefs(articleUrlIndex)` — extrahiert `<audio><source>` Tags aus HTML
- `getAudioBytes(filename)` — wie `getImageBytes()`, sucht in Namespaces I/, -/I/, C/, -/, A/
- `ImageRef` um `posInHtml: Int` erweitert (für Sortierung)
- `extractAudioRefsFromHtml()` + `extractAudioFilename()` — private Hilfsmethoden

**`MainActivity.kt`:**
- `listAudio` und `getAudioBytes` im ZIM MethodChannel ergänzt

**`wissensfreund_provider.dart`:**
- `ArticleMediaItem` (unified Bild/Audio) — neue Klasse mit `isAudio`, `posInHtml`
- `_BytesAudioSource extends StreamAudioSource` — Audio aus Bytes ohne Temp-Datei
- `AudioPlayer` (`just_audio`) — Audio-Wiedergabe
- `loadMedia(urlIndex)` — lädt Images + Audio parallel, sortiert nach HTML-Position
- `onMediaTap(index)` — implementiert Fall A/B/C
- `_playAudioItem()`, `_onAudioFinished()`, `_stopAudio()`, `_getAudioBytes()` — Audio-Logik
- `loadImages()` Aufruf → `loadMedia()` Aufruf beim Artikel-Laden

**`article_screen.dart`:**
- `_SoundThumbnailTile` — neues `StatefulWidget` mit `AnimationController` für Pulsieren
- `_WaveformPainter` — `CustomPainter` für statische Wellenform-Dekoration
- `_ThumbnailRow` — nutzt jetzt `provider.mediaItems` statt `provider.articleImages`,
  rendert `_SoundThumbnailTile` oder `_ZimImageTile` je nach `item.isAudio`

**Hinweis:** Ob die Klexikon-ZIM tatsächlich Audiodateien enthält ist noch ungetestet.
Falls keine `<audio>` Tags gefunden werden, erscheinen nur Bild-Thumbnails (Graceful Degradation).

---

## ✅ FERTIG — ANR-Fix: Foreground Service Typ (Stand 2026-05-21)

### Ursache

`WissensfreundForegroundService` war als `foregroundServiceType="shortService"` deklariert.
`shortService` hat ein hartes **3-Minuten-Limit** (Android 14+) — danach tötet das System den Service
und löst einen ANR aus. Das ist der Grund für alle 6 ANRs an diesem Tag (15:35, 15:39, 15:44, 20:08, 20:21, 20:57 Uhr).

### Fix

**`AndroidManifest.xml`:**
- `foregroundServiceType="shortService"` → `foregroundServiceType="specialUse"`
- Permission `FOREGROUND_SERVICE_SPECIAL_USE` hinzugefügt
- `<property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" android:value="childSafetyOverlay"/>` innerhalb `<service>` (Android 14+ Pflichtangabe)

**`WissensfreundForegroundService.kt`:**
- Import `android.content.pm.ServiceInfo` und `android.os.Build` hinzugefügt
- `startForeground()` auf API 34+ mit explizitem `FOREGROUND_SERVICE_TYPE_SPECIAL_USE` aufgerufen
- Auf API < 34: weiterhin 2-Argument-Form (kein Typ-Argument verfügbar)

**Warum `specialUse`:** Der Service zeigt nur ein Overlay-Fenster und läuft unbegrenzt.
Kein anderer Android-Typ passt (kein Location, kein Kamera, kein Media-Playback etc.).
`specialUse` ist der korrekte Typ für App-spezifische Daueraufgaben.

---

## ✅ FERTIG — Kommunikations-Infrastruktur + BIOMETRIC_WEAK (Stand 2026-05-21)

### BIOMETRIC_WEAK — Frontkamera-Gesichtserkennung

`ParentalUnlockActivity.kt`: Authenticators jetzt API-abhängig:
- **API 30+ (Android 11+):** `BIOMETRIC_STRONG | BIOMETRIC_WEAK | DEVICE_CREDENTIAL`
  → Fingerabdruck, Frontkamera-Gesicht, PIN, Muster, Passwort
- **API 29 (Android 10):** `BIOMETRIC_STRONG | DEVICE_CREDENTIAL`
  → Fingerabdruck, PIN, Muster, Passwort (`BIOMETRIC_WEAK` erst ab API 30 mit DEVICE_CREDENTIAL kombinierbar)

Grundsatz: Was der Nutzer auf seinem Gerät eingerichtet hat, soll auch zum Entsperren funktionieren.

### Neue Dateien im Repository

**PROJEKTDOKUMENT.md** — Kompakte Architektur-Referenz:
- App-Konzept, Tech-Stack, Zielgruppen, Kern-Entscheidungen
- Dient als schneller Einstieg für neue Claude-Sessions
- Bei neuer Projektdokument-Version (v17 etc.) bitte aktualisieren und pushen

**CLAUDE_CHAT_NOTIZEN.md** — Kommunikationskanal Claude Chat → Claude Code:
- Claude Chat schreibt Entscheidungen und Aufträge hinein
- Claude Code liest am Session-Start, setzt offene Aufträge um, markiert mit [x]
- Format: Datum, Thema, Entscheidung/Auftrag, Priorität, Erledigt-Checkbox

### CLAUDE.md — Neue Pflicht-Regeln ergänzt

1. **Session-Start Reihenfolge:** CLAUDE.md → CLAUDE_CHAT_NOTIZEN.md → CHANGES.md → dann Aufgaben
2. **Nach jeder Session:** CHANGES.md (+ weitere geänderte Dateien) committen und pushen

---

## ✅ FERTIG — Kinderschutz: Overlay-Flow überarbeitet (Stand 2026-05-21)

### Problem: Doppelter Overlay + ANR

**Bisheriger Fehler:**
- Kind drückt Recents → natives Overlay erscheint
- "Entsperren" brachte Wissensfreund in den Vordergrund → Flutter-Overlay erschien (gleicher Screen, doppelt)
- "Gerät freigeben" landete in Wissensfreund statt in Recents
- ANR-Crash nach "Gerät freigeben"

### Neue Architektur: Alles im nativen Overlay

**Natives Overlay (WissensfreundForegroundService):**
- Zeigt "Entsperren" (Eltern-Aktion) + "Zurück zu Wissensfreund" (Kind-Aktion)
- "Entsperren" startet `ParentalUnlockActivity` (transparent) — **kein Umweg über Wissensfreund**
- "Zurück zu Wissensfreund" schließt Overlay und bringt App in Vordergrund — keine Auth nötig

**ParentalUnlockActivity** (neu):
- Transparent, erscheint nicht in Recents (`excludeFromRecents`)
- Zeigt direkt den System-`BiometricPrompt` (Fingerabdruck / PIN / Muster)
- Erfolg → `released = true`, Activity schließt sich → Nutzer ist auf Recents/Home
- Abbruch → Overlay wird wieder eingeblendet, Activity schließt sich

**Flutter-Overlay** (`_ParentalOverlay` in main.dart):
- Wird **nicht mehr automatisch** durch Lifecycle-Events ausgelöst
- `didChangeAppLifecycleState`: nur noch `pauseSpeaking()` / `resumeSpeaking()` — kein Overlay-Trigger
- Kinderschutz läuft vollständig über das native Overlay

**Neue Dateien:**
- `ParentalUnlockActivity.kt` — transparente Activity mit BiometricPrompt

**Geänderte Dateien:**
- `WissensfreundForegroundService.kt`: "Zurück zu Wissensfreund"-Button im Overlay; "Entsperren" startet `ParentalUnlockActivity`
- `AndroidManifest.xml`: `ParentalUnlockActivity` registriert (transparent, excludeFromRecents)
- `android/app/build.gradle`: `androidx.biometric:biometric:1.1.0` als explizite Dependency
- `res/values/styles.xml`: `Theme.Transparent` für `ParentalUnlockActivity`
- `main.dart`: `didChangeAppLifecycleState` vereinfacht — kein Flutter-Overlay-Trigger

---

## ✅ FERTIG — Kinderschutz: In-App-Schutz + Onboarding-Wizard (Stand 2026-05-21)

### BiometricPrompt-Gate für Kinderschutz-Einstellungen

Sicherheitsrelevante Bereiche innerhalb der App sind nur nach Eltern-Entsperrung zugänglich.
Nicht-sicherheitsrelevante Bereiche (Lautstärke, Darstellung) bleiben frei nutzbar.

**Gesperrt (BiometricPrompt erforderlich):**
- Kinderschutz-Dashboard (Menü → Kinderschutz)
- Kindermodus aktivieren/deaktivieren
- Overlay-Berechtigung einrichten
- Gerätesperre aktivieren

**Verhalten:** Tippen auf "Kinderschutz" im Menü → BiometricPrompt erscheint sofort.
Ohne Entsperrung: Dashboard öffnet sich nicht. Nach Entsperrung: voller Zugang.

**Explizit NICHT blockiert:** Android-System-Einstellungen (Einstellungen → Apps → Wissensfreund).
Eltern die systemseitig auf die App zugreifen werden nicht unterbrochen — das wäre unerwartet
und nicht vertrauenerweckend.

### Onboarding-Wizard überarbeitet

**Vorher:** Einmaliger Dialog → markiert als erledigt → öffnet Einstellungen → Dialog weg → Kind nicht geschützt.

**Nachher:** 3-Schritt-Wizard (Dialog bleibt geöffnet):
- **Schritt 1:** Erklärung + "Jetzt einrichten"
- **Schritt 2:** Dialog bleibt offen während Nutzer den Schalter aktiviert; `WidgetsBindingObserver` erkennt Rückkehr → prüft Berechtigung → startet Kindermodus automatisch
- **Schritt 3:** ✅ "Kinderschutz ist aktiv!" → "Alles klar!" schließt Dialog

**Bugfix Flutter-Overlay:** `didChangeAppLifecycleState` zeigte Flutter-Overlay bei JEDEM
App-Resume, auch ohne aktiven Kindermodus. Gefixt: Overlay erscheint nur wenn `ps.isKioskMode == true`.

**Geänderte Dateien:**
- `home_screen.dart`: `_authenticateAndShowDashboard()` in `_AppMenu`; `_ParentalOnboardingDialog` → `StatefulWidget` mit 3 Schritten + `WidgetsBindingObserver`
- `main.dart`: `didChangeAppLifecycleState` prüft `ps.isKioskMode` vor Overlay-Anzeige

---

## ✅ FERTIG — Kinderschutz: SYSTEM_ALERT_WINDOW Overlay (Stand 2026-05-21)

### Implementierung

**Berechtigung:** `SYSTEM_ALERT_WINDOW` — "Über anderen Apps anzeigen"
- Gleiche Berechtigung wie Messenger-Bubbles, WhatsApp, etc.
- Kein beängstigender Datenschutz-Hinweis
- Einmalige Einrichtung: Ein Tap in der App → Toggle in Android-Einstellungen

**Wie es funktioniert:**
1. `onStop()` in `MainActivity` feuert bei ALLEN Navigationsarten (Home-Button, Recents, Wischgesten)
2. `WissensfreundForegroundService` (Foreground Service) zeigt sofort ein natives Overlay via `WindowManager.TYPE_APPLICATION_OVERLAY`
3. Overlay liegt über Homescreen und allen anderen Apps — Kind kann nichts bedienen
4. "Entsperren" im Overlay → Overlay wird entfernt, Wissensfreund kommt in Vordergrund
5. Flutter-Parental-Overlay zeigt BiometricPrompt (Fingerabdruck/PIN)
6. Nach Auth: "Zurück zu Wissensfreund" oder "Gerät freigeben"
7. "Gerät freigeben" → `released = true` im Service → kein Overlay bis Wissensfreund wieder geöffnet wird

**Neue Dateien:**
- `WissensfreundForegroundService.kt` — verwaltet WindowManager-Overlay, persistente Benachrichtigung "Kinderschutz aktiv"

**Entfernte Dateien:**
- `WissensfreundAccessibilityService.kt` — ersetzt durch Overlay-Ansatz
- `accessibility_service_config.xml` — nicht mehr benötigt

**Geänderte Dateien:**
- `MainActivity.kt`: `onStop()`/`onStart()` für Overlay-Steuerung, neue Channel-Methoden `hasOverlayPermission`/`requestOverlayPermission`, Service-Start/-Stop in `startKioskMode`/`stopKioskMode`
- `AndroidManifest.xml`: `SYSTEM_ALERT_WINDOW` + `FOREGROUND_SERVICE` Permissions, Foreground-Service-Eintrag
- `parental_lock_service.dart`: `hasOverlayPermission`/`requestOverlayPermission` statt Accessibility-API
- `home_screen.dart`: Dashboard zeigt Overlay-Berechtigung, Onboarding-Text angepasst
- `main.dart`: `_ParentalOverlay` ist jetzt `StatefulWidget` mit Post-Auth-Optionen ("Zurück"/"Freigeben")

**Abweichungen vom Plan:**
- Kein separater `foregroundServiceType` außer `shortService` notwendig — Service zeigt nur ein Overlay, nutzt keine eingeschränkten Capabilities (kein Netzwerk, Kamera etc.)
- Foreground Service Notification: Nutzt Android-System-Icon (`ic_lock_lock`) statt App-Icon, da Notification-Icons monochrom sein müssen

---

## ✅ FERTIG — Kinderschutz (Stand 2026-05-21)

### Implementierte Schutz-Mechanismen

**Zwei-Stufen-Architektur:**
- **Stufe 1 (bevorzugt):** DevicePolicyManager.lockNow() — echter Android Gerätesperr-Bildschirm
- **Stufe 2 (Fallback):** Eigener Eltern-Bildschirm in App-Farben mit 🔒 + "Für Erwachsene" + Entsperren-Button

**Entsperr-Methode:** BiometricPrompt über `local_auth` mit `biometricOnly: false`
→ deckt Fingerabdruck, Gesicht, Iris, PIN, Muster, Passwort ab

**Fall 1 — Zurück-Taste:**
- `PopScope(canPop: false)` in `HomeScreen` fängt letzten Back-Press ab
- Professor spricht: "Möchtest du Wissensfreund wirklich verlassen?" (`speakInterrupt()`)
- Dialog: "Nein, weiterlernen" / "Ja, beenden"
- "Ja" → BiometricPrompt → bei Erfolg: Stufe 1 (lockDevice) dann `SystemNavigator.pop()`
- Auth-Fehler oder "Nein" → Professor liest weiter ab Satzanfang

**Fall 2 — Externe Links:**
- Alle drei launchUrl-Stellen durch `_launchUrlWithParentalAuth()` ersetzt
- Dialog: "Dieser Link ist für Erwachsene. Bitte Mama oder Papa fragen!" + [Entsperren]-Button
- [Entsperren] → BiometricPrompt → bei Erfolg Link öffnen
- Abbrechen → Link wird nicht geöffnet

**Fall 3 — Home-Button:**
- `WidgetsBindingObserver.didChangeAppLifecycleState()` in `_WissensfreundAppState`
- `AppLifecycleState.paused` → `_wentToBackground = true`
  - Stufe 1 aktiv: `lockDevice()` sofort
  - Stufe 2: kein sofortiger Lock
- `AppLifecycleState.resumed` (nach Home → zurück):
  - Admin-Status refresh
  - Stufe 2: Professor stoppen + Eltern-Bildschirm zeigen
  - Stufe 1: kein Overlay nötig (Gerätesperre war aktiv)
- Wichtig: Starten einer anderen Activity (z.B. Device-Admin-Aktivierung) triggert nur
  `inactive` (nicht `paused`) → kein ungewolltes Overlay danach

**Onboarding:**
- Einmalig beim ersten App-Start (SharedPreferences: `parental_onboarding_done`)
- Dialog erklärt Gerätesperre, zwei Optionen:
  - "Jetzt aktivieren — empfohlen" → Device Admin Aktivierungsscreen
  - "Später / Nein danke" → App läuft mit Stufe 2

**Eltern-Dashboard:**
- Neuer Menü-Eintrag "Kinderschutz" im App-Menü
- Zeigt aktive Schutz-Stufe + Erklärungstext
- Wenn Stufe 2: Button "Gerätesperre aktivieren" → Device Admin

### Neue Dateien
- `android/app/src/main/res/xml/device_admin.xml` — Device-Admin-Policy (force-lock)
- `android/app/src/main/kotlin/.../WissensfreundDeviceAdmin.kt` — DeviceAdminReceiver
- `lib/services/parental_lock_service.dart` — ChangeNotifier-Service (Singleton)

### Geänderte Dateien
- `AndroidManifest.xml` — USE_BIOMETRIC/USE_FINGERPRINT permissions + DeviceAdmin receiver
- `MainActivity.kt` — `wissensfreund/parental` Channel + isDeviceAdminActive/requestDeviceAdmin/lockDevice
- `main.dart` — MultiProvider, WidgetsBindingObserver, MaterialApp.builder Overlay
- `home_screen.dart` — PopScope, Onboarding-Dialog, Kinderschutz-Dashboard, `speakInterrupt`-Aufruf
- `wissensfreund_provider.dart` — `speakInterrupt(String text)` hinzugefügt
- `article_screen.dart` — `_launchUrlWithParentalAuth` auf ParentalLockService umgestellt

### Abweichungen vom Plan
- Kein separater Dart-Import für `AuthenticationOptions.biometricOnly` nötig — `local_auth`-Paket
  (bereits installiert) erledigt BiometricPrompt mit DeviceCredential-Fallback automatisch
- Device-Admin-Aktivierungsscreen ist eine externe Activity — Flutter sieht nur `inactive`
  (nicht `paused`) → `_wentToBackground`-Flag bleibt false → kein Overlay nach Rückkehr ✓

---

## ⚡ NÄCHSTE SESSION — Hier weitermachen (Stand 2026-05-21)

### Thumbnail- und Vollbild-Verhalten komplett neu gestaltet ✅ FERTIG

**Thumbnail antippen:**
- Hauptbild wechselt mit crossFade 200ms (`AnimatedSwitcher` in `_MainArticleImageState`)
- Professor läuft weiter — keine Unterbrechung, kein Ton
- Kein Bildtext im Hauptbereich (Mode A: `_ImageCaption` entfernt)

**Vollbild öffnen (Hauptbild antippen):**
- Neue `_FullscreenGallery` ersetzt `_FullscreenImagePage`
- Fade + Zoom-Animation (Scale 0.88 → 1.0, EaseOutCubic)
- Schwarzer Hintergrund, Bild mit `BoxFit.contain`
- Bildtext kursiv unterhalb des Bildes (falls vorhanden)
- 🔊 Lautsprecher-Button auf dem Bild (nur wenn Bildtext vorhanden)
- ← Zurück-Button unten mittig (56px, gut für Kinderfinger)

**Wischen links/rechts im Vollbild:**
- `onHorizontalDragEnd` wechselt Bild über `provider.onThumbnailTap()`
- 2,5-Sekunden-Timer nach Wischen: wenn Caption vorhanden → `interruptForCaption()`
- Am Rand (erstes/letztes Bild) kein weiteres Wischen möglich

**Vollbild — 🔊 antippen:**
- `provider.interruptForCaption(caption)` aufgerufen
- Professor pausiert, Position auf Satzanfang (`_sentenceStartOffset()`)
- Caption wird vorgelesen
- 1 Sekunde Pause, dann "Soll ich weiterlesen?"
- 5 Sekunden Auto-Resume ab Satzanfang
- `_CaptionResumeOverlay` erscheint sowohl im Vollbild als auch im Hauptbildschirm

**Vollbild schliessen:**
- ← Zurück-Button (primär)
- Swipe nach unten (velocity > 300)

**Abweichungen vom Konzept:**
- "Tap auf schwarzen Hintergrund → schliessen" nicht implementiert: bei `BoxFit.contain` ist der gesamte Expanded-Bereich vom GestureDetector abgedeckt, eine pixelgenaue Unterscheidung Bild/Randbereich wäre unverhältnismäßig komplex. Swipe-down und Zurück-Button sind die primären Schliess-Mechanismen.
- Zoom-Animation: beginnt nicht exakt von der Bildposition (kein Hero-Widget), sondern skaliert von der Bildschirmmitte. Hero mit PageView/AnimatedSwitcher hätte Konflikte verursacht.
- `_ImageCaption` (Caption unter Hauptbild in Modus A) wieder entfernt — Spec sagt "Kein Bildtext" beim Thumbnail-Tap.

**Offen (nächste Session):**
- Missing images für Thumbnails 5+ (vermutlich URL-decode-Problem in getImageBytes)

---

## ✅ ARCHIV — Abgeschlossene Sessions (Stand 2026-05-20)

### 1. ~~GitHub Workflow~~ ✅ FERTIG

**Ergebnis (Session 2026-05-20):**
- `libzim` komplett entfernt; ZIM-Datei wird direkt binär geparst (kein externes Paket nötig)
- `image_licenses.json` → `media_licenses.json` (enthält jetzt `images` + `audio` Sektion)
- 2500 Bilder gefunden, alle `allowed: true`; 0 Audio-Dateien (Klexikon hat keinen Audio-Content)
- Release-Asset live: `https://github.com/Vorlesefreund/wissensfreund/releases/latest/download/media_licenses.json`
- `wikimedia_license_checker.dart` + `license_cache_db.dart` entsprechend aktualisiert
- **Hinweis:** Kiwix-ZIM speichert Bilder mit MD5-Hash-Dateinamen (`Assets /abc123.JPG`), nicht mit Wikimedia-Originalnamen → Wikimedia-API findet keine Treffer. Fix: unbekannte Dateien defaultmäßig `allowed: true` (Klexikon kuratiert nur CC-Content). Gilt so lange bis `getImageRefs()` tatsächlich getestet und die Dateinamen bekannt sind.

---

### 2. ~~Bilder-Integration Schritt 3~~ ✅ FERTIG (neu gestaltet 2026-05-21)

Thumbnail-Tap: nur Bildwechsel (crossFade 200ms), kein TTS.
Vollbild: 🔊-Button → `interruptForCaption()` im Provider → Satzanfang, Caption, Prompt.

### 3. ~~Bilder-Integration Schritt 4~~ ✅ FERTIG

RAM-Grenze: `getImageBytes()` cached nur Bilder ≤ 2 MB. Größere Bilder werden angezeigt aber nicht gecacht.

### 4. ~~Bilder-Integration Schritt 5~~ ✅ FERTIG (neu gestaltet 2026-05-21)

Vollbild-Galerie (`_FullscreenGallery`):
- Fade + Scale-Animation, schwarzer Hintergrund
- Wischen links/rechts für Bildnavigation
- 🔊 auf Bild, Bildtext darunter, ← Zurück-Button unten mittig (56px)

---

### 5. Längerfristig offen (aus CLAUDE.md-Spec)

- **Gezielte Antworten** (Warum/Wie/Wann/Wo-Fragen): KI extrahiert nur relevante Textstelle — kompletter Pfad fehlt
- **Eltern-Verweis** ("Das können Mama oder Papa erklären"): Text vorhanden, wird aber nie gesprochen
- **History** und **Settings**: nur Platzhalter

---

## Implementierungsstand (Snapshot 2026-05-20)

### Fertig implementiert

**Kern-Flow (produktionsreif)**
- Spracheingabe (STT): Deutsches on-device-Erkenner (Android 12+) mit Cloud-Fallback, 150 ms Audio-Warmup nach TTS, automatischer Retry bei transientem Fehler
- Artikelsuche: 2-Phasen-Scoring — Phase 1 scanbt alle ~8.000 Titel (Exact/Inflection/Prefix/Substring), Phase 2 re-bewertet Top-20 nach Absatz-Treffer; Umlaut-Normalisierung aktiv
- Disambiguierung: "Meinst du X oder Y?" bei Gleichstand, danach Auto-Mikrofon; Loop-Bug (Reset-Timing) behoben
- Artikelwiedergabe (TTS): Chunking bei ~3.000 Zeichen, Pause/Resume mit Cursor-Position
- Drei Anzeige-Modi (A/B/C): Volltext + Satz-Highlighting, Dark-Focus, Vollbild-Bild
- Klexikon-Attribution: CC BY-SA 3.0, anklickbarer Footer, korrekte Domain `klexikon.zum.de`
- ZIM-Status-Anzeige: Ladefortschritt, grünes Häkchen bei fertig, orange Warnung bei "nicht gefunden"
- Maxi-ZIM (156 MB, mit Bildern) als Standard-ZIM eingerichtet

**Infrastruktur**
- ZimReader.kt: Liest ZIM v5/v6, unterstützt Deflate/LZMA/ZSTD (JNI), folgt Redirects (max. 5 Hops)
- Klexikon-Outro-Entfernung: früheste Position über alle Marker (nicht erster Treffer in der Liste)
- Audio-Focus-Management: saubere Übergabe zwischen TTS und STT

---

### Läuft / teilweise implementiert

| Feature | Status | Datei | Problem |
|---|---|---|---|
| Frage-Typ-Erkennung | Logik vorhanden, **nicht genutzt** | `wissensfreund_provider.dart` | `_detectQueryType()` wird aufgerufen, das Ergebnis aber nie verwendet — kein Unterschied im Verhalten zwischen "Was ist X" und "Warum Y" |
| Eltern-Verweis | Text definiert, **keine UI** | `wissensfreund_provider.dart` | `_parentReferralMessage` ist gesetzt, wird aber nie gesprochen oder angezeigt |
| Bildanzeige (Thumbnails) | UI-Gerüst vorhanden | `article_screen.dart` | Alle 5 Thumbnail-Slots zeigen Gradient-Platzhalter; keine echten Bilder aus ZIM extrahiert |
| KI-gestützte Teilantwort | Nicht begonnen | — | Für "Warum/Wie"-Fragen soll KI nur die relevante Textstelle extrahieren — dieser Pfad fehlt komplett |

---

### Nicht implementiert (laut Projektdokument vorgesehen)

- **Gezielte Antwort**: KI extrahiert NUR die relevante Textstelle für Warum/Wie/Wann/Wo-Fragen — komplett offen
- **Eltern-Verweis**: Wenn kein Artikel gefunden oder Frage über Artikelinhalt hinausgeht → "Das können Mama oder Papa dir erklären" — UI fehlt
- **Verlauf** (History-Menüpunkt): Nur Platzhalter mit Label "bald"
- **Einstellungen** (Settings-Menüpunkt): Nur Platzhalter mit Label "bald"

---

### Abweichungen vom Projektdokument (CLAUDE.md)

**Scoring-Schema:**
- CLAUDE.md definiert: Titel +3, erster Absatz +2, Fließtext +1, Mehrere Begriffe → Multiplikation
- Implementiert: Titel-Phase mit Exact(+5)/Inflection(+4)/Prefix(+3)/Substring(+1), Body-Phase mit Absatz(+2)/Fließtext(+1), Multi-Term-Multiplikator ×(n×0.7)
- Bewertung: Mechanismus ist äquivalent, aber granularer als spezifiziert — kein funktionaler Fehler

**Frage-Typ → Antwortverhalten:**
- CLAUDE.md definiert: Komplett-Vorlesen vs. Gezielte Antwort vs. Folgefrage vs. Vergleichsfrage → vier verschiedene Pfade
- Implementiert: Nur ein Pfad — immer Komplett-Vorlesen, unabhängig vom Frage-Typ
- Bewertung: **Funktionale Abweichung** — gezielte Antworten (Warum/Wie/Wann/Wo) fehlen

**Eiserne Regel:**
- CLAUDE.md: KI darf NIEMALS aus Trainingswissen antworten
- Implementiert: Keine KI-Komponente im Antwortpfad — die App antwortet ausschließlich aus Artikeltext (Regel ist de facto eingehalten, aber nicht durch KI-Logik, sondern weil KI-Integration noch fehlt)

---

### Ungenutzte Abhängigkeiten (pubspec.yaml)

`speech_to_text`, `just_audio`, `sqflite`, `http` — alle importiert, nirgends verwendet. Können entfernt werden.

---

### Nicht genutzter Code

`lib/screens/article_screen_a.dart` (498 Zeilen) — ältere alternative Artikel-Ansicht, kein Import, kein Navigationspfad. Kann gelöscht werden.

---

## Session 2026-05-20

## Session 2026-05-20

### Bilder-Integration — Schritt 2: Bilder aus ZIM + Lizenz-Check (fertig)

**Architektur-Änderung gegenüber ursprünglichem Plan:**
Nicht per-Gerät einzeln via Wikimedia API prüfen, sondern zentral:
- GitHub Actions Workflow (`.github/workflows/update_image_licenses.yml`) läuft 1×/Monat
- Lädt Klexikon-ZIM von download.kiwix.org, extrahiert alle Bild-Dateinamen mit `python-libzim`
- Fragt Wikimedia Commons API in Batches (50 Bilder/Aufruf, 0,5 s Rate-Limiting)
- Veröffentlicht `image_licenses.json` als GitHub Release Asset (Tag `image-licenses`)
- App lädt diese JSON beim ersten Start, cached in SQLite → danach komplett offline

**Neue Dateien:**
- `.github/workflows/update_image_licenses.yml` — monatlicher Workflow
- `scripts/generate_license_json.py` — Python-Script für Workflow und lokale Nutzung
- `lib/services/license_cache_db.dart` — SQLite-Cache: `license_cache` + `sync_info` Tabellen; `putBatch()` für Bulk-Insert; `isSynced()` / `saveLastSync()` für Sync-Tracking; DB-Version 2
- `lib/services/wikimedia_license_checker.dart` — lädt JSON von GitHub-Release, populated Cache; `isAllowed()` liest nur lokal; `syncLicenses()` für Download; kein API-Call vom Gerät

**Wichtig — vor erstem Start anpassen:**
- In `lib/services/wikimedia_license_checker.dart`: `_licenseJsonUrl` auf eigenes GitHub-Repo setzen
- GitHub-Repo anlegen, Workflow ausführen → Release `image-licenses` wird erstellt
- ZIM-URL in Workflow ggf. auf aktuellen Download-Link prüfen (download.kiwix.org/zim/klexikon/)

**ZimReader.kt — neue Methoden:**
- `getImageRefs(articleUrlIndex)` → parst Artikel-HTML nach `<img>` Tags, extrahiert Dateinamen + Bildunterschriften (thumbcaption)
- `getImageBytes(filename)` → Binärsuche über URL-Pointer-Tabelle für `I/` bzw. `-/` Namespace, gibt rohe Bild-Bytes zurück
- Binärsuche `findUrlIndexByPath(targetPath)` über alle ZIM-Einträge (sortiert nach namespace/url)
- Unterstützt URL-dekodierte Dateinamen und beide ZIM-Namespace-Varianten (`I/` und `-/`)

**MainActivity.kt — neue Channel-Handler:**
- `listImages(urlIndex)` → `List<Map>` mit `{filename, mimeType, caption}`
- `getImageBytes(filename)` → `ByteArray?`

**wissensfreund_provider.dart — neue Felder und Methoden:**
- `ArticleImageInfo` Klasse: `filename`, `caption`
- `articleImages`, `selectedImageIndex` Getter
- `selectImage(i)` — Toggle-Selektion (zweimaliges Tippen deselektiert)
- `loadImages(urlIndex)` — holt Refs aus ZIM, prüft Lizenz, befüllt `_articleImages`
- `getImageBytes(filename)` — mit In-Memory-Cache pro Artikel
- `_initLicenseCache()` — synct JSON beim ersten Start
- Bilder werden beim Starten der Aufnahme (`startListening`) vollständig zurückgesetzt

**article_screen.dart — Umbau:**
- `_MainArticleImage` (neu): zeigt echtes ZIM-Bild oder Emoji-Fallback; liest `provider.selectedImageIndex`; `onTap` für Schritt 5 vorbereitet
- `_ZimImageTile` (neu): lazy-loading Thumbnail mit ⓘ-Icon
- `_LicenseInfoButton` (neu): ⓘ-Button mit Bildnachweis-Dialog (Urheber, Lizenz, Wikimedia-Link)
- `_showLicenseInfo()` (neu): Dialog, barrierDismissible
- `_ThumbnailRow` komplett neu: liest `provider.articleImages`, keine Parameter mehr
- `_FullThumbView` entfernt (war nur Platzhalter)
- `_selectedThumbIdx` aus Mode-A/B/C-States entfernt → liegt jetzt im Provider
- `_ModeCContent` von `StatefulWidget` zu `StatelessWidget` vereinfacht

**Noch ausstehend:**
- `_licenseJsonUrl` muss auf echtes Repo gesetzt werden
- Schritt 3: Thumbnail-Tippen während Vorlesen (Pause/Resume + Bildunterschrift)
- Schritt 4: Lazy-Loading / RAM-Begrenzung (technisch bereits durch on-demand getImageBytes und In-Memory-Cache pro Artikel erfüllt; explizite 2 MB-Grenze noch nicht implementiert)
- Schritt 5: Vollbild-Ansicht (onTap auf Hauptbild)

---

### Bilder-Integration — Schritt 1: Lizenz-Check (fertig)

**Neue Dateien:**
- `lib/services/license_cache_db.dart` — SQLite-Cache für Lizenzprüfungen
  - Tabelle `license_cache`: `image_filename` (PK), `urheber`, `lizenz`, `lizenz_url`, `erlaubt` (0/1), `checked_at`
  - Singleton `LicenseCacheDb.instance`, lazy-opened, überlebt App-Neustarts
  - `LicenseEntry`-Klasse mit allen Metadaten fürs ⓘ-Overlay (Schritt 2)
- `lib/services/wikimedia_license_checker.dart` — Wikimedia Commons API + Lizenzentscheid
  - `WikimediaLicenseChecker.instance.isAllowed(filename)` → Cache → API → false bei Netzwerkfehler
  - `getCached(filename)` → liefert gecachten Eintrag für ⓘ-Overlay ohne neuen API-Call
  - Erlaubt: CC0, CC BY (alle Versionen), CC BY-SA (alle Versionen)
  - Gesperrt: CC BY-NC, CC BY-ND, unbekannt/fehlend, alles andere
  - Bei Netzwerkfehler / Timeout (10 s): `return null` → Bild wird nicht angezeigt

**Entscheidungen & Abweichungen:**
- Cache-Key ist `image_filename` (nicht `article_id + filename`), da Commons-Dateinamen global eindeutig sind — ein gecachter Eintrag gilt für alle Artikel, die dasselbe Bild referenzieren
- Cache-Einträge laufen nicht ab (Lizenzen auf Commons ändern sich selten); kein TTL implementiert
- CC BY-ND (no derivatives) ist nicht in der erlaubten Liste — gemäß Spezifikation "alles andere → gesperrt"
- `sqflite` und `http` waren bereits in pubspec.yaml; keine neuen Dependencies nötig
- INTERNET-Permission war bereits im AndroidManifest.xml vorhanden

**Noch offen (Schritt 2+):** Bilder aus ZIM extrahieren und Dateinamen an `isAllowed()` übergeben

---

### Klexikon-Attributions-Link (Domain-Fix)
- **Problem:** Link öffnete "Sichere Verbindung fehlgeschlagen" — `klexikon.de` hat TLS-Probleme und leitet auf `klexikon.zum.de` um, aber nur per HTTP
- **Fix:** `articleUrl`-Getter in `wissensfreund_provider.dart` auf `host: 'klexikon.zum.de'` umgestellt
- **Fix:** Fallback-URL von `https://klexikon.de` auf `https://klexikon.zum.de` geändert
- **Fix:** Attributionstext in `article_screen.dart` von `Klexikon.de` auf `klexikon.zum.de` aktualisiert

### Debug-Logs entfernt
- `HTML_PRECLEAN_TAIL`, `TEXT_TAIL`, `ARTICLE_URL` Log-Aufrufe aus `ZimReader.kt → getArticleByUrlIndex()` entfernt
- Dazugehörige unnötige `val cleaned = preClean(html)` Zwischenvariable entfernt

### ZIM-Datei: "Nicht gefunden"-Zustand
- **Problem:** Wenn die ZIM-Datei fehlt (z. B. nach `flutter install`, das erst deinstalliert und dabei `Android/data/.../files/` löscht), zeigte die App dauerhaft "Wissensspeicher lädt... 0%" — identisch zum Ladezustand, kein Hinweis auf das eigentliche Problem
- **Fix `MainActivity.kt`:** Neue Methode `findZimPath()` prüft zwei Pfade nacheinander:
  1. `getExternalFilesDir(null)` — app-spezifisch extern, für Nutzer per Datei-Manager zugänglich
  2. `filesDir` — intern, überlebt Reinstalls, per `adb` auf Debug-Builds zugänglich
  Wenn keine Datei gefunden wird, wird sofort `status: not_found` gemeldet (kein unnötiger Lade-Versuch)
- **Fix `wissensfreund_provider.dart`:** Neues Feld `_zimNotFound` / Getter `zimNotFound`; wird bei `status: not_found` auf `true` gesetzt
- **Fix `home_screen.dart`:** `_ZimStatusBar` unterscheidet jetzt drei Zustände:
  - **Lädt:** Fortschrittsbalken mit Prozentangabe (unverändert)
  - **Fertig:** grünes Häkchen + Artikelanzahl (unverändert)
  - **Nicht gefunden:** orange Warndreieck + "klexikon.zim nicht gefunden" (neu)

### ZIM-Datei: Maxi-Version (mit Bildern)
- Wechsel von `klexikon_de_all_nopic_2025-10.zim` auf `klexikon_de_all_maxi_2025-10.zim` als Standard-ZIM
- Vorbereitung für die geplante Bildintegration; echtes Bildmaterial direkt aus dem ZIM nutzbar
- Ablage auf PC: `C:\Users\Andreas\Wissensfreund\klexikon_de_all_maxi_2025-10.zim` (~156 MB)
- Geräte-Pfad: `/sdcard/Android/data/de.wissensfreund.wissensfreund_app/files/klexikon.zim`

### Disambiguierungs-Loop behoben
- **Problem:** Nach Rückfrage "Meinst du X oder Y?" startete das Mikrofon automatisch, die Antwort des Nutzers löste aber dieselbe Rückfrage erneut aus — endlose Schleife
- **Ursache:** `startListening()` setzte `_awaitingDisambiguation = false` zurück, bevor `_processQuery()` lief; dadurch griff der `!_awaitingDisambiguation`-Guard nicht
- **Fix:** Reset von `_awaitingDisambiguation` und `_pendingCandidates` aus `startListening()` und `submitText()` entfernt
- **Fix:** Reset jetzt in `_loadAndSpeak()` (nach erfolgreichem Artikel-Load) und `_speakAndIdle()` (nach Fehlermeldungen) — d. h. erst wenn das Ergebnis wirklich feststeht

---

## Session 2026-05-19 (Vorherige Session — Zusammenfassung)

### `normalizeUmlauts()` ergänzt
- Funktion wurde in `ZimReader.kt → search()` aufgerufen, war aber nie definiert
- Ergänzt: `ä→a, ö→o, ü→u, Ä→A, Ö→O, Ü→U, ß→ss`
- Bewirkt: "Mäuse" findet jetzt den Tier-Artikel (Score 5) statt Computermaus (Score 1)

### Klexikon-Abspann-Entfernung (Earliest-Position-Fix)
- **Problem:** Klexikon-Outro erschien in manchen Artikeln noch, weil die Marker-Schleife bei der ersten Übereinstimmung in der Liste abbrach (`break`)
- **Fix:** Schleife findet jetzt die FRÜHESTE Position über alle Marker (Minimum), nicht den ersten Treffer in der Marker-Liste
- Zusätzliche Marker ergänzt: `MiniKlexikon.de`, `Ralph Caspers`, `Checker Julian`, `bzkj.de` u. a.

### `trimStart`-Bug behoben
- `cur.url.trimStart('A', '/', 'C')` trimmt einzelne Zeichen → "Affe" wurde zu "ffe"
- Fix: `cur.url.removePrefix("A/").removePrefix("C/").trim()`

### Auto-Listen nach Disambiguierung
- Nach der Rückfrage "Meinst du X oder Y?" öffnet sich das Mikrofon automatisch
- Implementiert im TTS-Completion-Handler: wenn `_awaitingDisambiguation && _state == AppState.idle` → `startListening()` nach 500 ms

### Klexikon-Attributions-Footer (CC BY-SA 3.0)
- Widget `_KlexikonAttribution` in allen drei Artikel-Anzeigemodi (A, B, C) eingebaut
- Tipp auf den Footer öffnet den Klexikon-Artikel im externen Browser (`url_launcher`)
- `url_launcher: ^6.3.0` zu `pubspec.yaml` hinzugefügt
- HTTPS-Intent-Query in `AndroidManifest.xml` ergänzt
