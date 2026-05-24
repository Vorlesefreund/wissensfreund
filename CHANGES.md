# Changelog — Wissensfreund App

---

## ✅ FERTIG — Internet-Einstellungen, Datenlimit & ZIM-Update (Stand 2026-05-24)

### Neue Services

- **`lib/services/network_settings_service.dart`** (NEU): SharedPreferences-Wrapper für WLAN/Mobilfunk-Datenlimit-Einstellungen.
  Felder: `wifiUnlimited`, `wifiDailyLimitMb`, `wifiMonthlyLimitMb`, `mobileAllowed`, `mobileDailyLimitMb`, `mobileMonthlyLimitMb`, `networkSettingsOffered`.

- **`lib/services/data_usage_service.dart`** (NEU): Tägliches/monatliches Datenverbrauch-Tracking.
  `LimitWarningLevel` Enum (warning80/warning90/limitReached).
  Schwellenwert-Check mit Tages-Deduplizierung (SharedPreferences).

- **`lib/services/network_service.dart`** (NEU): Zentraler Netzwerk-Gate für alle Downloads.
  `canUseNetwork({estimatedBytes, trackUsage})` prüft Verbindung, Mobilfunk-Erlaubnis, Datenlimits.
  `consumePendingWarning()` drains ausstehende 80/90%-Warnungen für die UI.
  `recordUsage(bytes)` bucht Verbrauch nach erfolgreichem Download.

- **`lib/services/zim_update_service.dart`** (NEU): ZIM-Update-Mechanismus.
  `checkForUpdate()` holt `zim_version.json` von R2, vergleicht mit gespeicherter Version.
  30-Tage-Überspringen per SharedPreferences.
  `downloadAndSwap()` nutzt `AssetDownloadService` mit `trackUsage: false`.
  Android-Platform-Channel `swapZim` (pending Kotlin-Implementierung).

### Geänderte Services

- **`lib/services/license_cache_db.dart`**: Schema v4 → v5, neue `data_usage`-Tabelle
  `(date, connection_type, bytes_used PRIMARY KEY)`.
  Neue Methoden: `recordDataUsage`, `getDailyUsage`, `getMonthlyUsage`, `getStoredZimVersion`.

- **`lib/services/asset_download_service.dart`**: `downloadAsset()` erhält `trackUsage: bool = true`.
  Delegiert Netzwerk-Check an `NetworkService.canUseNetwork()` statt direkt Connectivity zu prüfen.
  Bucht Verbrauch nach Erfolg via `NetworkService.recordUsage()`.
  WiFi-Lost-Check prüft jetzt `ConnectionType.none` statt `ConnectivityResult.wifi`.

- **`lib/services/hires_image_service.dart`**: WiFi-Check durch `NetworkService.canUseNetwork()` ersetzt.
  Bucht Verbrauch nach erfolgreichem HiRes-Download.

- **`lib/services/storage_manager.dart`**: Neues `zimUpdateDir` für ZIM-Download-Staging.

- **`lib/config/asset_config.dart`**: `zimVersionUrl` hinzugefügt.

### Provider

- **`lib/providers/wissensfreund_provider.dart`**: `ZimVersionInfo? pendingZimUpdate` + `clearPendingZimUpdate()`.
  `_initLicenseCache()` startet `_checkZimUpdateInBackground()` im Hintergrund.

### UI (`home_screen.dart`)

- Onboarding-Kette erweitert: nach Image-Quality-Dialog → `_checkNetworkSettings()`
  (BiometricPrompt + `_NetworkSettingsOnboardingDialog`, einmalig).
- `_onProviderChanged()` zeigt SnackBar bei 80/90%-Limit, triggert `_ZimUpdateDialog` wenn Update verfügbar.
- Neuer Menüpunkt "Internet & Daten" (Icons.wifi_rounded, immer BiometricPrompt zuerst).
- Neue Dialoge: `_NetworkSettingsOnboardingDialog`, `_InternetDataDialog`, `_ZimUpdateDialog`.
- Neue Hilfswidgets: `_SectionHeader`, `_LimitDropdown`, `_UsageRow`.

### Workflow

- **`.github/workflows/update_image_licenses.yml`**: Neuer Step `Create zim_version.json`
  (enthält Version, ZIM-URL, Dateigröße, Datum), Upload zu R2 mit `max-age=3600`.

### Offene Android-Arbeit (Kotlin)

- `wissensfreund/zim` → `swapZim({path})` Platform-Channel muss im Android-Code implementiert werden,
  damit die App nach einem ZIM-Download ohne Neustart wechseln kann.
  Derzeit wirft der Channel `MissingPluginException` → App zeigt "Neustart erforderlich".

---

## ✅ FERTIG — Bildqualität-System & On-Demand-HiRes (Stand 2026-05-24)

### Neue Services

- **`lib/services/image_library_service.dart`** (NEU): Offline-Bilderbibliothek (800px).
  `downloadLibrary(onProgress)` lädt `images_medium.zip` von R2, extrahiert per `archive_io`-Streaming.
  `getImage(filename)`, `hasImage(filename)`, `totalSizeBytes`, `clear()`.

- **`lib/services/hires_image_service.dart`** (NEU): On-Demand-HiRes (1600px).
  Singleton, ein Download gleichzeitig (`_loading`-Flag). WiFi-only.
  Wikimedia REST API: `https://api.wikimedia.org/core/v1/commons/file/File:[filename]`.
  `preferred.url?width=1600`, max 3 MB, 8 s Timeout. SQLite-Index (LRU).
  Neu: `cacheSizeBytes()`, `clearCache()` für Storage-Dialog.

- **`lib/services/license_cache_db.dart`**: Schema auf v4 — `image_cache_index`-Tabelle
  für HiRes-LRU-Cache-Tracking. Neue Methoden: `upsertImageCache`, `touchImageCache`,
  `imageCacheTotalBytes`, `clearImageCacheIndex`.

- **`lib/services/storage_manager.dart`**: `image_library/` + `image_cache/` (500 MB LRU, 30 d).

### Provider

- **`lib/providers/wissensfreund_provider.dart`**: `getImageBytes()` prüft jetzt zuerst
  `ImageLibraryService.instance.getImage(filename)`, dann ZIM-Fallback.

### Vollbild-Galerie (`article_screen.dart`)

- `_FullscreenGalleryState` lädt beim Öffnen + bei jedem Wischen das HiRes-Bild via
  `HiResImageService.instance.getHiResImage()` (WiFi-only, non-blocking).
- HiRes-Bild blendet sich mit 300ms-Crossfade (`AnimatedSwitcher`) über das Basisbild ein.
- Nur ein Download gleichzeitig; fehlendes WiFi / Fehler → kein Overlay, Basisqualität bleibt.

### Onboarding & Settings (`home_screen.dart`)

- Nach Kinderschutz-Onboarding: `_ImageQualityDialog` (einmalig, SharedPreferences-Flag).
  Wahl zwischen Standard (ZIM-Bilder) und Gut (~2 GB Offline-Bibliothek).
  Bei Download: Live-Fortschrittsanzeige + ETA.
- Neuer Menüpunkt "Speicher & Qualität": `_StorageDialog` zeigt Bibliotheks- und
  HiRes-Cache-Größe, ermöglicht gezieltes Löschen und nachträglichen Bibliotheks-Download.

### Workflow & Pipeline

- **`scripts/download_images.py`** (NEU): Inkrementeller 800px-Download von Wikimedia Commons.
  - Liest `media_licenses.json` für erlaubte Bilder
  - Lädt `images_medium_manifest.json` von R2 (JSON-Tracking welche Bilder bereits gecacht sind)
  - Batched-API-Query für Thumbnail-URLs (50er-Batches, 1,5 s Pause)
  - Lädt nur neue/fehlende Bilder herunter (max 3 MB/Bild)
  - Holt vorhandenes `images_medium.zip` von R2, fügt neue Bilder hinzu, packt neu (ZIP_STORED)
  - Max 2 GB gesamt; Rate-Limit-Detection mit Abort-Signal
  - Schreibt aktualisiertes Manifest

- **`.github/workflows/update_image_licenses.yml`**: Neuer `images`-Job (parallel zu `download`):
  - `needs: prepare` — startet gleichzeitig mit `download`-Job nach prepare
  - Lädt `media_licenses.json` per Artifact von prepare
  - Wartet 3600 s (gleicher Rate-Limit-Reset wie `download`-Job)
  - Führt `download_images.py` aus
  - Lädt `images_medium.zip` + `images_medium_manifest.json` auf R2 hoch
  - `MAX_IMAGES` = `max_articles` aus Workflow-Input (Testmodus)

---

## ✅ FERTIG — Cloudflare R2 Asset-Infrastruktur (Stand 2026-05-24)

Alle Asset-Downloads von GitHub Release Assets auf Cloudflare R2 umgestellt.

### Was gebaut wurde

- **`lib/config/asset_config.dart`**: Zentrale R2-URL-Konfiguration
- **`lib/services/asset_download_service.dart`**: WiFi-only, Streaming to disk, Retry ×3 Exponential Backoff, ETA-Berechnung (5s Rolling Window)
- **`lib/services/storage_manager.dart`**: `image_library/` + `image_cache/` (500 MB LRU, 30-Tage-TTL), External Storage bevorzugt
- **`WikimediaLicenseChecker`**: R2-URL + AssetDownloadService
- **`AudioPackageService`**: R2-URLs + Streaming-ZIP-Extraktion via `archive_io`
- **Workflow**: R2-Upload für alle 3 Assets (aws s3 cp, EU-Endpoint)
- **Manifest**: `ACCESS_NETWORK_STATE` für `connectivity_plus`

### R2 Bucket

- Bucket: `wissensfreund-assets` (EU, Public Access aktiv)
- Public URL: `https://pub-07f0107be14b48fd8652e5318441c7c2.r2.dev`
- GitHub Secrets gesetzt: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY`, `CLOUDFLARE_R2_BUCKET_NAME`

### Testlauf 26362328051 — alles grün

- `media_licenses.json`: ✅ 909 KB auf R2 abrufbar
- `audio_index.json`: ✅ auf R2 (Testlauf leer, wird am 1. Juni befüllt)
- `wissensfreund_audio.zip`: ✅ auf R2 (Testlauf leer, wird am 1. Juni befüllt)

---

## ✅ FERTIG — Workflow: Zwei-Job-Split + Node.js 24 (Stand 2026-05-24)

### Zwei-Job-Workflow (fece876, c3ce4f4)

Workflow aufgeteilt um Wikimedia-Rate-Limit dauerhaft zu umgehen:

- **Job `prepare`** (~1,5h): ZIM → generate_license_json → extract_article_audio →
  find_wikipedia_audio → `media_licenses.json` publizieren → `wikipedia_audio_refs.json`
  als GitHub-Actions-Artifact hochladen
- **Job `download`** (startet nach `prepare`): Artifact herunterladen → **3600 s warten**
  (Rate-Limit-Reset) → download_audio.py → Audio-Package publizieren

`download_audio.py`: 300-s-Sleep entfernt (jetzt im Workflow gesteuert).

### Node.js 24 (c3ce4f4)

`actions/checkout@v4 → v5` und `actions/setup-python@v5 → v6` in beiden Jobs aktualisiert.
Verhindert Fehler ab dem erzwungenen Wechsel auf Node.js 24 (2. Juni 2026).

### Nächste Audio-Dateien

373 lizenzierte Audio-Dateien (259 Artikel) werden beim **Cron-Lauf am 1. Juni**
automatisch heruntergeladen. Sound-Thumbnails in der App warten auf diese Daten.

---

## ✅ FERTIG — Voll-Produktionslauf (alle ~3.500 Artikel) (Stand 2026-05-23)

Run 26330677982 erfolgreich in **1h28m** abgeschlossen.

### Ergebnisse

- **find_wikipedia_audio.py**: 373 erlaubte Audio-Dateien in 259 Artikeln gefunden
- **download_audio.py**: 368 eindeutige Dateien geprüft — alle 368/368 lizenziert (CC0/BY/BY-SA)
  - Downloads: 0 Dateien (Rate-Limit von Wikimedia aktiv nach API-intensiven Schritten)
  - Fast-fail nach erster persistenter 429 — kein Timeout mehr
- **media_licenses.json**: Vollständig (alle ~3.500 Artikel) publiziert ✓
- **audio_index.json + wissensfreund_audio.zip**: Publiziert, aber leer (0 Dateien wegen Rate-Limit)

### Releases

- https://github.com/Vorlesefreund/wissensfreund/releases/tag/image-licenses
- https://github.com/Vorlesefreund/wissensfreund/releases/tag/wissensfreund-audio

### Bekannte Einschränkung: Audio-Downloads

Das Wikimedia-Rate-Limit wird durch `generate_license_json.py` + `find_wikipedia_audio.py`
erschöpft. `download_audio.py` erhält auf den ersten Versuch sofort 429. Die Audio-Dateien
werden erst beim nächsten monatlichen Cron-Run (1. Juni) heruntergeladen, wenn das
Rate-Limit-Fenster frisch ist.

**Langfristige Lösung:** `download_audio.py` als separaten Workflow-Job mit `needs:` und
mindestens 1h Pause nach den API-intensiven Schritten ausführen.

---

## ✅ FERTIG — GitHub Actions: Audio-Pipeline Publish-Fix (Stand 2026-05-23)

Drei Bugs behoben, Testlauf 26330317351 erfolgreich in 11m27s:

1. **`download_audio.py`** (f221b17): Fast-fail bei anhaltendem 429 — bricht Download-Schleife
   sofort ab statt 60 s × N-Dateien zu warten (verhindert 6h-Timeout)
2. **Workflow Publish** (33501a8): `softprops/action-gh-release@v2` durch `gh release create`
   ersetzt — funktioniert zuverlässig bei `workflow_dispatch`-Triggern
3. **gh CLI Syntax** (d4362ee): Tag ist Positions-Argument, nicht `--tag`-Flag; Dateien ans Ende

---

## ⚠️ PROBLEM — GH Actions Run 26315426127: Download-Timeout (Stand 2026-05-23)

### Was passierte

Der Produktionslauf (Nacht 22./23. Mai) ist nach ~5h noch nicht fertig und droht am
6-Stunden-Timeout von GitHub zu scheitern. Ursache: `download_audio.py` wartet bei jedem
429-Rate-Limit-Fehler 60 Sekunden und versucht es dann erneut. Da das Rate-Limit-Fenster
von Wikimedia deutlich länger als 5 Minuten ist (der `time.sleep(300)` reicht nicht aus),
erhalten ALLE Dateien einen 429 — und das Script schläft 60 s × N-Dateien lang.

### Fix (bereits commitet)

`scripts/download_audio.py`: Beim zweiten 429 pro Datei nicht mehr `continue` (nächste Datei),
sondern `break` (komplette Download-Schleife abbrechen). Begründung: Wenn eine Datei nach 60 s
immer noch 429 liefert, liefern alle anderen Dateien das auch — weitermachen ist sinnlos.

**Vorher:** N Dateien × 60 s Wartezeit = mehrere Stunden Timeout-Risiko
**Nachher:** 1 Datei × 60 s Wartezeit → break → Download-Schritt fertig in ~10 min

### Nächste Schritte (nach Aufwachen)

1. Prüfen ob Run 26315426127 erfolgreich abgeschlossen oder getimeout ist
2. Falls getimeout: neuen Run manuell triggern (der neue Fix greift sofort)
3. Falls erfolgreich mit 0 Downloads: ebenfalls neuen Run für Audios nötig
4. Langfristig: `download_audio.py` als separaten Workflow-Job mit 1h Pause nach
   den API-intensiven Schritten ausführen, damit das Rate-Limit garantiert abläuft

---

## ✅ FERTIG — GitHub Actions: Wikipedia-Audio-Pipeline (Stand 2026-05-22)

### Feature

Der bestehende "Update Media Assets"-Workflow wurde um eine Wikipedia-Audio-Suche erweitert.
Für jeden der ~3.500 Klexikon-Artikel wird die deutsche Wikipedia-API abgefragt, um passende
Audio-Dateien (Tierlaute, Musik, Naturgeräusche, Aussprachen) zu finden.

### Neue Datei: `scripts/find_wikipedia_audio.py`

**Pipeline (5 Schritte):**

1. **Artikel-Titel aus ZIM lesen** — nutzt nur den URL-Pointer-Table (kein Cluster-Dekomprimieren),
   daher schnell (~1 s für alle 3.500 Artikel)

2. **Wikipedia-API abfragen** — pro Artikel:
   `https://de.wikipedia.org/w/api.php?action=query&titles={title}&prop=images&imlimit=50&format=json`
   - Filtert auf Audio-Formate: `.ogg`, `.oga`, `.mp3`, `.opus`, `.wav`, `.flac`
   - Schließt aus: Dateinamen die `"gesprochen"` oder `"spoken"` enthalten
   - Rate-Limiting: 0,5 s zwischen Anfragen
   - User-Agent: `Wissensfreund/1.0`
   - Bei Fehler: überspringen, weiter mit nächstem Artikel

3. **Wikimedia Commons Lizenzprüfung** — gebatcht (50 Dateien pro Anfrage):
   - Nur CC0, CC BY, CC BY-SA erlaubt
   - Audio OHNE Commons-Eintrag wird blockiert (kein implizites Vertrauen wie bei Bildern,
     wo Klexikon-Kuration als Vertrauensbeweis gilt)

4. **`media_licenses.json` aktualisieren** — audio-Sektion wird erweitert:
   ```json
   {
     "filename": "Elephas_maximus_call.ogg",
     "allowed": true,
     "license": "CC-BY-SA-4.0",
     "author": "...",
     "license_url": "...",
     "caption": "",
     "article": "Elefant"
   }
   ```
   Neues Feld `"article"` gibt an, in welchem Klexikon-Artikel die Datei gefunden wurde.

5. **`wikipedia_audio_refs.json` schreiben** — nur erlaubte Dateien, im gleichen Format wie
   `article_audio_refs.json`, als Input für `download_audio.py`

**Umgebungsvariablen:**
- `ZIM_FILE` — Pfad zur ZIM-Datei
- `ZIM_VERSION` — Versions-String für media_licenses.json
- `MAX_ARTICLES` — Test-Modus: nur die ersten N Artikel (0 = alle)
- `LICENSES_FILE` — Pfad zu media_licenses.json (Standard: media_licenses.json)

### Workflow-Änderungen (`.github/workflows/update_image_licenses.yml`)

- **Neuer Schritt 2b** "Find Wikipedia audio files" — läuft nach `generate_license_json.py`
  und `extract_article_audio.py`, vor dem Download-Schritt
- **Download-Schritt** bekommt `REFS_FILE: wikipedia_audio_refs.json` — damit liest
  `download_audio.py` die Wikipedia-Ergebnisse statt der (leeren) ZIM-internen Refs
- Test-Modus (`max_articles != '0'`) gilt für alle drei Audio-Schritte

### Nachträgliche Korrektur: Englisch-Wikipedia-Fallback

Analyse ergab: `action=query&prop=images` funktioniert korrekt (Amsel: beide OGGs gefunden).
Das Problem war inhaltlich: **de.Wikipedia hat im Beethoven-Artikel keine Audiodateien**,
en.Wikipedia dagegen schon (Namensaussprache + 2 Klaviersonaten-OGGs).

Lösung: `query_wikipedia_images()` prüft jetzt zuerst de.Wikipedia, fällt bei leerem
Ergebnis auf en.Wikipedia zurück (+ 0,5 s Extra-Delay). Logging: `(EN-Fallback für 'X')`.

---

### Abweichungen vom Plan

- **`article`-Feld in `media_licenses.json`**: Die Spezifikation zeigt die `media_licenses.json`
  audio-Sektion als flaches Dict (filename als Key). Das neue Feld `"article"` gibt den
  Klexikon-Artikel an, in dem die Datei gefunden wurde. Wenn dieselbe Datei in mehreren
  Artikeln vorkommt, gewinnt der letzte Treffer — für den MVP akzeptabel.
- **Zweifache Commons-Abfrage**: `find_wikipedia_audio.py` prüft Lizenzen (extmetadata),
  `download_audio.py` fragt nochmals (extmetadata|url) für die Download-URL. Die Redundanz
  ist bewusst, um `download_audio.py` unverändert zu lassen.

---

## ✅ FERTIG — Professor-Antwort-Katalog + Ruhemodus (Stand 2026-05-22)

### Feature

**SQLite-Katalog (~200 Sätze):** Alle Professor-Sprachausgaben kommen jetzt aus einem
SQLite-Datenbank-Katalog (`professor_responses.db`) statt aus fest verdrahteten Strings.
Kein Satz wird zweimal in Folge verwendet (`zuletzt_verwendet`-Zeitstempel).

**8 Kataloge mit Eskalationslogik:**
- `k1` — nicht verstanden (2 Varianten)
- `k2` — kein Artikel gefunden (3 Varianten)
- `k3_s1/s2/s3` — Eskalation bei wiederholten Fehlern (1./2./3.+ Folgeversuch)
- `k4` — dieselbe Frage wie zuvor, anderer Hinweis
- `k5_s1/s2/s3` — technische Fehler (STT/TTS PlatformException)
- `k6_s1/s2/s3` — Pause-Prompts (nach 30s, 60s, 90s Stille)
- `k6_wake` — Aufwach-Begrüßung aus dem Ruhemodus
- `k7` / `k8` — Reaktion auf Dankeschön / Tschüss-Keywords

**Zähler und Resets:**
- `_misserfolgZaehler` — zählt aufeinanderfolgende Misserfolge (STT leer + kein Artikel);
  treibt k1/k2/k3-Eskalation; Reset bei erfolgreichem Artikel-Fund
- `_technischZaehler` — zählt PlatformExceptions; treibt k5-Eskalation
- `_lastFailedQuery` — erkennt Wiederholung derselben Frage → k4 statt k2
- Alle Zähler + Timer werden bei Texteingabe (`submitText`) und Keywords zurückgesetzt

**Pause-Timer-Kette:**
- 30 s Stille → k6_s1 vorlesen → TTS-Ende → 60 s → k6_s2 → TTS-Ende → 90 s → k6_s3 → Ruhemodus
- Timer-Kette wird durch jede Nutzer-Interaktion (Mikrofon, Text, Artikelstart) abgebrochen

**Ruhemodus (`_isRestMode`):**
- Professor-Charakter atmet sanft (Scale-Animation 1.0→1.04, 3 s, reverse)
- Transparenz 65%, "Tippe mich an"-Badge (grünes Pill) erscheint unterhalb
- Mikrofon-Button ausgeblendet — nur Menü-Icon sichtbar
- Tippen auf Professor → `wakeFromRest()` → k6_wake + Zähler-Reset

**Keyword-Erkennung (STT-Ergebnis):**
- Dankeschön-Keywords (`danke`, `toll`, `super`, `klasse`, `prima`, `cool`, `schön`, `gefällt mir`, `du bist`) → k7
- Abschied-Keywords (`tschüss`, `auf wiedersehen`, `bye`, `ich muss gehen`, `ich gehe jetzt`, `bis später`) → k8

### Neue Datei

**`lib/services/professor_response_service.dart`** — Singleton mit:
- `initialize()` — Completer-Pattern, safe für mehrfaches Aufrufen
- `_onCreate()` — Tabelle erstellen + Batch-Insert aller ~200 Einträge
- `getResponse(katalogId)` — zufällig, aber vermeidet zuletzt verwendeten Satz

### Geänderte Dateien

- `lib/providers/wissensfreund_provider.dart` — Zähler, Timer-Kette, Ruhemodus-Logik,
  `_catalogOrFallback()`, `_isThankKeyword()`, `_isGoodbyeKeyword()`, `_handleKeyword()`,
  `_checkStartIdleTimer()`, `_cancelIdleTimers()`, `_fireK6S1/S2/S3()`, `_enterRestMode()`,
  `wakeFromRest()`; `_handleNoSpeech()` zu `Future<void>` konvertiert
- `lib/screens/home_screen.dart` — `SingleTickerProviderStateMixin`, Atem-Animation
  (`AnimationController` 3 s repeat-reverse), Ruhemodus-Zweig im Professor-Bereich,
  `_RestModeBadge`-Widget, Mic-Button ausblenden im Ruhemodus

---

## ✅ FERTIG — Immersive Mode + 3-Button-Layout im Artikel-Screen (Stand 2026-05-22)

### Feature

**Immersive Mode:** Der Artikel-Screen (`ArticleScreen`) und das Vollbild-Galerie-Screen
(`_FullscreenGallery`) aktivieren jetzt Android's Immersive-Sticky-Modus beim Öffnen
(`SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky)`) und stellen den
Normalzustand beim Verlassen wieder her (`SystemUiMode.edgeToEdge`).

**Neues Button-Layout während des Vorlesens:**

Während der Professor liest (`speaking`), pausiert (`isPaused`) oder einer Folgefrage lauscht
(`listening`), erscheinen drei Buttons im unteren Bereich links des Professors:

| [←] Zurück | [🎤] Mikrofon | [⏸/▶] Pause/Play |
|---|---|---|
| `stopSpeaking()` + `Navigator.pop` | `interruptAndStartListening()` | `pauseSpeaking()` / `resumeSpeaking()` |

Im Leerlauf (`idle`) bleibt der einzelne Zurück-Pfeil in der Mitte (bisheriges Verhalten).

**Mikrofon-Interrupt-Logik (`interruptAndStartListening()`):**

- Artikel-Text, Titel, Pfad und Leseposition werden gespeichert
- Professor pausiert, STT startet auf dem Artikel-Screen
- Nach der Antwort: Artikel wird wiederhergestellt, `_isPaused = true`
- "Soll ich weiterlesen?"-Prompt erscheint automatisch nach 5 s
- Wenn eine neue Frage zu einem anderen Thema gestellt wird (`_loadAndSpeak` feuert):
  gespeicherter Artikel wird verworfen — kein unerwartetes Wiederherstellen

### Geänderte Dateien

- `lib/screens/article_screen.dart` — `ArticleScreen` zu `StatefulWidget`, `_ArticleControls`
  (neu), Immersive Mode in `_FullscreenGalleryState`
- `lib/providers/wissensfreund_provider.dart` — `interruptAndStartListening()` (neu),
  TTS-Completion-Handler: Artikel-Restore-Zweig, `_loadAndSpeak`: Flag löschen

---

## ✅ FERTIG — Modus-C: Bild oberhalb von Thumbnails/Professor, Swipe, 🔊-Button (Stand 2026-05-22)

### Feature

Modus C (Nur-Bild-Modus) wurde komplett überarbeitet:

- **Bild endet oberhalb des Professors:** `Positioned(bottom: imageClearance)` mit
  `imageClearance = _kProfH + _kProfBottom = 224px` — deckt weder Professor (224px) noch
  Thumbnails (180px) ab.
- **Hintergrund:** `ColoredBox(Color(0xFF112D1F))` füllt den Bereich unterhalb des Bildes.
- **Gradient an der Bildunterkante** für weiches Ausblenden.
- **Wischen:** `GestureDetector(onHorizontalDragEnd)` navigiert zum nächsten/vorherigen Bild;
  sucht den korrekten `mediaItems`-Index (überspringt Audio-Elemente).
- **🔊-Button:** erscheint rechts an der Bildunterkante wenn eine Caption vorhanden ist;
  Tap → `provider.interruptForCaption(caption)`.

### Geänderte Datei

- `lib/screens/article_screen.dart` — `_ModeCContent` komplett neu

---

## ✅ FERTIG — Bugfix: Bildtexte fehlen (Galerie + Fallback-Suche) (Stand 2026-05-22)

### Ursache

Bildtexte (Captions) fehlten in zwei Szenarien:
1. **Galerie-Bilder:** `findNearbyCaption()` kannte `<div class="gallerytext">` nicht — nur
   `thumbcaption` und `figcaption` waren implementiert. Galerie-Bilder haben deshalb nie einen Bildtext bekommen.
2. **Edge-Cases bei `thumbcaption`:** Das Suchfenster war nur 1200 Zeichen breit; außerdem
   fehlte ein Fallback-Pfad für Fälle wo die Caption erst nach dem `thumbinner`-Block gefunden wird.

### Fix (`ZimReader.kt`)

- `captionFromWindow()` als lokale Hilfsfunktion extrahiert (sucht `figcaption`, `thumbcaption`, `gallerytext`)
- Suchfenster von 1200 auf 3000 Zeichen erweitert
- Neuer Rückwärts-Fallback: `findEnclosingBlock()` findet das nächste `thumbinner`/`gallerybox`/`<figure>`
  vor dem `<img>` und restartet die Suche von dort — fängt komplexe Schachtelungen ab
- `cleanHtml()` um deutsche HTML-Entities erweitert (`&auml;` → ä, `&szlig;` → ß usw.)

### Neues Skript: `scripts/dump_article_html.py`

Diagnostik-Skript: öffnet ZIM-Datei, sucht Artikel nach Keyword, druckt HTML-Kontext um alle
`<img>`-Tags — so ist das Kaptions-Suchmuster leicht zu überprüfen.

Verwendung: `ZIM_FILE=klexikon.zim ARTICLE=Beethoven python scripts/dump_article_html.py`

Im GH-Actions-Workflow (bei Test-Runs mit `max_articles != 0`) läuft dieser Schritt automatisch.

---

## ✅ FERTIG — Bugfix: Zu wenige Bilder nach thumbimage-Filter (Stand 2026-05-22)

### Ursache

Der `thumbimage`-Klassen-Filter aus dem K-Logo-Fix war zu aggressiv:
`class="thumbimage"` kommt nur auf Floating-Thumbnails vor, nicht auf
Infobox-Bildern, Galerie-Bildern usw. — dadurch fielen ~80% der Artikel-Bilder weg.

Außerdem: `extractImageRefsFromHtml()` durchsuchte das volle HTML-Dokument
inklusive Navigation/Header — daher war das K-Logo überhaupt sichtbar.

### Fix (`ZimReader.kt`)

- Neue Methode `extractArticleBody(html)` trimmt das HTML auf den Artikel-Body
  (gleiche Start-Marker wie `preClean()`: `mw-content-text`, `mw-parser-output`,
  `bodyContent`, `<body`).
- `extractImageRefsFromHtml()` sucht jetzt nur im Artikel-Body — K-Logo im Header
  wird damit automatisch ausgeschlossen, ohne jeglichen Klassen-Filter.
- `thumbimage`-Filter und Debug-Logs entfernt.

---

## ✅ FERTIG — App: Audio-Paket laden und abspielen (Stand 2026-05-22)

### Neue Datei

**`lib/services/audio_package_service.dart`** — `AudioPackageService` (Singleton):
- `initialize()` — lädt lokalen Index sofort, startet Update-Check im Hintergrund
- `getAudioRefs(articleTitle)` — gibt Refs zurück, nur für Dateien die lokal vorhanden sind
- Download-Flow: `audio_index.json` holen (klein) → Versionscheck → bei Änderung
  `wissensfreund_audio.zip` laden → entpacken nach `<AppDocuments>/audio/` → Index neu laden
- Graceful Degradation: bei Netzwerkfehler läuft App mit bereits gecachten Dateien weiter

### Änderungen in bestehenden Dateien

**`pubspec.yaml`:**
- `archive: ^3.4.0` — ZIP-Entpackung (ZipDecoder)
- `path_provider: ^2.1.0` — App-Verzeichnis ermitteln (war bereits transitive dep)

**`wissensfreund_provider.dart`:**
- `ArticleMediaItem` — neues Feld `localPath: String?` für lokale Audio-Dateien
- `loadMedia()` — lädt nur noch Bilder aus ZIM; Audio kommt aus `AudioPackageService`
- `_playAudioItem()` — bei `localPath != null`: `_audioPlayer.setFilePath()` statt Bytes;
  Fallback auf ZIM-Bytes weiterhin vorhanden (greift bei Klexikon-ZIM nie)
- `_initZim()` — ruft `AudioPackageService.instance.initialize()` wenn ZIM bereit ist

**`scripts/download_audio.py`:**
- `position` wird jetzt in `audio_index.json` gespeichert (für Thumbnail-Reihenfolge)

### Ablauf beim ersten App-Start
1. ZIM-Ladefortschritt 0..100% (wie bisher)
2. ZIM bereit → AudioPackageService.initialize() startet im Hintergrund
3. Sofort: lokaler Index geladen (leer beim ersten Mal)
4. Hintergrund: audio_index.json von GitHub holen → neu? → ZIP laden → entpacken
5. Nächster Artikel-Abruf: Sound-Thumbnails erscheinen für Artikel mit Audio

---

## ✅ FERTIG — GitHub Actions: Audio-Pipeline (Stand 2026-05-21)

### Neue Dateien

**`scripts/extract_article_audio.py`** (neu):
- Öffnet ZIM mit `libzim` Python-Bindings
- Scannt alle Artikel-HTML-Einträge nach `wpDestFile=`-Links (Wikimedia-Audio)
- Extrahiert Dateinamen (ogg/mp3/wav) + Caption (Text vor dem Link, bis 500 Zeichen zurück)
- Schreibt `article_audio_refs.json` (Artikel → Liste von {filename, caption, position})
- Testmodus: `MAX_ARTICLES=10` begrenzt den Scan (z.B. für Probedurchlauf mit Beethoven)

**`scripts/download_audio.py`** (neu):
- Liest `article_audio_refs.json`
- Fragt Wikimedia Commons API für Lizenz + Download-URL (`iiprop=extmetadata|url`)
- Gleiche Lizenzregeln wie Bilder: CC0, CC BY, CC BY-SA — alle anderen gesperrt
- Lädt erlaubte Dateien herunter: max 5 MB pro Datei, max 50 MB gesamt
- Schreibt `audio_index.json` (Artikel → [{filename, caption, local_path}])
- Packt alle Dateien als `wissensfreund_audio.zip` (intern: `audio/DATEINAME`)

### Workflow-Update: `update_image_licenses.yml`

Umbenannt in "Update Media Assets". Neue Eingabe `max_articles` für Testläufe.

Neue Schritte nach dem bestehenden `generate_license_json.py`:
1. `extract_article_audio.py` — Audio-Links aus HTML extrahieren
2. `download_audio.py` — Lizenzcheck + Download + ZIP erstellen
3. Release-Asset: `wissensfreund_audio.zip` + `audio_index.json` unter Tag `wissensfreund-audio`

### Bekannte Einschränkungen / Abweichungen vom Plan

- **Klexikon-ZIM hat KEINE eingebetteten Audio-Dateien.** Audio auf klexikon.zum.de sind
  Wikimedia-Links, die per JavaScript nachgeladen werden — nicht im ZIM-Archiv enthalten.
  Die `generate_license_json.py` Audio-Sektion bleibt daher leer (korrekt, da keine ZIM-Einträge).
- **`extract_article_audio.py` findet die Wikimedia-Links** aus dem Artikel-HTML direkt
  (wpDestFile= Muster) — das ist der richtige Ansatz für diesen Inhalt.
- **App-Seite (Schritt 5)** — Download + Entpacken + SQLite-Cache + getAudioRefs() —
  ist noch nicht implementiert. Folgt in nächster Session.

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

**Hinweis:** Die Klexikon-ZIM enthält **keine Audiodateien** — Audio auf klexikon.zum.de wird
dynamisch aus Wikimedia via JavaScript nachgeladen und ist nicht im Offline-Archiv enthalten.
Die Sound-Thumbnail-Infrastruktur ist fertig und wartet auf ein ZIM mit Audio-Inhalten.

---

## ✅ FERTIG — Bugfix: Klexikon-Logo als Thumbnail (Stand 2026-05-21)

### Ursache

Das Klexikon-K-Logo (`Klexikon_K_yellow.png`) erschien als zweites Thumbnail in der Leiste,
weil `extractImageRefsFromHtml()` alle `<img>`-Tags erfasste — auch Logos und Navigationsgrafiken.

### Fix (`ZimReader.kt`)

In `extractImageRefsFromHtml()`: Bilder ohne `class="thumbimage"` werden übersprungen.
Klexikon setzt `thumbimage` ausschließlich auf redaktionellen Artikelbildern, nie auf Logos/Icons.

```kotlin
if (!match.value.contains("thumbimage", ignoreCase = true)) continue
```

---

## ✅ FERTIG — Bugfix: Fehlende Thumbnails (URL-Doppelkodierung) (Stand 2026-05-21)

### Ursache

Bilder in der Thumbnail-Leiste fehlten, wenn ihre Dateinamen Sonderzeichen enthielten.

**Logcat-Befund:**
```
getImageBytes: '_assets_/.../Wien%252C_...jpg'  → not found
```
Das HTML im ZIM kodiert Sonderzeichen doppelt: `%252C` (im HTML) steht für `%2C` in der ZIM-URL-Tabelle.
Auch `%C3%A9` (UTF-8 für `é`) kommt im HTML vor, die ZIM-URL-Tabelle speichert es als `é` (Literal).

### Fix (`ZimReader.kt`)

- `findByFilename(filename)` — neue Hilfsmethode, sucht in allen Namespaces (C/, I/, -/I/, -/, A/)
- `urlDecodeOnce(filename)` — neue Hilfsmethode: URL-dekodiert den Dateinamen einmal (`%25XX` → `%XX`, `%C3%A9` → `é`); schützt `+` vor fälschlicher Dekodierung als Leerzeichen; gibt `null` zurück wenn keine Änderung
- `getImageBytes()`: probiert jetzt as-is (`findByFilename(filename)`), dann einmal-dekodiert (`findByFilename(urlDecodeOnce(filename))`)
- `getAudioBytes()`: identische Logik
- Bereits funktionierende Bilder (ASCII-Dateinamen ohne Sonderzeichen) unverändert — as-is-Suche findet sie auf dem ersten Versuch

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
