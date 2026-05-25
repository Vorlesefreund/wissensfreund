# Wissensfreund Status
<!-- updated: 2026-05-25T13:14:12Z -->

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

### Sonstiges
- `AnimatedSwitcher` Crossfade 200 ms → 300 ms
- `_StorageDialog` Endlos-Spinner gefixt (StorageManager-Init fehlte)
- CHANGES.md + STATUS.md: `<!-- updated: ... -->` Timestamp-System

---

## Offen / Nächste Schritte

### Dringend
- **images_medium.zip**: Workflow #31 fehlgeschlagen (exit code 255, transient).
  Neuer Workflow läuft gerade — images-Job bei 2h 40m+ und noch aktiv (gutes Zeichen).
  Sobald dieser Run grün wird, ist `images_medium.zip` auf R2 und "Gut"-Bildqualität downloadbar.

### Fehlende Features (aus Prompt-Checkliste)
- **100% Datenlimit-Overlay mit BiometricPrompt**: Limit-reached → aktuell nur stiller Fehler.
  Sperre + Eltern-Authentifizierung zum Entsperren fehlt noch.
- **Upgrade-Flow bei Rückfrage (Free-User)**: `canAskQuestions`-Gate vorhanden,
  aber kein Prompt / kein Dialog wenn Free-User fragt. Wartet auf Gemini-Integration.
- **Speicher-Prüfung im Onboarding**: Empfehlung basiert auf freiem Speicher — ✅ erledigt heute.
  Download-Größe wird noch statisch ("~2 GB") angezeigt, nicht aus Manifest gelesen.

### Design-Ausstände
- **Plus & Premium Dialog**: Neue Designvorgaben vom User angekündigt, noch nicht geliefert.
- **Sound-Thumbnails**: Audio-Infrastruktur fertig; wartet auf Ergebnis des GH-Actions-Runs
  (Audio-Pipeline, läuft parallel zum Images-Job heute).

### Technische Schulden
- `kMonthlyQuestionLimit = 5000` und `addSessionMinutes()` vorhanden aber inaktiv
  (aktivieren wenn Gemini läuft).
- Bottom-Navigation-Bar-Abstand: Fix installiert, aber vom User noch nicht final bestätigt.
