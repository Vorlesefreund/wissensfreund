# Changelog — Wissensfreund App

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
