# WISSEN: Bild-Pipeline
<!-- Thematisches Wissensdokument — wird nicht täglich gelesen, nur bei Bild-Themen -->
<!-- Letztes Update: 2026-06-01 -->

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
