# Stufen-Umbau: 3 Lesestufen → 2 Inhaltstypen

<!-- erstellt: 2026-07-18 · Status: PLAN, PO-Grundmodell bestätigt, Umsetzung offen -->

Planungsdokument für die Umstellung von drei Lesestufen (S1/S2/S3) auf zwei
Inhaltstypen bei dreistufiger Profil-Auswahl. Grundmodell vom PO bestätigt;
dieses Dokument hält Zielbild, betroffene Stellen und Reihenfolge fest, bevor
Code geändert wird.

## 1. Zielmodell (bestätigt)

**Profil-Auswahl bleibt dreistufig** — sie steuert die Lesemodi:

| Profil (`ageLevel`) | Alter | Inhaltstyp | Lesemodi |
|---|---|---|---|
| 1 | 4–6 | **Hörspiel** | B + C |
| 2 | 7–9 | **Hörspiel** (dieselbe Datei wie 4–6) | A + B + C |
| 3 | 10–12 | **Erzählertext** (= altes S3, unverändert) | A + C |

**Zwei Inhaltstypen, nicht drei:**
- **Hörspiel (4–9):** neu. Ersetzt altes S1 (war zu schwach) + S2 (passte nicht
  für 4–6). Ein Artefakt, das 4–6 UND 7–9 hören. Rahmende Geschichte mit den
  Story-Cast-Figuren.
- **Erzählertext (10–12):** das bisherige S3, bleibt inhaltlich wie es ist.

**Wichtige Eigenschaft:** Das Hörspiel ist EIN Artefakt für zwei Profil-Bänder.
4–6 und 7–9 bekommen denselben Inhalt, aber unterschiedliche Lesemodi (UI-Ebene,
unabhängig vom Inhalt). Alle heute vorhandenen Artikel sind Klexikon-Reste und
werden verworfen → **Neugenerierung von Grund auf**, freie Neunummerierung
(keine Kollision mit Bestand).

## 2. Nummerierung & Benennung (ENTSCHIEDEN 2026-07-18)

**ID nach Inhaltstyp** (PO-Entscheidung), nicht mehr `{slug}_l{n}`:

- `{slug}_hoerspiel`
- `{slug}_erzaehltext`

**Mapping Profil → Inhalt** (eine Funktion, ersetzt `articleIdFor`):

```
ageLevel 1 (4–6)  → {slug}_hoerspiel
ageLevel 2 (7–9)  → {slug}_hoerspiel   (dieselbe Datei)
ageLevel 3 (10–12) → {slug}_erzaehltext
```

Begründung: Selbsterklärend, keine Doppeldeutigkeit. Die numerische Variante
(`_l1` = Hörspiel, für Profil 1 UND 2) war genau die Verwechslungsquelle, die
dieses Projekt schon zweimal gekostet hat. Mehr App-Umbau (`levelFromId` →
`contentTypeFromId`), aber die App-Schicht wird ohnehin angefasst.

Profil behält `ageLevel` 1/2/3 (dreistufige Auswahl). Die drei sichtbaren
Stufen-Namen (heute „Kleine Forscher / Entdecker / Wissensprofis") bleiben
zunächst; Auswahl erfolgt nach Alter, der Inhaltstyp-Split ist für den Nutzer
unsichtbar (Implementierungsdetail). Feinschliff der Namen optional, nicht nötig.

## 3. age_floor: Freigabe zur Anbietezeit (gelöst)

Problem: Themen mit `age_floor = 2` (z. B. WWII, Holocaust — „kein WWII für
4-Jährige") sind für 4–6 ungeeignet, aber das Hörspiel bedient 4–9 als ein
Artefakt.

**Lösung:** `age_floor` wandert von der Generierungs- in die **Anbietezeit**.
Das Hörspiel wird normal produziert; die App blendet es je Profil aus:

| Profil | bekommt angeboten |
|---|---|
| 4–6 | nur Hörspiele mit `age_floor = 1` |
| 7–9 | Hörspiele mit `age_floor = 1` **und** `2` |
| 10–12 | Erzähltexte |

Freitext-Frage eines 4–6-Kindes nach einem ausgeblendeten Thema → kein Treffer →
Professor verweist an die Eltern (Pfad existiert: `wissensfreund_provider.dart:128`).
→ 7–9 verliert **nichts**; nur die Kleinsten sehen heikle Themen nicht.

**Nur `age_floor = 3` bekommt kein Hörspiel** (nicht mal für 7–9) → ausschließlich
Erzählertext.

### Neues Stück Technik (klein, lokal)
1. `age_floor` beim Upload in die Artikel-Metadaten / Level-Index schreiben
   (`upload_articles.py`) — steht heute NICHT in den App-Metadaten.
2. Feld `ageFloor` in `WfArticle` ergänzen (`json_article_service.dart`).
3. Angebotsliste je Profil filtern (`wf_article_list_screen.dart`): 4–6 blendet
   `age_floor = 2`-Hörspiele aus.

## 4. Bild-`ab_stufe`: Floor folgt dem jüngsten Zuschauer (gelöst)

Problem: Manche Bilder sind für S2 (7–9) frei, für S1 (4–6) nicht (`ab_stufe`).
Per-Bild-Gating zur LAUFZEIT wäre hakelig — der Erzähler sagt „schau dir das an",
aber das Bild ist beim 4-Jährigen ausgeblendet → Erzähl-Loch.

**Lösung zur Generierungszeit:** Das Hörspiel ist EIN Artefakt mit EINEM
Bildersatz — dem, der für das jüngste Kind passt, das es je zu sehen bekommt:

| Hörspiel | jüngster Zuschauer | erlaubte Bilder |
|---|---|---|
| `age_floor = 1` (4–9) | 4 Jahre | nur `ab_stufe = 1` |
| `age_floor = 2` (nur 7–9) | 7 Jahre | `ab_stufe ≤ 2` |
| Erzählertext (10–12) | 10 Jahre | `ab_stufe ≤ 3` |

Zeile 2 ist der Clou: age_floor-2-Hörspiele bekommt kein 4-Jähriger je zu sehen
(per age_floor ausgeblendet) → sie dürfen die reicheren S2-Bilder nutzen. Die
Bildbeschränkung koppelt sich automatisch an die Artikel-Freigabe.

**Umsetzung:** Beim Hörspiel-Generieren `select_images_for_stufe` (run_batch.py)
mit der jüngsten Zielstufe des Themas aufrufen — Funktion kennt den Parameter
schon. Kein Laufzeit-Bildtausch, keine Erzähl-Löcher, kein pauschaler Verlust.

Preis: Ein 8-Jähriger sieht beim age_floor-1-Hörspiel den konservativen
4–6-Bildersatz. Bei einem bewusst jünger gedachten Format vertretbar; Bild ist
im Hörspiel sekundär zum Ton.

## 5. Wortziele / Hördauer Hörspiel (ENTSCHIEDEN 2026-07-18)

- **Hörspiel-Körperband ≈ altes S3, `(225, 975)`.** PO-Entscheidung: Inhaltstiefe
  vor Kürze.
- **5–7 min ist ein Richtwert, KEIN hartes Limit** (bewusst geändert ggü. der
  ersten Vorgabe). Ergiebige Themen dürfen 8–11 min lang werden.
  - Rechnerischer Hintergrund: ~90–100 gesprochene Wörter/min (aus den echten
    vulkan-Vertonungen). 975 Körper-Wörter + Rahmung ≈ 10–11 min.
  - OFFEN/optional: eine Sicherheits-Obergrenze (z. B. Trim bei > ~11–12 min über
    den bestehenden `CAP_GRACE_FRAC`/`TRIM`-Mechanismus), damit kein Ausreißer
    entsteht. Vom PO noch zu bestätigen.
- **Erzählertext (10–12):** Wortband bleibt unverändert `(225, 975)` (= altes S3).
- **Vier Band-Quellen vereinheitlichen:** Code `ERG_BANDS` (generate_grounded.py:101)
  ist die Wahrheit — S2 `(150,600)`, S3 `(225,975)`, +50 % seit 09.07. Die drei
  veralteten Doku-Kopien (PROJEKTDOKUMENT.md:41, WISSEN_ARTIKEL_PIPELINE.md:520,
  _validation_run.py:42) auf den Code zeigen lassen statt eigene Zahlen zu nennen.
- Kalibrierung: Das vorhandene Leonardo-Hörspiel als echten Dauer/Wort-Anker
  messen, sobald das Band verdrahtet ist.

## 6. Betroffene Stellen (aus der Bestandsaufnahme)

### App (`lib/`)
- **Datenmodell:** `profile_service.dart:12` (`ageLevel 1|2|3`, Defaults =2 an
  :22/:67/:94/:139) · `license_cache_db.dart:441` (`age_level DEFAULT 2`, Migration
  :193) · `wf_article.dart:39`, `json_article_service.dart:41` (`age_level ?? 2`).
- **Artikel-IDs:** `json_article_service.dart:127` (`levelFromId` Regex `_l(\d)`),
  :122 (`baseId`), :181 (`articleIdFor`), :83 (`loadLevelIndex` → `index/level_$level.json`)
  · `wf_article_list_screen.dart:97` · `narration_service.dart:80/:101` ·
  `asset_config.dart:51` (R2-Dateinamen).
- **Stufen-Auswahl-UI:** `profile_creation_screen.dart:21-24` (Namen+Alter) ·
  `profile_management_screen.dart:320-321` (`[1,2,3]`, Labels) · Stufen-Switcher in
  `wf_article_list_screen.dart:61` und `card_album_screen.dart:88`.
- **Modus-/Bild-Logik nach Stufe (Substanz!):** `article_screen.dart:157-158`
  (S1 kein Modus A), :470-472 (Toggle `ageLevel==1?[b,c]:[a,b,c]`), :1737-1764
  (`ageLevel<2` freies Swipen), :2011-2012/:2706-2707, :1975/:1979/:3543.
  → Neu verdrahten auf das bestätigte Raster (4–6 B+C, 7–9 A+B+C, 10–12 A+C).
  Alte `ageLevel<2`-Sonderwege prüfen: 4–6 soll TTS-Sync normal haben.
- **Sonstiges:** `home_screen.dart:389` (Test-ID `leo_mit_tags_l2`) ·
  `collected_card.dart:3,6` (Karten level-übergreifend, überlebt).

### Pipeline (`scripts/`)
- **Schon 2-stufig, neu umzudeuten:** `generate_grounded.py:101` (`ERG_BANDS`),
  :109 (`AGE_RANGES`), :1791 (`--stufen choices=[2,3]`) · `prepare_articles.py:495` ·
  `generate_articles.py:54` (`MIN_QUIZ_QUESTIONS`) · `artikel_pipeline.yml:69`.
- **Noch 3-stufig, mechanisch:** `upload_articles.py:191/:255` (`level_1..3.json`) ·
  `build_production_status.py:40/:131` (`STUFEN`, `COLS`) · `create_review_docs.py:424`.
- **3-stufig mit Inhalt (Entscheidung/Neutext):** `tts_compose.py:6-140` (`_PHRASES`
  S1/S2/S3 — S1-Phrasen für 4–6 getextet, fürs Hörspiel neu) · `tts_produce.py:56-67`
  (`MOOD_SCENE`) · `pipeline_new.py:73/:600/:1038-1044` · `lektorat_common.py:48/:245`
  (referenziert bereits totes S1) · `image_vision_filter.py:92/:243` (`ab_stufe`) ·
  `run_batch.py:934-935` (`_limit_images`) · `story_mode_v2.py:243/:306-314`.
- **Daten:** `ergiebigkeit_scores.json` (4.385 Themen × {S1,S2,S3}) +
  `build_ergiebigkeit_scores.py` neu aufbauen.

### Katalog / XLSX
- `catalog_review_master.xlsx`: `age_floor`-Spalte (J / Index 8) bleibt LESEND
  gültig — die Werte werden nur neu INTERPRETIERT (§3), nicht umgeschrieben.
- Output-Spalten S1/S2/S3 in `build_production_status.py:131` auf 2 Typen umstellen.

### CI-Guards (brechen absichtlich)
- `verify_project_facts.py:49-50` prüft `ERG_BANDS[3]=(225,975)` per `contains` →
  bricht bei jeder Band-Änderung. Sollbruchstelle by design: hier UND im Code
  anpassen. :45-48 (Prompt-Verdrahtung), :55-56 (`ergiebigkeit_scores ≥ 4000`,
  hält solange Themenzahl gleich bleibt).

### Doku (nach dem Umbau)
- `PROJEKTDOKUMENT.md` (veraltet, „durchgängig S1/S2/S3 [PO]"), `STATUS.md:6`,
  `WISSEN_ARTIKEL_PIPELINE.md`, `ARTIKEL_PIPELINE_MASTER.md`, `WISSEN_BILDER.md`,
  `wissensfreund_generator_prompt_v5_2.md`.

## 7. Umbau-Reihenfolge (vorgeschlagen)

1. **Entscheidungen fixieren** (§8) — Nummerierung, Namen, Wortbänder. Ohne die
   kein sinnvoller Start.
2. **Pipeline zuerst** — Generator + Prompt auf zwei Inhaltstypen; `ERG_BANDS`/
   `AGE_RANGES` neu; Hörspiel-Bildauswahl (§4); Quiz/Box je Typ. Ergebnis: ein
   Probelauf mit wenigen Themen erzeugt Hörspiel + Erzählertext sauber.
3. **Upload/Index** — `age_floor` in die Metadaten (§3), Index-Struktur auf zwei
   Typen. CI-Guards nachziehen.
4. **App** — ID-Mapping, Profil-Filter nach `age_floor`, Modus-Raster, UI-Texte/
   Namen. Handy-Modus prüfen (Regel: vorher absprechen).
5. **Katalog neu klassieren** — `age_floor`-Werte im Master gegen das neue Modell
   sichten (die meisten bleiben; nur Grenzfälle prüfen).
6. **Vollproduktion** neu generieren, alte Artikel verwerfen.
7. **Doku** aktualisieren (§6) + Projektdokument generalüberholen (auch auf
   weitere Inkonsistenzen prüfen).

## 8. Produktentscheidungen

1. **Nummerierung/Namen** — ENTSCHIEDEN (§2): `_hoerspiel/_erzaehltext`, Profil
   dreistufig, Stufen-Namen bleiben.
2. **Wortbänder** — ENTSCHIEDEN (§5): Hörspiel-Körperband `(225,975)` wie S3,
   Dauer floatet (5–7 min = Richtwert). Code `ERG_BANDS` ist die Wahrheit, Doku
   vereinheitlichen. OFFEN: optionale Sicherheits-Obergrenze gegen Ausreißer.
3. **Migration bestehender Profile** — kein Handlungsbedarf: Profil bleibt
   dreistufig (`ageLevel` 1/2/3), Bestandsprofile funktionieren weiter. Nur prüfen,
   ob Default `=2` noch passt.
4. **Vertonung/Timing-Sidecars** — kein Rename-Problem: bestehende Audios auf R2
   werden mit der Neugenerierung ohnehin ersetzt.

## 9. Was gelöscht / neu erzeugt wird

- **Löschen/verwerfen:** alle bisherigen generierten Artikel (`_l1/_l2/_l3` —
  Klexikon-Reste), zugehörige Audios/Sidecars auf R2, `ergiebigkeit_scores.json`
  (Rebuild).
- **Neu:** Hörspiel + Erzählertext je Thema, neue IDs, `age_floor` in Metadaten,
  bildkohärent nach §4.
