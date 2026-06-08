#!/usr/bin/env python3
"""
preview_article_html.py  —  Wissensfreund article HTML preview generator

Fetches images from Wikipedia/Commons, parses a Wissensfreund article .md
file, and renders a mobile-sized tabbed HTML preview (S1/S2/S3).

Usage:
    python tools/preview_article_html.py --thema Biene --artikel temp/bienen_artikel.md

Output: output/preview_{thema}.html
        (+ R2 upload when CF_R2_ACCESS_KEY_ID, CF_R2_SECRET_ACCESS_KEY,
           CF_ACCOUNT_ID, CF_R2_BUCKET, CF_R2_PUBLIC_URL are set)
"""

import argparse
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

EXCLUDE_RE = re.compile(r'logo|icon|flag|map|wappen', re.IGNORECASE)

BOX_MAP = {
    '🌟': ('#FFF3CD', 'wow'),
    '🤔': ('#D1ECF1', 'stimmt'),
    '⚠️': ('#F8D7DA', 'warnung'),
    '💡': ('#D4EDDA', 'fakt'),
}

_UA = 'WissensfreundPreview/1.0'

# ── Wikipedia / Commons image fetching ───────────────────────────────────────

def _api_get(base_url, **params):
    params.setdefault('format', 'json')
    url = base_url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _strip_html_tags(s):
    return re.sub(r'<[^>]+>', '', s).strip()


def _get_wikipedia_image_names(thema):
    data = _api_get(
        'https://de.wikipedia.org/w/api.php',
        action='query', titles=thema, redirects=1, prop='images',
        imlimit=50, formatversion=2,
    )
    names = []
    for page in data.get('query', {}).get('pages', []):
        for img in page.get('images', []):
            title = img.get('title', '')
            name = re.sub(r'^(File|Datei):', '', title, flags=re.IGNORECASE)
            ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
            if ext not in ('jpg', 'jpeg', 'png'):
                continue
            if EXCLUDE_RE.search(name):
                continue
            names.append(name)
    return names


def _get_commons_meta(filename):
    data = _api_get(
        'https://commons.wikimedia.org/w/api.php',
        action='query', titles=f'File:{filename}',
        prop='imageinfo', iiprop='url|extmetadata',
        iiurlwidth=800, iiextmetadatafilter='Artist|LicenseShortName',
    )
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        info_list = page.get('imageinfo') or []
        if not info_list:
            continue
        info = info_list[0]
        url = info.get('thumburl') or info.get('url', '')
        if not url:
            continue
        em = info.get('extmetadata', {})
        artist = _strip_html_tags(em.get('Artist', {}).get('value', '')) or 'Unknown'
        license_ = em.get('LicenseShortName', {}).get('value', '').strip() or 'Unknown'
        return {'url': url, 'artist': artist, 'license': license_}
    return None


def fetch_images(thema, max_count=8):
    print(f'[img] Fetching Wikipedia images for "{thema}"…', file=sys.stderr)
    names = _get_wikipedia_image_names(thema)
    print(f'[img] {len(names)} candidates', file=sys.stderr)
    images = []
    for name in names:
        if len(images) >= max_count:
            break
        time.sleep(0.4)  # respect Commons rate limit
        try:
            meta = _get_commons_meta(name)
            if meta:
                images.append(meta)
                print(f'[img]   ✓ {name}', file=sys.stderr)
            else:
                print(f'[img]   - {name} (no url)', file=sys.stderr)
        except Exception as exc:
            print(f'[img]   ✗ {name}: {exc}', file=sys.stderr)
    print(f'[img] Using {len(images)} images', file=sys.stderr)
    return images

# ── Markdown parsing helpers ──────────────────────────────────────────────────

def _esc(s):
    return html_lib.escape(str(s))


def _inline(s):
    s = _esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    return s


def _to_paragraphs(text):
    """Split text into groups of consecutive non-blank lines."""
    result, current = [], []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result


def _detect_box(para):
    """If first non-blank line contains a box emoji, return (color, css_class, raw_content)."""
    first = para[0].strip()
    for emoji, (color, css_cls) in BOX_MAP.items():
        if emoji in first[:6]:
            content = ' '.join(l.strip() for l in para if l.strip())
            content = content.replace(emoji, '', 1).strip()
            return color, css_cls, content
    return None


def _is_quiz_paragraph(para):
    """Heuristic: paragraph with A)/B)/C) answer lines = quiz Q&A block."""
    lines = [l.strip() for l in para if l.strip()]
    if len(lines) < 2:
        return False
    answer_lines = [l for l in lines[1:] if re.match(r'^[A-Ca-c]\)', l)]
    return len(answer_lines) >= 2


def _render_quiz_block(para):
    """Render one quiz Q&A block as <details><summary>…</summary>…</details>."""
    lines = [l.strip() for l in para if l.strip()]
    if not lines:
        return ''
    question = _esc(lines[0])
    answers_html = ''
    for ans in lines[1:]:
        correct = '✓' in ans
        ans_text = ans.replace('✓', '').strip()
        color = '#28a745' if correct else 'inherit'
        answers_html += (
            f'<div style="color:{color};padding:2px 0">{_esc(ans_text)}</div>'
        )
    return (
        f'<details style="margin:8px 0;border:1px solid #ddd;border-radius:6px;padding:8px">'
        f'<summary style="cursor:pointer;font-weight:bold">{question}</summary>'
        f'<div style="padding:8px 0">{answers_html}</div>'
        f'</details>'
    )

# ── Level renderer ────────────────────────────────────────────────────────────

def render_level(text, images, level_idx):
    """Convert one level's markdown text to an HTML fragment."""
    paras = _to_paragraphs(text)
    out = []
    p_count = 0
    img_idx = 0
    in_quiz = False

    i = 0
    while i < len(paras):
        para = paras[i]
        first = para[0].strip()

        # ── Stufe X subtitle line ──────────────────────────────────────────
        if re.match(r'^Stufe \d', first):
            out.append(
                f'<p style="color:#888;font-size:14px;margin:4px 0 0">{_esc(first)}</p>'
            )
            i += 1
            continue

        # ── Quiz heading ───────────────────────────────────────────────────
        if re.match(r'^\*{0,2}Quiz\*{0,2}$', first):
            in_quiz = True
            out.append('<h3>Quiz</h3>')
            i += 1
            continue

        # ── Quiz Q&A block (only after "Quiz" heading) ─────────────────────
        if in_quiz and _is_quiz_paragraph(para):
            out.append(_render_quiz_block(para))
            i += 1
            continue

        # ── Box (emoji-prefixed indented paragraph) ────────────────────────
        box = _detect_box(para)
        if box:
            color, css_cls, content = box
            # Lookahead: merge next indented non-emoji, non-quiz paragraph
            if (not in_quiz
                    and i + 1 < len(paras)
                    and paras[i + 1][0].startswith('    ')
                    and not _detect_box(paras[i + 1])
                    and not _is_quiz_paragraph(paras[i + 1])):
                extra = ' '.join(l.strip() for l in paras[i + 1] if l.strip())
                content = content + ' ' + extra
                i += 1
            out.append(
                f'<div class="box {css_cls}" style="background:{color};padding:12px;'
                f'border-radius:8px;margin:16px 0">{_inline(content)}</div>'
            )
            i += 1
            continue

        # ── ### heading ────────────────────────────────────────────────────
        if first.startswith('###'):
            out.append(f'<h3>{_inline(first[3:].strip())}</h3>')
            i += 1
            continue

        # ── Regular paragraph ──────────────────────────────────────────────
        body = ' '.join(l.strip() for l in para if l.strip())
        out.append(f'<p>{_inline(body)}</p>')
        p_count += 1

        # Insert image after every 2nd paragraph in S2 / S3
        if level_idx > 0 and p_count % 2 == 0 and img_idx < len(images):
            img = images[img_idx]
            img_idx += 1
            out.append(
                f'<img src="{_esc(img["url"])}" '
                f'style="width:100%;border-radius:8px;margin:12px 0" '
                f'loading="lazy" alt="">'
                f'<div style="font-size:12px;color:#666;margin-bottom:8px">'
                f'© {_esc(img["artist"])} · {_esc(img["license"])}</div>'
            )

        i += 1

    return '\n'.join(out)

# ── Article parser ────────────────────────────────────────────────────────────

def parse_article(md_text):
    """Strip <planung> block and split into three level text blocks."""
    text = re.sub(r'<planung>.*?</planung>\s*', '', md_text, flags=re.DOTALL).strip()

    # Try explicit "---" separator first
    parts = re.split(r'\n---\n', text)
    if len(parts) >= 3:
        return [p.strip() for p in parts[:3]]

    # Fall back: split on "Stufe X" headings
    chunks = re.split(r'(?=^Stufe \d)', text, flags=re.MULTILINE)
    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) >= 3:
        return chunks[:3]

    # Last resort: same text for all three (parse will still work)
    return [text, text, text]

# ── HTML template ─────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; }
body {
    max-width: 420px; margin: auto; font-family: sans-serif;
    font-size: 18px; line-height: 1.6; padding: 12px;
}
h2 { margin-bottom: 4px; font-size: 20px; }
h3 { margin: 20px 0 8px; }
p  { margin: 12px 0; }
.tabs {
    display: flex; gap: 8px; margin-bottom: 16px;
    border-bottom: 2px solid #eee;
}
.tab-btn {
    background: none; border: none; font-size: 16px;
    padding: 8px 12px; cursor: pointer; color: #666;
    border-bottom: 3px solid transparent; margin-bottom: -2px;
}
.tab-btn.active { color: #000; border-bottom-color: #000; font-weight: bold; }
.level   { display: none; }
.level.active { display: block; }
details { margin: 6px 0; }
details summary { cursor: pointer; }
"""

_JS = """
function showTab(n) {
    document.querySelectorAll('.level').forEach(function(el, i) {
        el.classList.toggle('active', i === n);
    });
    document.querySelectorAll('.tab-btn').forEach(function(el, i) {
        el.classList.toggle('active', i === n);
    });
}
"""


def build_html(thema, levels_html):
    tabs = ''.join(
        f'<button class="tab-btn{" active" if i == 0 else ""}" '
        f'onclick="showTab({i})">S{i + 1}</button>'
        for i in range(3)
    )
    levels = ''.join(
        f'<div class="level{" active" if i == 0 else ""}">{h}</div>'
        for i, h in enumerate(levels_html)
    )
    return (
        '<!DOCTYPE html>\n<html lang="de">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>Vorschau: {_esc(thema)}</title>\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n<body>\n'
        f'<h2>Vorschau: {_esc(thema)}</h2>\n'
        f'<div class="tabs">{tabs}</div>\n'
        f'{levels}\n'
        f'<script>{_JS}</script>\n'
        '</body>\n</html>'
    )

# ── R2 upload ─────────────────────────────────────────────────────────────────

def upload_r2(local_path, key):
    """Upload a single file to Cloudflare R2 via boto3 (S3-compatible)."""
    import boto3  # noqa: PLC0415

    access_key = os.environ.get('CF_R2_ACCESS_KEY_ID', '')
    secret_key = os.environ.get('CF_R2_SECRET_ACCESS_KEY', '')
    account_id = os.environ.get('CF_ACCOUNT_ID', '')
    bucket     = os.environ.get('CF_R2_BUCKET', '')
    public_url = os.environ.get('CF_R2_PUBLIC_URL', '').rstrip('/')

    missing = [
        k for k, v in [
            ('CF_R2_ACCESS_KEY_ID',     access_key),
            ('CF_R2_SECRET_ACCESS_KEY', secret_key),
            ('CF_ACCOUNT_ID',           account_id),
            ('CF_R2_BUCKET',            bucket),
        ] if not v
    ]
    if missing:
        raise SystemExit(f'Fehlende Umgebungsvariablen: {", ".join(missing)}')

    endpoint = f'https://{account_id}.r2.cloudflarestorage.com'
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='auto',
    )
    with open(local_path, 'rb') as fh:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=fh,
            ContentType='text/html; charset=utf-8',
            CacheControl='public, max-age=3600',
        )
    return f'{public_url}/{key}' if public_url else f'{endpoint}/{bucket}/{key}'

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Wissensfreund article HTML preview generator'
    )
    parser.add_argument('--thema',   required=True,
                        help='Wikipedia search term for image fetching')
    parser.add_argument('--artikel', required=True, type=Path,
                        help='Path to Wissensfreund article .md file')
    args = parser.parse_args()

    thema_slug = args.thema.lower()
    out_dir    = Path('output')
    out_dir.mkdir(exist_ok=True)
    out_file   = out_dir / f'preview_{thema_slug}.html'

    # 1. Fetch images (Steps 1–3)
    images = fetch_images(args.thema)

    # 2. Parse article markdown
    md_text     = args.artikel.read_text(encoding='utf-8')
    level_texts = parse_article(md_text)

    # 3. Render each level
    levels_html = [
        render_level(level_texts[0], [],          0),   # S1 — no images
        render_level(level_texts[1], images[:4],  1),   # S2 — images 0–3
        render_level(level_texts[2], images[4:8], 2),   # S3 — images 4–7
    ]

    # 4. Write HTML
    html_page = build_html(args.thema, levels_html)
    out_file.write_text(html_page, encoding='utf-8')
    print(f'[out] Written: {out_file}', file=sys.stderr)

    # 5. Upload to R2
    key = f'previews/preview_{thema_slug}.html'
    public_url = upload_r2(out_file, key)
    print(f'\nÖffentliche URL: {public_url}')


if __name__ == '__main__':
    main()
