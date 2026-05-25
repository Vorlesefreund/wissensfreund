# Wissensfreund Status
<!-- updated: 2026-05-25T13:42:54Z -->

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
- **images_medium.zip**: Workflow #31 fehlgeschlagen (exit code 255, transient).
  Neuer Workflow lief bei letztem Check bei 2h 40m+ noch aktiv.
  Sobald grün: `images_medium.zip` auf R2 und "Gut"-Bildqualität downloadbar.

### Fehlende Features
- **Upgrade-Flow bei Rückfrage (Free-User)**: `canAskQuestions`-Gate vorhanden,
  aber kein Dialog wenn Free-User fragt. Wartet auf Gemini-Integration.
- **Download-Größe dynamisch**: Wird noch statisch ("~2 GB") angezeigt, nicht aus Manifest gelesen.

### Design-Ausstände
- **Plus & Premium Dialog**: Neue Designvorgaben vom User angekündigt, noch nicht geliefert.
- **Sound-Thumbnails**: Audio-Infrastruktur fertig; wartet auf Ergebnis des GH-Actions-Audio-Runs.

### Technische Schulden
- `kMonthlyQuestionLimit = 5000` und `addSessionMinutes()` vorhanden aber inaktiv
  (aktivieren wenn Gemini läuft).
- Bottom-Navigation-Bar-Abstand: Fix installiert, aber vom User noch nicht final bestätigt.
- RadioListTile groupValue/onChanged deprecated in Flutter 3.32+ (data_limit_overlay.dart) —
  kein Fehler, nur Info-Warnung; bei Gelegenheit auf RadioGroup umstellen.
