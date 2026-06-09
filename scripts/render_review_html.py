#!/usr/bin/env python3
"""
render_review_html.py
Wandelt generierte Artikel-JSONs in eine druckfertige HTML-Sichtungsdatei um.

Usage:
    python scripts/render_review_html.py
    python scripts/render_review_html.py --input articles/test_grounded
Output: <input>/_review.html
"""

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Box-Konfiguration ────────────────────────────────────────────────────────

BOX_CONFIG = {
    "wow":       {"label": "Wusstest du?",   "bg": "#FFFDE7", "border": "#F9A825", "label_color": "#F57F17"},
    "fakt":      {"label": "Info",            "bg": "#E3F2FD", "border": "#1976D2", "label_color": "#1565C0"},
    "stimmt_das":{"label": "Stimmt das?",    "bg": "#F3E5F5", "border": "#8E24AA", "label_color": "#6A1B9A"},
    "warnung":   {"label": "Wichtig",         "bg": "#FFF3E0", "border": "#EF6C00", "label_color": "#E65100"},
}
BOX_DEFAULT = {"label": "Box", "bg": "#F5F5F5", "border": "#9E9E9E", "label_color": "#616161"}


# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 16px;
  line-height: 1.65;
  color: #1a1a1a;
  background: #f4f4f0;
  padding: 32px 16px;
}

.article-wrapper {
  max-width: 680px;
  margin: 0 auto 60px;
  background: white;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0,0,0,.1);
  padding: 48px 56px 40px;
  page-break-after: always;
}

/* Header */
.article-header { margin-bottom: 32px; border-bottom: 2px solid #e0e0e0; padding-bottom: 20px; }
.article-emoji  { font-size: 2.8rem; line-height: 1; }
.article-title  { font-size: 2.2rem; font-weight: 700; margin-top: 6px; line-height: 1.2; }
.article-subtitle { font-size: 1.05rem; color: #555; margin-top: 4px; font-style: italic; }

.article-chips  { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-block; padding: 3px 12px; border-radius: 20px;
  font-family: sans-serif; font-size: 0.78rem; font-weight: 600;
}
.chip-age   { background: #E8F5E9; color: #2E7D32; border: 1px solid #A5D6A7; }
.chip-method{ background: #EDE7F6; color: #4527A0; border: 1px solid #CE93D8; }
.chip-flag  { background: #FFEBEE; color: #B71C1C; border: 1px solid #EF9A9A; }

.article-meta-line {
  margin-top: 10px;
  font-family: sans-serif; font-size: 0.78rem; color: #777;
}

/* Sections */
.section      { margin-bottom: 28px; }
.section-heading {
  font-size: 1.25rem; font-weight: 700; margin-bottom: 10px;
  padding-bottom: 4px; border-bottom: 1px solid #e8e8e8;
}

/* Sentences */
.sentences    { margin-bottom: 8px; }
.sentence     { margin-bottom: 6px; }
.sentence .img-ref {
  display: inline-block; margin-left: 6px;
  font-family: sans-serif; font-size: 0.68rem;
  color: #999; vertical-align: super;
}

/* Boxes */
.box {
  margin: 16px 0;
  padding: 14px 18px;
  border-left: 4px solid;
  border-radius: 0 4px 4px 0;
}
.box-label {
  font-family: sans-serif; font-size: 0.75rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .06em;
  margin-bottom: 8px;
}
.box-text { font-size: 0.95rem; }
.box-reveal {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed;
  font-size: 0.9rem;
}
.box-reveal-label {
  font-family: sans-serif; font-size: 0.72rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em;
  margin-bottom: 4px; opacity: .7;
}

/* Tables */
.article-table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.9rem; }
.article-table th {
  background: #37474F; color: white; padding: 8px 12px;
  text-align: left; font-family: sans-serif;
}
.article-table td { padding: 7px 12px; border-bottom: 1px solid #E0E0E0; }
.article-table tr:last-child td { border-bottom: none; }
.article-table tr:nth-child(even) td { background: #FAFAFA; }

/* Quiz */
.quiz-section { margin-top: 36px; padding-top: 24px; border-top: 2px solid #e0e0e0; }
.quiz-heading {
  font-family: sans-serif; font-size: 0.85rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .08em;
  color: #555; margin-bottom: 18px;
}
.quiz-question { margin-bottom: 20px; }
.quiz-q-text  { font-weight: 700; margin-bottom: 8px; }
.quiz-options { list-style: none; padding-left: 0; }
.quiz-option  { padding: 4px 0 4px 12px; font-size: 0.95rem; }
.quiz-option.correct {
  background: #E8F5E9; border-left: 3px solid #43A047;
  padding-left: 9px; border-radius: 0 3px 3px 0;
  font-weight: 600; color: #2E7D32;
}
.quiz-option .opt-key { font-family: monospace; font-weight: 700; margin-right: 6px; }

/* Images list */
.images-section {
  margin-top: 32px; padding-top: 20px; border-top: 1px solid #e0e0e0;
}
.images-heading {
  font-family: sans-serif; font-size: 0.85rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .08em;
  color: #555; margin-bottom: 12px;
}
.image-row { display: flex; gap: 12px; margin-bottom: 14px; font-size: 0.82rem; }
.image-idx {
  flex-shrink: 0; width: 24px; height: 24px;
  background: #37474F; color: white;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-family: sans-serif; font-size: 0.7rem; font-weight: 700;
}
.image-info { flex: 1; }
.image-filename { font-family: monospace; font-weight: 600; color: #1565C0; word-break: break-all; }
.image-alt  { color: #444; margin-top: 2px; font-style: italic; }
.image-meta { color: #888; margin-top: 2px; }

/* Footer */
.article-footer {
  margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0;
  font-family: sans-serif; font-size: 0.76rem; color: #888;
}
.footer-label { font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.footer-companions { margin-top: 4px; }
.footer-meta { margin-top: 6px; }

/* Print */
@media print {
  body { background: white; padding: 0; }
  .article-wrapper {
    box-shadow: none; border-radius: 0;
    padding: 20mm 18mm; max-width: 100%;
    margin: 0;
  }
  .box { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .quiz-option.correct { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .image-idx { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .article-table th { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


# ── HTML-Helfer ───────────────────────────────────────────────────────────────

def e(text: str) -> str:
    """HTML-escape."""
    return html.escape(str(text), quote=False)


def render_box(box: dict) -> str:
    btype  = box.get("type", "")
    cfg    = BOX_CONFIG.get(btype, BOX_DEFAULT)
    text   = box.get("text", "")
    reveal = box.get("reveal_text", "")
    mode   = box.get("reveal_mode", "")

    reveal_html = ""
    if reveal:
        reveal_html = f"""
      <div class="box-reveal" style="border-top-color:{cfg['border']}">
        <div class="box-reveal-label">Auflösung{' (' + e(mode) + ')' if mode else ''}</div>
        {e(reveal)}
      </div>"""

    return f"""
    <div class="box" style="background:{cfg['bg']};border-left-color:{cfg['border']}">
      <div class="box-label" style="color:{cfg['label_color']}">{e(cfg['label'])}</div>
      <div class="box-text">{e(text)}</div>{reveal_html}
    </div>"""


def render_table(table: dict) -> str:
    if not table:
        return ""
    headers = table.get("headers", [])
    rows    = table.get("rows", [])
    head_html = "".join(f"<th>{e(h)}</th>" for h in headers)
    rows_html = ""
    for row in rows:
        cells = "".join(f"<td>{e(str(cell))}</td>" for cell in row)
        rows_html += f"<tr>{cells}</tr>\n"
    return f"""
    <table class="article-table">
      <thead><tr>{head_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""


def render_section(sec: dict, images: list) -> str:
    heading   = sec.get("heading", "")
    sentences = sec.get("sentences", [])
    boxes     = sec.get("boxes", [])
    table     = sec.get("table")

    # Sentences
    sent_parts = []
    for s in sentences:
        text      = e(s.get("text", ""))
        img_index = s.get("img_index", -1)
        ref_html  = ""
        if img_index is not None and img_index >= 0:
            # Show short filename reference
            img_fn = ""
            if img_index < len(images):
                img_fn = images[img_index].get("filename", "")
                img_fn = img_fn[:30] + ("…" if len(img_fn) > 30 else "")
            ref_html = f'<span class="img-ref">[Bild {img_index}: {e(img_fn)}]</span>'
        sent_parts.append(f'<div class="sentence">{text}{ref_html}</div>')

    # Boxes (inline after sentences)
    box_parts = [render_box(b) for b in boxes]

    table_html = render_table(table) if table else ""

    return f"""
  <div class="section">
    <div class="section-heading">{e(heading)}</div>
    <div class="sentences">{"".join(sent_parts)}</div>
    {"".join(box_parts)}
    {table_html}
  </div>"""


def render_quiz(quiz: dict) -> str:
    if not quiz:
        return ""
    questions = quiz.get("questions", [])
    if not questions:
        return ""

    q_parts = []
    for q in questions:
        text    = e(q.get("text", ""))
        correct = q.get("correct_key", "")
        opts    = []
        for opt in q.get("options", []):
            key     = opt.get("key", "")
            opt_txt = e(opt.get("text", ""))
            css     = ' correct' if key == correct else ''
            opts.append(
                f'<li class="quiz-option{css}">'
                f'<span class="opt-key">{e(key)}.</span>{opt_txt}</li>'
            )
        q_parts.append(f"""
    <div class="quiz-question">
      <div class="quiz-q-text">{text}</div>
      <ul class="quiz-options">{"".join(opts)}</ul>
    </div>""")

    return f"""
  <div class="quiz-section">
    <div class="quiz-heading">Quiz</div>
    {"".join(q_parts)}
  </div>"""


def render_images(images: list) -> str:
    if not images:
        return ""
    rows = []
    for img in images:
        idx      = img.get("index", "?")
        filename = img.get("filename", "")
        alt      = img.get("alt", "")
        caption  = img.get("caption", "")
        license_ = img.get("license", "")
        author   = img.get("license_author", "")
        meta_parts = [p for p in [license_, author] if p]
        meta_str   = " · ".join(meta_parts)

        caption_html = f'<div class="image-alt">{e(caption)}</div>' if caption else ""
        rows.append(f"""
    <div class="image-row">
      <div class="image-idx">{e(str(idx))}</div>
      <div class="image-info">
        <div class="image-filename">{e(filename)}</div>
        <div class="image-alt">{e(alt)}</div>
        {caption_html}
        <div class="image-meta">{e(meta_str)}</div>
      </div>
    </div>""")

    return f"""
  <div class="images-section">
    <div class="images-heading">Bilder ({len(images)})</div>
    {"".join(rows)}
  </div>"""


def render_footer(meta: dict) -> str:
    companions   = meta.get("grounding_companions", [])
    word_count   = meta.get("word_count")
    generated_at = meta.get("generated_at", "")
    method       = meta.get("generation_method", "")
    source_url   = meta.get("source_wikipedia_url", "")

    comp_html = ""
    if companions:
        comp_list = ", ".join(e(c) for c in companions)
        comp_html = f'<div class="footer-companions"><span class="footer-label">Quellen:</span> Primär + {comp_list}</div>'
    elif source_url:
        comp_html = f'<div class="footer-companions"><span class="footer-label">Quelle:</span> {e(source_url)}</div>'

    meta_items = []
    if word_count:
        meta_items.append(f"{word_count} Wörter")
    if method:
        meta_items.append(f"method={method}")
    if generated_at:
        meta_items.append(f"generiert {generated_at[:10]}")
    meta_html = ""
    if meta_items:
        meta_html = f'<div class="footer-meta">{" · ".join(meta_items)}</div>'

    return f"""
  <div class="article-footer">
    {comp_html}
    {meta_html}
  </div>"""


def render_article(art: dict, index: int) -> str:
    meta     = art.get("meta", {})
    sections = art.get("sections", [])
    images   = art.get("images", [])
    quiz     = art.get("quiz", {})

    # Header
    title    = meta.get("title", "Ohne Titel")
    subtitle = meta.get("subtitle", "")
    emoji    = meta.get("emoji", "")
    age      = meta.get("age_level", "?")
    method   = meta.get("generation_method", "")
    flag     = meta.get("review_flag", False)

    chips = [f'<span class="chip chip-age">Stufe {e(str(age))}</span>']
    if method:
        chips.append(f'<span class="chip chip-method">{e(method)}</span>')
    if flag:
        chips.append('<span class="chip chip-flag">⚠ Review-Flag</span>')

    subtitle_html = f'<div class="article-subtitle">{e(subtitle)}</div>' if subtitle else ""

    header_html = f"""
  <div class="article-header">
    <div class="article-emoji">{e(emoji)}</div>
    <div class="article-title">{e(title)}</div>
    {subtitle_html}
    <div class="article-chips">{"".join(chips)}</div>
    <div class="article-meta-line">
      {e(meta.get("category_top", ""))} / {e(meta.get("category_sub", ""))}
      · {e(meta.get("id", ""))}
    </div>
  </div>"""

    sections_html = "".join(render_section(sec, images) for sec in sections)

    return f"""
<div class="article-wrapper" id="article-{index}">
  {header_html}
  {sections_html}
  {render_quiz(quiz)}
  {render_images(images)}
  {render_footer(meta)}
</div>"""


def render_html(articles: list[dict], input_dir: Path) -> str:
    total   = len(articles)
    titles  = ", ".join(a.get("meta", {}).get("id", "?") for a in articles)
    bodies  = "".join(render_article(art, i) for i, art in enumerate(articles))

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wissensfreund Sichtung — {e(str(input_dir.name))} ({total} Artikel)</title>
  <style>{CSS}</style>
</head>
<body>
  <div style="max-width:680px;margin:0 auto 32px;font-family:sans-serif;font-size:0.8rem;color:#888">
    Sichtungs-Datei · {total} Artikel: {e(titles)}
  </div>
  {bodies}
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Artikel-JSONs → HTML-Sichtungsdatei")
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "articles" / "test_grounded",
        help="Ordner mit Artikel-JSONs (Default: articles/test_grounded)",
    )
    args = parser.parse_args()

    input_dir: Path = args.input.resolve()
    if not input_dir.is_dir():
        print(f"Fehler: Ordner nicht gefunden: {input_dir}")
        raise SystemExit(1)

    json_files = sorted(
        f for f in input_dir.glob("*.json")
        if not f.name.startswith("_") and not f.stem.endswith("_report")
    )
    if not json_files:
        print(f"Keine *.json-Dateien in {input_dir}")
        raise SystemExit(1)

    articles = []
    for jf in json_files:
        try:
            art = json.loads(jf.read_text(encoding="utf-8"))
            articles.append(art)
        except Exception as exc:
            print(f"  Übersprungen ({jf.name}): {exc}")

    print(f"Lese {len(articles)} Artikel aus {input_dir} ...")

    out_path = input_dir / "_review.html"
    out_path.write_text(render_html(articles, input_dir), encoding="utf-8")
    print(f"Gespeichert: {out_path}")


if __name__ == "__main__":
    main()
