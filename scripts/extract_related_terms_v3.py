#!/usr/bin/env python3
"""
extract_related_terms_v3.py
Wissensfreund Artikel-Pipeline — Related Terms + Sound + Content-Depth + Bild-Metadaten

Änderungen gegenüber v2:
- fetch_image_metadata(): Lädt source_url, author, license direkt von Commons API
- strip_html(): Bereinigt HTML-Tags im Artist-Feld
- ImageMetadata TypedDict
- main() gibt IMAGE_METADATA Block aus
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import TypedDict


# ─────────────────────────────────────────────────────────
# Typen
# ─────────────────────────────────────────────────────────

class WikiLink(TypedDict):
    title: str
    slug: str
    label: str
    position: float
    count: int
    source: str

class RelatedTerm(TypedDict):
    slug: str
    label: str
    context: str
    link_type: str    # "core" | "discover"
    source: str
    available: bool


class ImageMetadata(TypedDict):
    filename: str       # z.B. "African_Bush_Elephant.jpg"
    source_url: str     # Link zur Commons-Seite
    author: str         # Urheber, HTML-bereinigt
    license: str        # z.B. "CC BY-SA 4.0"

class SoundCandidate(TypedDict):
    filename: str     # z.B. "Ode_an_die_Freude.ogg"
    caption: str      # Beschreibungstext aus dem Wikitext
    position: float   # Position im Artikel


# ─────────────────────────────────────────────────────────
# Slug-Normalisierung
# ─────────────────────────────────────────────────────────

def normalize_slug(title: str) -> str:
    title = re.sub(r'\s*\([^)]+\)', '', title).strip()
    title = title.lower()
    for char, replacement in {'ä':'ae','ö':'oe','ü':'ue','ß':'ss'}.items():
        title = title.replace(char, replacement)
    title = unicodedata.normalize('NFKD', title)
    title = title.encode('ascii', 'ignore').decode('ascii')
    title = re.sub(r'\s+', '_', title)
    title = re.sub(r'[^a-z0-9_-]', '', title)
    return title.strip('_-')


SKIP_PREFIXES = {
    'datei:','file:','bild:','image:','kategorie:','category:',
    'vorlage:','template:','wikipedia:','hilfe:','portal:',
    'wiktionary:','wikisource:','commons:','benutzer:',
}

SKIP_SLUGS = {
    'mittelhochdeutsch','mittellatein','altfranzosisch',
    'latein','griechisch','arabisch','wikipedia',
    'weblink','einzelnachweis','liste','kategorie',
}


# ─────────────────────────────────────────────────────────
# Content-Depth Score
# ─────────────────────────────────────────────────────────

def content_depth_score(wikitext: str, age_level: int) -> int:
    """
    Berechnet CONTENT_DEPTH 1-3 aus dem Wikipedia-Rohtext.

    1 = kurzer/dünner Artikel → wenige Abschnitte
    2 = normaler Artikel
    3 = reicher Artikel → viele Abschnitte möglich

    Kriterien:
    - Textlänge (Hauptindikator für Quelldichte)
    - Zahlen/Maßangaben (konkrete Fakten vorhanden)
    - Altersspezifische Signalwörter
    """
    score = 0

    # Textlänge → Quelldichte
    length = len(wikitext)
    if length > 8000:
        score += 2
    elif length > 3000:
        score += 1

    # Zahlen und Maßangaben → konkrete Fakten
    numbers = len(re.findall(r'\b\d+[\.,]?\d*\s*(?:km|m|cm|kg|t|Jahre?|Jahrhundert|Prozent|%)\b', wikitext))
    if numbers >= 5:
        score += 1

    # Altersspezifische Signalwörter
    signals = {
        1: ['frisst', 'lebt', 'groß', 'klein', 'Junge', 'Mutter', 'spielt'],
        2: ['erfunden', 'gebaut', 'kämpfte', 'entdeckte', 'Ausbildung', 'Turnier'],
        3: ['Gesellschaft', 'System', 'Wirtschaft', 'Konflikt', 'Entwicklung', 'Forschung'],
    }
    level_signals = signals.get(age_level, signals[2])
    hits = sum(1 for s in level_signals if s.lower() in wikitext.lower())
    if hits >= 3:
        score += 1

    return max(1, min(3, score))


# ─────────────────────────────────────────────────────────
# Link-Extraktion
# ─────────────────────────────────────────────────────────

def extract_candidates(wikitext: str) -> list[WikiLink]:
    pattern = re.compile(r'\[\[([^\[\]|#]+)(?:\|([^\[\]]+))?\]\]')
    total_len = max(len(wikitext), 1)
    seen: dict[str, WikiLink] = {}

    for match in pattern.finditer(wikitext):
        raw_title = match.group(1).strip()
        raw_label = match.group(2).strip() if match.group(2) else raw_title

        if any(raw_title.lower().startswith(p) for p in SKIP_PREFIXES):
            continue

        slug = normalize_slug(raw_title)
        label = re.sub(r'\s*\([^)]+\)', '', raw_label).strip()

        if not slug or slug in SKIP_SLUGS or len(slug) < 3:
            continue

        position = match.start() / total_len

        if slug in seen:
            seen[slug]['count'] += 1
            seen[slug]['position'] = min(seen[slug]['position'], position)
        else:
            seen[slug] = WikiLink(
                title=raw_title, slug=slug, label=label,
                position=round(position, 3), count=1, source='wikipedia_link',
            )

    return sorted(seen.values(), key=lambda x: (x['position'], -x['count']))


# ─────────────────────────────────────────────────────────
# Sound-Extraktion
# ─────────────────────────────────────────────────────────

def extract_sound_candidates(wikitext: str) -> list[SoundCandidate]:
    """
    Sucht nach Audio-Dateien (.ogg) im Wikitext.
    Format: [[Datei:Name.ogg|Beschreibung]] oder direkte Verlinkungen.
    """
    candidates: list[SoundCandidate] = []
    total_len = max(len(wikitext), 1)

    # Datei/File-Links mit .ogg
    pattern = re.compile(
        r'\[\[(?:Datei|File):([^\]|]+\.ogg)(?:\|([^\]]*))?\]\]',
        re.IGNORECASE
    )
    for match in pattern.finditer(wikitext):
        filename = match.group(1).strip().replace(' ', '_')
        caption_raw = match.group(2) or ''
        # Wikitext-Markup aus Caption entfernen
        caption = re.sub(r'\[\[[^\]]+\|([^\]]+)\]\]', r'\1', caption_raw)
        caption = re.sub(r'\[\[([^\]]+)\]\]', r'\1', caption)
        caption = re.sub(r"'{2,}", '', caption).strip()
        caption = caption[:100] if caption else filename.replace('_', ' ').replace('.ogg', '')

        position = match.start() / total_len
        candidates.append(SoundCandidate(
            filename=filename,
            caption=caption,
            position=round(position, 3),
        ))

    return candidates


# ─────────────────────────────────────────────────────────
# Filter
# ─────────────────────────────────────────────────────────

def filter_candidates(
    candidates: list[WikiLink],
    article_index: dict[str, bool],
    max_for_ai: int = 15,
    position_cutoff: float = 0.65,
) -> list[RelatedTerm]:
    """
    Filtert gegen den Index.
    Gibt max. max_for_ai Kandidaten zurück — KI wählt daraus core/discover.
    """
    results: list[RelatedTerm] = []
    for c in candidates:
        available = article_index.get(c['slug'], False)
        results.append(RelatedTerm(
            slug=c['slug'],
            label=c['label'],
            context='',
            link_type='core',   # KI entscheidet core vs. discover
            source=c['source'],
            available=available,
        ))

    # Verfügbare zuerst, dann nach Position
    results.sort(key=lambda x: (
        0 if x['available'] else 1,
        next((c['position'] for c in candidates if c['slug'] == x['slug']), 1.0),
    ))
    return results[:max_for_ai]


# ─────────────────────────────────────────────────────────
# Wunschliste
# ─────────────────────────────────────────────────────────

def update_wishlist(
    candidates: list[WikiLink],
    article_index: dict[str, bool],
    wishlist_path: Path,
    source_slug: str,
) -> None:
    wishlist: dict = {}
    if wishlist_path.exists():
        wishlist = json.loads(wishlist_path.read_text(encoding='utf-8'))

    for c in candidates:
        if article_index.get(c['slug'], False):
            continue
        if c['slug'] not in wishlist:
            wishlist[c['slug']] = {'label': c['label'], 'count': 0, 'linked_from': []}
        wishlist[c['slug']]['count'] += 1
        if source_slug not in wishlist[c['slug']]['linked_from']:
            wishlist[c['slug']]['linked_from'].append(source_slug)

    sorted_wl = dict(sorted(wishlist.items(), key=lambda x: -x[1]['count']))
    wishlist_path.write_text(
        json.dumps(sorted_wl, ensure_ascii=False, indent=2), encoding='utf-8'
    )



# ─────────────────────────────────────────────────────────
# Bild-Metadaten von Wikimedia Commons API
# ─────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Entfernt HTML-Tags und dekodiert häufige HTML-Entities."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    for entity, char in {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#039;": "'", "&nbsp;": " ",
    }.items():
        clean = clean.replace(entity, char)
    return re.sub(r"\s+", " ", clean).strip()


def fetch_image_metadata(
    filenames: list[str],
    session,  # requests.Session
) -> dict[str, ImageMetadata]:
    """
    Holt source_url, author und license für eine Liste von Commons-Dateinamen.
    Bis zu 50 Dateien pro API-Aufruf (API-Maximum).

    Gibt dict {filename: ImageMetadata} zurück.
    Fehlende Einträge erhalten leere Strings.
    """
    COMMONS_API = "https://commons.wikimedia.org/w/api.php"
    results: dict[str, ImageMetadata] = {}

    # Batches à 50 (API-Maximum)
    for i in range(0, len(filenames), 50):
        batch = filenames[i:i + 50]
        titles = "|".join(f"File:{fn}" for fn in batch)

        try:
            r = session.get(COMMONS_API, params={
                "action": "query",
                "titles": titles,
                "prop": "imageinfo",
                "iiprop": "url|descriptionurl|extmetadata",
                "iiextmetadatafilter": "Artist|LicenseShortName",
                "iimetadatalanguage": "de",
                "format": "json",
                "formatversion": "2",
            }, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  Commons API Fehler: {e}")
            for fn in batch:
                results[fn] = ImageMetadata(
                    filename=fn, source_url="", author="", license=""
                )
            continue

        for page in data.get("query", {}).get("pages", []):
            title = page.get("title", "")
            filename = title.removeprefix("File:") if title.startswith("File:") else title
            if page.get("missing") or "imageinfo" not in page:
                results[filename] = ImageMetadata(
                    filename=filename, source_url="", author="", license=""
                )
                continue
            info = page["imageinfo"][0] if page["imageinfo"] else {}
            extmeta = info.get("extmetadata", {})
            results[filename] = ImageMetadata(
                filename=filename,
                source_url=info.get("descriptionurl", ""),
                author=strip_html(extmeta.get("Artist", {}).get("value", "")),
                license=extmeta.get("LicenseShortName", {}).get("value", ""),
            )

    return results


# ─────────────────────────────────────────────────────────
# Direktaufruf
# ─────────────────────────────────────────────────────────

def main():
    import argparse, sys
    try:
        import requests
    except ImportError:
        print("pip install requests --break-system-packages")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument('--title',    required=True)
    parser.add_argument('--age',      type=int, default=2, choices=[1,2,3])
    parser.add_argument('--index',    default='article_index.json')
    parser.add_argument('--wishlist', default='wishlist.json')
    args = parser.parse_args()

    r = requests.get(
        'https://de.wikipedia.org/w/api.php',
        params={'action':'query','titles':args.title,'prop':'revisions',
                'rvprop':'content','rvslots':'main','format':'json'},
        headers={'User-Agent':'Wissensfreund-Test/1.0'}, timeout=15,
    )
    pages = r.json()['query']['pages']
    page = next(iter(pages.values()))
    if 'revisions' not in page:
        print("Artikel nicht gefunden.")
        sys.exit(1)
    wikitext = page['revisions'][0]['slots']['main']['*']
    print(f"Wikitext: {len(wikitext):,} Zeichen")

    index_path = Path(args.index)
    article_index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}

    # Content-Depth
    depth = content_depth_score(wikitext, args.age)
    print(f"CONTENT_DEPTH: {depth}")

    # Links
    candidates = extract_candidates(wikitext)
    filtered = filter_candidates(candidates, article_index)
    available = [t for t in filtered if t['available']]
    not_available = [t for t in filtered if not t['available']]

    print(f"\nLink-Kandidaten für KI (Top {len(filtered)}):")
    print(f"  ✓ Im Index ({len(available)}):     " +
          ', '.join(t['label'] for t in available[:8]))
    print(f"  ○ Fehlt noch ({len(not_available)}): " +
          ', '.join(t['label'] for t in not_available[:8]))

    # Sounds
    sounds = extract_sound_candidates(wikitext)
    if sounds:
        print(f"\nSound-Kandidaten ({len(sounds)}):")
        for s in sounds[:3]:
            print(f"  [{s['position']:.2f}] {s['filename']} — {s['caption']}")
    else:
        print("\nKeine Sound-Dateien gefunden.")

    # Wunschliste
    update_wishlist(candidates, article_index, Path(args.wishlist), normalize_slug(args.title))
    print(f"\nWunschliste aktualisiert: {args.wishlist}")

    # Bild-Metadaten: alle .ogg + Bilder aus Wikipedia-Artikel holen
    # Wikimedia-Bilder aus Wikitext extrahieren
    img_pattern = re.compile(
        r'\[\[(?:Datei|File|Bild):([^\]|#]+\.(?:jpg|jpeg|png|svg|gif|webp))(?:\|[^\]]*)?\]\]',
        re.IGNORECASE
    )
    img_files = list({m.group(1).strip().replace(' ', '_')
                      for m in img_pattern.finditer(wikitext)})

    if img_files:
        import requests as req_mod
        img_session = req_mod.Session()
        img_session.headers['User-Agent'] = 'Wissensfreund-Pipeline/3.0'
        print(f"\nBild-Metadaten für {len(img_files)} Dateien:")
        meta = fetch_image_metadata(img_files, img_session)
        for fn, m in list(meta.items())[:5]:
            print(f"  {fn[:45]:<45} | {m['license']:<15} | {m['author'][:30]}")
        print(f"  ... ({len(meta)} gesamt)")
        # Für Artikel-Generierung als JSON-Block ausgeben
        print("\nIMAGE_METADATA:")
        print(json.dumps(list(meta.values()), ensure_ascii=False, indent=2))
    else:
        print("\nKeine Bilder im Wikitext gefunden.")


if __name__ == '__main__':
    main()
