# WISSEN: Bild-Pipeline
<!-- Thematisches Wissensdokument — wird nicht täglich gelesen, nur bei Bild-Themen -->
<!-- Letztes Update: 2026-06-05 -->

## Status: ABGESCHLOSSEN ✅

Alle drei Image-ZIPs sind live in Cloudflare R2:
- `images_thumb.zip` → 300px (~545 MB) — Free-Nutzer
- `images_standard.zip` → 800px (~3,3 GB) — Plus offline
- `images_pro.zip` → 1600px — Premium offline

`image_index.json` (Hash → Commons-Dateiname, 16.582 Einträge) liegt in R2.

---

## Wie die Bildauflösung funktioniert

| Nutzertyp | Quelle | Auflösung |
|---|---|---|
| Free | ZIM → images_thumb.zip | 300px |
| Plus + WLAN-Switch aus | images_standard.zip (lokal) | 800px |
| Plus + WLAN-Switch an | HiResImageService → Wikimedia Commons | bis ~2048px (Original wenn <5 MB, sonst 2048px-Thumbnail) |
| Premium + WLAN-Switch aus | images_pro.zip (lokal) | 1600px |

On-demand-Logik: App versucht Original-URL von Commons (< 5 MB Check), 
falls > 5 MB → 2048px-Thumbnail-URL. 404s werden nur im Arbeitsspeicher gecacht (nicht persistent).

---

## Wie das Hash→Dateiname-Mapping entstand

ZIM speichert Bilder als MD5-Hash (`_assets_/abc123.jpg`).
Kiwix stripped beim Bauen alle `Datei:`-Links aus dem HTML.

**Lösung:** `scrape_klexikon_images.py` scrapt live Klexikon-Seiten,
folgt `Datei:`-Links zu Commons-Beschreibungsseiten, extrahiert Commons-URL.
Ergebnis: 92% Match über 3.611 Artikel.

Commons-URL ist deterministisch aus Dateiname berechenbar (MediaWiki MD5-Routing),
deshalb ist `SKIP_COMMONS=1` verlustlos möglich.

---

## Verworfene Ansätze — NICHT nochmal versuchen

- `entry.title` aus ZIM → immer `null`
- `Datei:`-Links aus ZIM-HTML → von Kiwix beim Bauen entfernt
- `prop=images` + Caption-Matching → nur ~30% Konfidenz
- `action=parse` + Count-Matching → 37–82%, zu unzuverlässig
- mwoffliner (openzim) → nur als Notfall-Fallback wenn Scraping scheitert

---

## Content-Sicherheit (Bilder) — KINDERSCHUTZ

Geplante dreistufige Filterung (Konzept); tatsächlicher Stand aus Code-Analyse 2026-06-04:

- **Stufe 1 — Lizenz-Whitelist** (CC0, CC-BY, CC-BY-SA, **FAL/LAL**): **✅ aktiv implementiert.**
  `_is_free_license()` in `generate_articles.py` und `patch_article_images_v1.py` (je eigene
  Funktion, identische Logik). FAL (Free Art License / Licence Art Libre, SPDX LAL-1.x) am
  2026-06-05 ergänzt: FSF-anerkannt, copyleft, kommerziell nutzbar, CC-BY-SA-4.0-kompatibel —
  gleiche Attribution+Share-Alike-Pflicht wie CC-BY-SA. CC-BY-NC / CC-BY-ND werden explizit
  ausgeschlossen (NC = nicht kommerziell; ND = keine Bearbeitung, Resizing wäre Bearbeitung).
  Fund durch Kalibrier-Harness (`Elephant_feces_in_the_wildlife.jpg`, FAL, steht im echten
  Klexikon-Artikel). **Hinweis:** `patch_article_images_v1.py` hatte zuvor keinen Lizenzfilter
  (Doku-Fehler 2026-06-04); der Filter wurde mit diesem Commit ergänzt.

- **Stufe 2 — Kategorie-Blacklist** (Human_sexuality, War_photographs, Medical_imaging,
  Nudity u.a.): **❌ NICHT implementiert.** `global_exclusions.topics` in der
  Kategorien-Whitelist-JSON enthält eine entsprechende Liste, aber **kein Code fragt
  Wikipedia-Bildkategorien ab oder prüft diese topics-Liste**. Bilder aus expliziten
  Kategorien werden nicht aktiv ausgeschlossen.

- **Stufe 3 — Automatische Bildanalyse** (Content-Moderation, Safe-Search-artig):
  **⚠️ partiell.** `call_claude_image_filter()` in `patch_article_images_v1.py` sendet
  altersgerechte Filterregeln im Prompt:
  - Stufe 1: „Keine Skelette, Fossilien, Anatomie, tote Tiere, Jagdszenen, verstörende Inhalte"
  - Stufe 2: „Skelette und anatomische Darstellungen ok wenn lehrreich"
  - Stufe 3: „Alle sachlich korrekten Bilder erlaubt"
  Claude sieht jedoch nur **Dateinamen** — kein Vision-Modell, keine Safe-Search-API.
  Dateinamen-Matching ist schwach (z.B. `Anatomy_of_the_vulva.jpg` wird nicht erkannt).
  Patch noch nicht produktiv gelaufen.

**⚠️ OFFEN (Kinderschutz, Hoch):** Stufen 2 und 3 fehlen als aktiver Code-Filter.
Vor dem ersten produktiven Bild-Patch-Run entscheiden:
Reicht der dateiname-basierte Claude-Filter, oder braucht es Wikipedia-Kategorienabruf
(per `prop=categories` auf Commons) + Vision-API (z.B. Google Safe Search)?
Diese Entscheidung ist kinderschutz-relevant und sollte vor dem Pilot getroffen werden.

**Kalibrierung 2026-06-05, Pilot Elefant:** Stufenfilter bestätigt; Skelett S1 reject /
S2+S3 keep, Elfenbein S1 reject / S3 keep; S2-Skelett bewusst keep.

---

## Lizenz / Attribution

`scrape_klexikon_images.py` speichert **keine** Lizenz/Autor-Information (nur Dateiname + Caption).

`patch_article_images_v1.py` holt über Commons-API: `Artist` + `LicenseShortName` + `source_url`.
Freie Lizenzen: CC0, CC-BY, CC-BY-SA, FAL/LAL (alle Varianten: "FAL", "LAL", "Free Art License",
"Licence Art Libre", LAL-1.2, LAL-1.3). CC-BY-NC / CC-BY-ND werden vor KI-Verarbeitung
herausgefiltert (NC nicht kommerziell, ND keine Bearbeitung).

**CC-BY / CC-BY-SA / FAL verlangen Urhebernennung** — die App braucht eine Attributionsanzeige
(Foto-Credit im Vollbild oder Footer). Für ZIM-Artikel-Bilder ist die Attribution noch
offen (Patch nicht produktiv gelaufen, Anzeige nicht implementiert).
Der offene Punkt „Attributionsanzeige" deckt FAL vollständig mit ab (gleiche Urhebernennungspflicht).

---

## SVG-Diagramme (Fix B, 07.07.2026 — `image_vision_filter.py`, geteilt alt+neu)

Didaktische SVG-Diagramme (Schemata, Stromfluss, Querschnitte) sind jetzt erlaubt.
`.svg` war zuvor in `_IMG_SKIP_EXT` — der Skip filterte implizit auch fast alle
Deko (Logos/Icons/Flaggen sind meist SVG). Beim Öffnen des SVG-Tors mussten daher
die Namensfilter nachziehen.

- **Kein neues Dependency:** Die Wikimedia-API rendert SVG→PNG serverseitig, sobald
  `iiurlwidth` gesetzt ist — `thumburl` ist bei SVG bereits ein PNG
  (`.../Foo.svg/1600px-Foo.svg.png`). `thumb_url` (Download-/Vision-/Tier-Quelle)
  zeigt darauf; nie die rohe `.svg` (PIL kann sie nicht öffnen).
- **Fallback:** Fehlt `thumburl` bei SVG, baut `_wikimedia_thumb_url(filename, 1600)`
  die PNG-Thumb-URL per md5-Hash selbst (vorher toter Code, jetzt Sicherheitsnetz).
- **Deko-Filter trenner-agnostisch:** `t_key = t_lower.replace(" ","_").replace("-","_")`
  vor dem Matchen. Damit greifen `_logo.`/`_icon.`/`flag_of` auch für Bindestrich-/
  Leerzeichen-Titel (`Enigma-logo.svg`, `Flag of X.svg`) — vorher rutschten die durch.
  `_IMG_SKIP_PREFIXES_KEY` = normalisierte Prefix-Liste; neu: `qsicon`, `favicon`.
- **Transparenz → Weiß:** `_scale_image` legt Alpha (RGBA/LA/P) via `alpha_composite`
  auf weißen Grund statt `convert("RGB")` (sonst Diagramm-Linien auf Schwarz). Betrifft
  nur Bilder mit Alpha; JPGs unberührt.
- **Verifiziert:** Enigma → `Enigma-action.svg` (Rotor-Diagramm) überlebt, Deko-SVGs
  gefiltert, 24 Foto-JPGs unverändert; Download→RGBA(1920²)→JPEG-Tiers 300/800,
  Eckpixel weiß. Vision-*Akzeptanz* (Gemini) noch e2e nachzuziehen (503-Welle).

---

## Offene Punkte

- **Gallery-Artikel (111 Artikel, 540 Bilder)** → Version 1.1
  - Diese Artikel verwenden MediaWiki `<gallery>`-Tags
  - Kiwix rendert sie anders → kein Hash → kein ZIP-Eintrag
  - Braucht: `gallery_index.json` + eigene Gallery-UI-Komponente
- **Audio-Pipeline** → lief am 2026-05-28 in CI, produzierte 0 Dateien. `download_audio.py` / `extract_article_audio.py` noch nicht funktionsfähig — Debugging ausstehend

---

## Pipeline-Skripte (CI-Repo)

- `scrape_klexikon_images.py` — Hauptskript, scrapt Live-Klexikon-Seiten, extrahiert Commons-URLs
- `download_images.py` — lädt Bilder, resized lokal mit Pillow LANCZOS (thumb 300px/Q70, standard 800px/Q80, pro 1600px/Q85)
- `build_image_zips.py` / `merge_image_zips.py` / `merge_image_shards.py` — ZIP-Bau und Shard-Merge
- `generate_image_index.py` — erzeugt `image_index.json` (Hash → Dateiname)
- `patch_article_images_v1.py` — patcht ZIM-Artikel-JSONs: Wikipedia-API für Bildkandidaten, Claude API für altersgerechte Filterung und satzgenaue `img_index`-Zuweisung. Checkpoint-Datei für Resume.
- `update_image_licenses.yml` — GitHub Actions Workflow, läuft monatlich (oder manuell)

---

## App-seitige Services

- `HiResImageService` — on-demand Fetch, 5 MB Check, negativer In-Memory-Cache
- `ImageLibraryService` — offline ZIP, `hiresOnWifiEnabled` Bool (SharedPrefs)
- `WissensfreundProvider._resolveImageBytes()` — Routing nach Tier + WiFi-Setting
