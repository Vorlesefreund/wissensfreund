# Wissensfreund Status
<!-- updated: 2026-05-26T13:03:20Z -->

## Zuletzt erledigt (Session 2026-05-26)

### Bildqualitäts-System (Freemium-Umbau)

#### Neue Stufen-Logik (300px / 600px / 1200px)
- **Free**: 300px aus ZIM — kein on-demand, kein Download nötig
- **Plus/Premium ohne lokalen Download**: 300px sofort, 1200px on-demand bei WLAN (Crossfade 300ms)
- **Plus/Premium mit lokalem Download**: 600px aus `image_library/`, 1200px on-demand bei WLAN

#### Geänderte Dateien
- `lib/config/asset_config.dart`: URL auf `images_standard.zip` (600px) umgestellt; `imageLibrarySizeBytes` → 600 MB; alte `images_medium.zip`-Referenzen entfernt
- `lib/services/hires_image_service.dart`: Komplettumbau:
  - Commons-Dateiname wird aus ZIM-Pfad extrahiert (`langde-{size}px-{original}` → `{original}`)
  - Download via `Special:FilePath/{commons_fn}?width=1200` (ein HTTP-Request statt vorher zwei)
  - LRU-Cache: max 500 MB, evict auf 400 MB wenn überschritten
  - Free-User-Gate: `canUseHighResOnDemand` — liefert sofort null
- `lib/screens/article_screen.dart`:
  - `_loadHiRes()`: früher Ausstieg für Free-User (kein Netz-Check, kein Download)
  - Upgrade-Hinweis `_UpgradeHint` im Vollbild (Free-User, nicht während Vorlesen): "Schärfere Bilder mit Wissensfreund Plus" → tippt auf Alert-Dialog
- `lib/screens/first_run_screen.dart`:
  - Image-Quality-Seite wird für Free-User übersprungen (`_goToAfterNetwork()`)
  - Neue Texte: "Ja, bessere Bilder speichern (~600 MB)" / "Nein, nur bei WLAN laden"
  - `_kRequiredBytes` → 1 GB (600 MB ZIP + Extraktions-Overhead)
- `lib/screens/home_screen.dart` — `_StorageDialog` komplett überarbeitet:
  - **Free**: "Standard (300px)" + "Mit Plus: deutlich schärfere Bilder" + Upgrade-Button
  - **Plus/Premium ohne Download**: "Gut bei WLAN (bis 1200px)" + Inline-Download mit Fortschrittsanzeige
  - **Plus/Premium mit Download**: "Offline-Bilder: Gut (600px) — X MB" + "Löschen"-Button + "Bei WLAN: 1200px"
  - 1200px-Cache-Zeile nur für Plus/Premium sichtbar

#### Satzerkennung (Zahlen-Fix)
- `_splitSentences()` (article_screen.dart + article_screen_a.dart): neue Regex erkennt `1.000`, `1.000.000`, `1,5` als eine Einheit → kein falsches Satzende bei deutschen Zahlenformaten
- `_sentenceStartOffset()` (provider): überspringe Punkt zwischen zwei Ziffern beim Rückwärts-Scan

#### GitHub Actions (Workflow-Trigger)
- `update_image_licenses.yml`: `type: string` zu `workflow_dispatch` input hinzugefügt
- GitHub hatte zum Zeitpunkt der letzten Trigger-Versuche einen Major Outage (10:57–13:xx UTC); Testlauf mit `max_articles=10` sobald GitHub wieder grün ist

### Offen / Nächste Schritte
- **Workflow-Testlauf**: `max_articles=10` starten sobald GitHub Actions wieder stabil (githubstatus.com prüfen)
- **images_standard.zip**: tatsächliche Größe nach erstem Lauf bekannt — `imageLibrarySizeBytes` ggf. anpassen
- **Gemini-Integration**: Frage-Typ-Erkennung Typ 3 (Vergleich) + Typ 5 (Fallback) noch ausstehend
- **Download-Größe dynamisch**: "~600 MB" noch statisch; nach erstem Workflow-Run aus Manifest lesen

---

## Zuletzt erledigt (Session 2026-05-25 — nacht)

### "Weiterhören" + Gemini-Platzhalter (komplett implementiert)

#### Weiterhören (Home-Screen)
- `ProfileService`: `saveLastArticle(title, charOffset)` / `getLastArticle()` / `clearLastArticle()` hinzugefügt
- `ProfileService.deleteProfile()`: löscht jetzt auch `last_article_title_{id}` + `last_article_offset_{id}`
- `WissensfreundProvider`:
  - `saveCurrentArticlePosition()` — speichert aktuellen Satzanfang-Offset
  - `clearLastArticle()` — delegiert an ProfileService
  - `resumeLastArticle(title, offset)` — ZIM-Suche → `_loadAndSpeakFrom()` → spricht "Weiter mit [Titel]!" → Resume
  - `_loadAndSpeakFrom()` — lädt Artikel, setzt `_resumeAfterHandoff=true`, spielt Intro-Phrase
  - `_loadAndSpeak()`: ruft jetzt `clearLastArticle()` bevor `_startSpeakingFrom(0)` (neuer Artikel = Weiterhören löschen)
  - TTS completion (Artikel-Ende): ruft `clearLastArticle()` auf
- `article_screen.dart`: ← Button (sprechend + idle) speichert Position vor `stopSpeaking()`
- `article_screen.dart`: "Vorlesen beenden" + "Zum Hauptmenü" rufen `clearLastArticle()` auf
- `main.dart`: Background-Pause speichert Position (`saveCurrentArticlePosition()`) vor `pauseSpeaking()`
- `home_screen.dart`:
  - `_lastArticle` State, `_loadLastArticle()`, `_onProfileChanged()` Listener
  - `_WeiterhoerenCard` Widget (grüne Karte mit ▶, Titel, Untertitel)
  - Karte erscheint nur wenn idle + kein Artikel geladen + letzter Artikel gespeichert

#### Gemini-Platzhalter (5 Frage-Typen verdrahtet)
- `_QueryType` Enum: `{ fullRead, targeted, comparison, followUp, unknown }`
- `_kCompareWords` Konstante (19 Vergleichswörter)
- `_detectQueryType()`: gibt jetzt `unknown` als Default zurück (war `fullRead`)
- `_processQuery()` komplett überarbeitet — 5 Typen:
  - Typ 1 (fullRead): wie bisher → Artikel vorlesen
  - Typ 2 (targeted): `_handleGeminiPlaceholder()` nach ZIM-Suche mit Treffer
  - Typ 3 (comparison): erkannt nach ZIM (2 Treffer ≥ kMinScore + Vergleichswort) → Platzhalter
  - Typ 4 (followUp): erkannt via `_hasInterruptedForMic` → Platzhalter, kein ZIM-Download
  - Typ 5 (unknown): kein Treffer → Eltern-Verweis; Treffer → Artikel vorlesen (wie Typ 1)
  - Typen 2/3/5 ohne Treffer: immer Eltern-Verweis (eiserne Regel)
- `_handleGeminiPlaceholder()`: Free → Upgrade-Phrase (3 Varianten); Premium → Platzhalter-Phrase (3 Varianten)

---

## Zuletzt erledigt (Session 2026-05-25 — abends)

### Onboarding-Flow (FirstRunScreen) — komplett implementiert

#### Neue Dateien
- `lib/screens/first_run_screen.dart` — 4-seitiger Willkommens-Wizard:
  - Seite 0: Welcome — Begrüßung, Beschreibung, "~3 Minuten"-Badge, Übersicht der 4 Schritte
  - Seite 1: Internet & Daten — identische Logik wie `_NetworkSettingsOnboardingDialog` (WLAN-Unlimited, Tageslimit, Monatslimit, Mobilfunk-Toggle)
  - Seite 2: Bildqualität — Standard vs. Gut (~2 GB), Speicherplatz-Prüfung, Download mit Fortschrittsanzeige
  - Seite 3: Kinderschutz — `requestOverlayPermission` flow (intro → warten → erteilt/verweigert → fertig)
  - Nach Seite 3: `onboarding_complete = true` setzen, alle Onboarding-Flags schreiben, → `ProfileCreationScreen(isFirstProfile: true)`

#### Geänderte Dateien
- `lib/main.dart`:
  - `SharedPreferences.getBool('onboarding_complete')` beim Start
  - Neues Pflichtargument `onboardingComplete` für `WissensfreundApp`
  - Routing: `!onboardingComplete` → `FirstRunScreen`, sonst bekannte Logik

#### Ablauf (wie vom User spezifiziert)
1. Erstinstallation → `FirstRunScreen` mit Fortschrittspunkten
2. Eltern richten Internet-Limits, Bildqualität und Kinderschutz ein
3. → `ProfileCreationScreen` (Name, Alter, Avatar, Sprachniveau, Fertig+Konfetti)
4. → `HomeScreen` (normaler App-Start)
5. Alle Folgestarts: `onboarding_complete = true` → direkt zum normalen Start-Screen

#### Fixes (Slider, Back-Button aus letzter Session)
- Slider-Bug in Profil-Wizard (Schritt 2 ohne sichtbaren Regler) → `FocusScope.unfocus()` in `_next()`
- Back-Button-Spinner-Loop → `PopScope(canPop: !widget.isFirstProfile)` in `ProfileCreationScreen`

---

## Zuletzt erledigt (Session 2026-05-25 — nachmittags 2)

### 100% Datenlimit-Overlay (komplett implementiert)

#### Neue Dateien
- `lib/services/data_limit_overlay_service.dart` — Singleton ChangeNotifier (show/dismiss + retry/cancel-Callbacks)
- `lib/widgets/data_limit_overlay.dart` — Vollbild-Overlay, 4 Phasen:
  - Gesperrt: "Datenlimit erreicht" + Verbrauch mit Fortschrittsbalken + Entsperren-Button
  - Entsperrt: Tageslimit / Monatslimit erhöhen
  - Anpassen: Radio-Liste (100/200/500 MB/Tag, 500 MB/1 GB/2 GB/Monat + Unbegrenzt)
  - Speichern → NetworkSettingsService + dismiss(retry: true) → automatischer Retry

#### Geänderte Dateien
- `lib/main.dart` — DataLimitOverlayService in Providers; DataLimitOverlay in _AppShell-Stack
- `lib/providers/wissensfreund_provider.dart`:
  - `pauseForDataLimit()` — pausiert Vorlesen, spricht Übergabe-Phrase, awaitable Completer
  - `resumeAfterDataLimit()` — setzt Vorlesen fort nach Retry
  - `speakDataLimitCancelled()` — "Kein Problem, wir machen weiter!" → auto-Resume
  - 80%/90%-Warnphrases zwischen TTS-Chunks eingebettet (`_deferredArticleChunk`)
  - 3 Übergabe-Varianten, 3×80%-Varianten, 3×90%-Varianten
- `lib/screens/article_screen.dart` (`_FullscreenGalleryState`):
  - `_loadHiRes()` prüft jetzt canUseNetwork() → triggert Overlay bei limit_reached
  - `_triggerDataLimitOverlay()` — awaitet Professor-Phrase, zeigt Overlay
- `lib/screens/home_screen.dart`:
  - `_UsageProgressRow` — neues Widget mit Fortschrittsbalken (grün → orange 80% → rot 100%)
  - Ersetzt einfache `_UsageRow` im Internet & Daten Dialog

#### Ablauf (wie spezifiziert)
1. Kind tippt → limit_reached erkannt
2. Professor beendet graceful, spricht Übergabe-Phrase (aus 3 Zufallsvarianten)
3. Vollbild-Overlay erscheint → "Datenlimit erreicht" + Verbrauchsstats
4. Eltern entsperren mit BiometricPrompt → Limit erhöhen → Speichern
5. Overlay schließt → unterbrochene Aktion startet automatisch neu
6. Bei Abbrechen: Professor sagt "Kein Problem" → liest weiter ab Speicherpunkt

---

## Zuletzt erledigt (Session 2026-05-25 — nachmittags)

### Multi-User-System + Bottom-Sheet-Menü (komplett)

#### Schritt 1 — SQLite Schema v6 → v7
- `profiles` Tabelle (id, name, birth_year, avatar_id, language_level, created_at, last_used_at)
- `article_history` Tabelle (profile_id FK, article_title, opened_at) — max. 200 Einträge/Profil
- `favorites` Tabelle (profile_id FK, article_title, added_at)
- Alle CRUD-Methoden in `LicenseCacheDb`

#### Schritt 2 — Profilerstellungs-Wizard (5 Schritte)
- `lib/screens/profile_creation_screen.dart`
- Schritte: Name → Geburtsjahr (Slider) → Avatar (20 Tiere) → Sprachniveau → Fertig + Konfetti
- Kein Back-Button auf Schritt 1 wenn erstes Profil

#### Schritt 3 — Profilauswahl-Screen
- `lib/screens/profile_selection_screen.dart`
- "Wer bist du heute?" mit Karten-Grid (Avatar, Name, Alter)
- "+" Karte für neues Profil
- Beim Start: kein Profil → direkt Erstellungs-Wizard; sonst → Grid

#### Schritt 4 — Bottom-Sheet-Menü neu
- Profil-Header (Avatar, Name, Alter, Sprachniveau, "Wechseln"-Button)
- Kinder-Sektion: Hauptmenü, Texteingabe, Verlauf, Favoriten (ohne Auth)
- Eltern-Sektion: gesichert mit BiometricPrompt (einmalig pro Menü-Öffnung)
  → Internet & Daten, Kinderschutz, Speicher & Qualität, Profile verwalten, Plus & Premium

#### Schritt 5 — Profilverwaltung für Eltern
- `lib/screens/profile_management_screen.dart`
- Liste aller Profile; aktives markiert
- Bearbeiten-Dialog (Avatar, Name, Alter, Sprachniveau)
- Löschen mit Bestätigungs-Dialog (nur wenn > 1 Profil)

#### `ProfileService` + `main.dart`
- `lib/services/profile_service.dart` — CRUD, setActiveProfile, Verlauf, Favoriten
- `main.dart`: ProfileService.initialize() beim Start; Route → ProfileSelectionScreen wenn kein Profil

#### Nachträglich ergänzt (vollständig verdrahtet)
- `_trackArticleListened()` in `wissensfreund_provider.dart` ruft jetzt auch
  `ProfileService.instance.recordArticleOpened(title)` auf → Verlauf füllt sich automatisch
- `_FavoriteBtn` (⭐) im Artikel-Screen-Header — prüft und togglet Favorit per Tap
  (gelber Stern wenn aktiv, Outline wenn nicht); Zustand aus DB geladen

---

## Zuletzt erledigt (Session 2026-05-25 — vormittags)

### Freemium-Modell
- `SubscriptionService` (Free / Plus / Premium) mit SharedPreferences-Cache
- `BillingService.kt` — Google Play Billing 6.2.1, Produkte: `wissensfreund_plus` (INAPP), `wissensfreund_premium` (SUBS)
- Feature-Gates: `canAskQuestions`, `canDownloadMediumQuality`, `canUseHighResOnDemand`
- `_SubscriptionDialog` im Menü mit Upgrade-Cards, Statistiken, Restore-Button
- `question_usage` + `usage_stats` Tabellen in SQLite (Schema v6)

### Menü & Kinderschutz
- Menü-Zugang durch BiometricPrompt gesichert wenn Kiosk aktiv
- Einmalige Auth für alle Menüpunkte (`parentalUnlocked`-Flag — kein zweiter Prompt)

### Onboarding-Kette (Bugfix)
- `StorageManager.initialize()` fehlte vor der Kette → `AssertionError` → Bildqualitäts- und Netzwerk-Dialog wurden nie gezeigt. Gefixt.
- `evictOldCache()` wird jetzt beim App-Start im Hintergrund aufgerufen (war toter Code)

### Bildqualitäts-Dialog
- Speicher-Prüfung via `StatFs` (neuer `getFreeStorageBytes()`-Channel in MainActivity.kt)
- Bei < 2 GB frei: Standard empfohlen, Orange-Warnung, Download-Button deaktiviert
- Fehlermeldungen jetzt sprechend: HTTP 404 → "Bildpaket noch nicht verfügbar" statt "Bitte WLAN prüfen"

---

## Offen / Nächste Schritte

### Dringend
- **images_medium.zip**: Neuer Workflow läuft (Stand 20:08 UTC):
  `prepare` ✅ 1h 14m, `download` ✅ 1h 2m, `images` ⏳ seit 7h 30m noch aktiv.
  Sobald `images`-Job grün: `images_medium.zip` auf R2 → "Gut"-Bildqualität downloadbar.

### Fehlende Features
- **Gemini-Integration**: Frage-Typ-Erkennung (5 Typen) muss vor Gemini verdrahtet werden.
  Logik dokumentiert in CLAUDE_CHAT_NOTIZEN.md (2026-05-25).
  `_detectQueryType()` vorhanden aber nicht aktiv. Typ 3 (Vergleichsfrage) und Typ 5 (Fallback) fehlen noch.
- **Upgrade-Flow bei Rückfrage (Free-User)**: `canAskQuestions`-Gate vorhanden,
  aber kein Dialog wenn Free-User fragt. Wartet auf Gemini-Integration.
- **Download-Größe dynamisch**: Wird noch statisch ("~2 GB") angezeigt, nicht aus Manifest gelesen.

### Design-Ausstände
- **Plus & Premium Dialog**: Neue Designvorgaben vom User angekündigt, noch nicht geliefert.
- **Sound-Thumbnails**: Audio-Infrastruktur fertig; wartet auf Ergebnis des GH-Actions-Audio-Runs.

### Technische Schulden
- `kMonthlyQuestionLimit = 5000` und `addSessionMinutes()` vorhanden aber inaktiv
  (aktivieren wenn Gemini läuft).
- RadioListTile groupValue/onChanged deprecated in Flutter 3.32+ (data_limit_overlay.dart) —
  kein Fehler, nur Info-Warnung; bei Gelegenheit auf RadioGroup umstellen.
