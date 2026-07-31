#!/usr/bin/env python3
"""
render_review_comment_html.py
Interaktive HTML-Sichtungsdatei MIT Kommentarfeldern (Ersatz fuer den fragilen
Word-Kommentar-Rueckweg).

Gegenueber render_review_html.py zusaetzlich:
  - Bilder werden INLINE angezeigt (thumb_url), Hero markiert
  - Kommentarfeld pro Bild UND pro Artikel
  - localStorage: Kommentare ueberleben Reload/Schliessen (kein Datenverlust)
  - Export-Knopf: kopiert alle Kommentare in die Zwischenablage + laedt .txt herunter
    -> diese kleine Textdatei schickt der Nutzer zurueck (100 % zuverlaessig lesbar)

Usage:
    python scripts/render_review_comment_html.py --input articles/batch_new_20260708
Output: <input>/_review_kommentar.html
"""

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render_review_html as R  # bewaehrte Renderer-Bausteine wiederverwenden

e = getattr(R, "e", html.escape)
ROOT = Path(__file__).parent.parent

EXTRA_CSS = """
.image-row { display:flex; gap:14px; align-items:flex-start; padding:12px 0; border-top:1px solid #eee; }
.image-thumb img { max-width:240px; max-height:190px; border-radius:4px; border:1px solid #ddd; display:block; }
.image-thumb .noimg { width:240px; height:120px; display:flex; align-items:center; justify-content:center;
  background:#f0f0f0; color:#999; font-size:.8rem; border-radius:4px; text-align:center; padding:8px; }
.hero-badge { display:inline-block; background:#E65100; color:#fff; font-size:.7rem; font-weight:700;
  padding:2px 7px; border-radius:3px; margin-bottom:4px; font-family:sans-serif; }
.cmt-wrap { margin-top:6px; }
.cmt-label { font-family:sans-serif; font-size:.72rem; color:#c62828; font-weight:700; letter-spacing:.03em; }
textarea.cmt { width:100%; min-height:44px; margin-top:3px; font-family:sans-serif; font-size:.85rem;
  border:1.5px solid #f0b0b0; border-radius:4px; padding:6px 8px; resize:vertical; background:#fffdfd; }
textarea.cmt:focus { outline:none; border-color:#c62828; background:#fff; }
textarea.cmt.filled { border-color:#2e7d32; background:#f4fbf4; }
.article-cmt { margin:8px 0 4px; padding:12px 14px; background:#fff8f8; border:1.5px dashed #e0a0a0; border-radius:6px; }
#exportbar { position:fixed; right:18px; bottom:18px; z-index:9999; font-family:sans-serif; display:flex; gap:8px; }
#exportbar button { background:#c62828; color:#fff; border:none; border-radius:22px; padding:11px 18px;
  font-size:.9rem; font-weight:700; cursor:pointer; box-shadow:0 3px 10px rgba(0,0,0,.25); }
#exportbar button.sec { background:#455a64; }
#cmtcount { position:fixed; right:18px; bottom:64px; z-index:9999; font-family:sans-serif; font-size:.75rem;
  color:#555; background:#fff; padding:4px 10px; border-radius:12px; box-shadow:0 2px 6px rgba(0,0,0,.15); }
#modal { position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:10000; display:none; align-items:center; justify-content:center; }
#modal .box { background:#fff; max-width:680px; width:90%; max-height:80vh; border-radius:8px; padding:20px; display:flex; flex-direction:column; }
#modal textarea { width:100%; flex:1; min-height:340px; font-family:monospace; font-size:.8rem; }
#modal .row { display:flex; gap:8px; justify-content:flex-end; margin-top:10px; font-family:sans-serif; }
#modal button { padding:8px 14px; border-radius:5px; border:none; cursor:pointer; font-weight:700; }
"""


def _art_id(art: dict, index: int) -> str:
    m = art.get("meta", {})
    return str(m.get("id") or m.get("slug") or f"artikel_{index}")


def _cmt(key: str, label: str = "Kommentar") -> str:
    return f"""
    <div class="cmt-wrap">
      <div class="cmt-label">{e(label)}</div>
      <textarea class="cmt" data-key="{e(key)}" placeholder="hier tippen …"></textarea>
    </div>"""


def render_images_with_comments(images: list, art_id: str) -> str:
    if not images:
        return f'<div class="images-section"><div class="images-heading">Bilder (0)</div></div>'
    rows = []
    for img in images:
        idx      = img.get("index", "?")
        filename = img.get("filename", "")
        alt      = img.get("alt", "")
        caption  = img.get("caption", "")
        meta_str = " · ".join(p for p in [img.get("license", ""), img.get("license_author", "")] if p)
        thumb    = img.get("thumb_url", "")
        is_hero  = img.get("is_hero", False)

        if thumb:
            thumb_html = f'<img src="{e(thumb)}" loading="lazy" alt="{e(alt)}">'
        else:
            thumb_html = f'<div class="noimg">kein thumb_url<br>{e(filename)}</div>'
        hero_html = '<div class="hero-badge">★ HERO</div>' if is_hero else ""
        cap_html  = f'<div class="image-alt">{e(caption)}</div>' if caption else ""

        rows.append(f"""
    <div class="image-row">
      <div class="image-thumb">{hero_html}{thumb_html}</div>
      <div class="image-info">
        <div class="image-filename">[{e(str(idx))}] {e(filename)}</div>
        <div class="image-alt">{e(alt)}</div>
        {cap_html}
        <div class="image-meta">{e(meta_str)}</div>
        {_cmt(f"{art_id}::bild{idx}", "Kommentar zu diesem Bild")}
      </div>
    </div>""")
    return f"""
  <div class="images-section">
    <div class="images-heading">Bilder ({len(images)})</div>
    {"".join(rows)}
  </div>"""


def render_article(art: dict, index: int) -> str:
    meta     = art.get("meta", {})
    sections = art.get("sections", [])
    images   = art.get("images", [])
    quiz     = art.get("quiz", {})
    art_id   = _art_id(art, index)

    title    = meta.get("title", "Ohne Titel")
    subtitle = meta.get("subtitle", "")
    emoji    = meta.get("emoji", "")
    age      = meta.get("age_level", "?")

    chips = [f'<span class="chip chip-age">Stufe {e(str(age))}</span>',
             f'<span class="chip chip-method">{e(art_id)}</span>']
    subtitle_html = f'<div class="article-subtitle">{e(subtitle)}</div>' if subtitle else ""

    header_html = f"""
  <div class="article-header">
    <div class="article-emoji">{e(emoji)}</div>
    <div class="article-title">{e(title)}</div>
    {subtitle_html}
    <div class="article-chips">{"".join(chips)}</div>
  </div>"""

    sections_html = "".join(R.render_section(sec, images) for sec in sections)
    lektorat_html = R.render_lektorat(art.get("pruefbericht", {}))
    art_cmt = f'<div class="article-cmt">{_cmt(f"{art_id}::artikel", "Gesamt-Kommentar zu diesem Artikel (Text, Ton, Länge …)")}</div>'

    return f"""
<div class="article-wrapper" id="article-{index}">
  {header_html}
  {art_cmt}
  {sections_html}
  {R.render_quiz(quiz)}
  {lektorat_html}
  {render_images_with_comments(images, art_id)}
  {R.render_footer(meta)}
</div>"""


def render_html(articles: list, input_dir: Path) -> str:
    total  = len(articles)
    run    = input_dir.name
    titles = ", ".join(_art_id(a, i) for i, a in enumerate(articles))
    bodies = "".join(render_article(art, i) for i, art in enumerate(articles))

    js = """
<script>
const RUN = %RUN%;
const SKEY = "wf_review_" + RUN;
function load() {
  let data = {};
  try { data = JSON.parse(localStorage.getItem(SKEY) || "{}"); } catch(e) {}
  document.querySelectorAll("textarea.cmt").forEach(t => {
    const k = t.dataset.key;
    if (data[k]) t.value = data[k];
    mark(t);
  });
  count();
}
function mark(t){ t.classList.toggle("filled", t.value.trim().length>0); }
function save() {
  const data = {};
  document.querySelectorAll("textarea.cmt").forEach(t => {
    if (t.value.trim()) data[t.dataset.key] = t.value;
  });
  localStorage.setItem(SKEY, JSON.stringify(data));
  count();
}
function count(){
  const n = [...document.querySelectorAll("textarea.cmt")].filter(t=>t.value.trim()).length;
  document.getElementById("cmtcount").textContent = n + " Kommentar(e)";
}
function buildText(){
  let out = "# Wissensfreund Review — " + RUN + "\\n\\n";
  document.querySelectorAll(".article-wrapper").forEach(w => {
    const cmts = [...w.querySelectorAll("textarea.cmt")].filter(t=>t.value.trim());
    if (!cmts.length) return;
    const title = w.querySelector(".article-title")?.textContent?.trim() || "";
    const aid = w.querySelector(".chip-method")?.textContent?.trim() || "";
    out += "## " + aid + "  (" + title + ")\\n";
    cmts.forEach(t => {
      let loc = t.dataset.key.split("::")[1] || "";
      loc = loc.replace("artikel","ARTIKEL").replace("bild","BILD ");
      // Dateiname des Bildes mitgeben
      let extra = "";
      const info = t.closest(".image-info");
      if (info) extra = " " + (info.querySelector(".image-filename")?.textContent?.trim() || "");
      out += "  [" + loc + extra + "] " + t.value.trim().replace(/\\n/g," ") + "\\n";
    });
    out += "\\n";
  });
  return out;
}
function openExport(){
  const txt = buildText();
  document.getElementById("modaltext").value = txt;
  document.getElementById("modal").style.display = "flex";
  // zusaetzlich Download anbieten
}
function download(){
  const blob = new Blob([document.getElementById("modaltext").value], {type:"text/plain;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "review_" + RUN + "_kommentare.txt";
  a.click();
}
async function copyClip(){
  const t = document.getElementById("modaltext");
  t.select();
  try { await navigator.clipboard.writeText(t.value); alert("In Zwischenablage kopiert!"); }
  catch(e){ document.execCommand("copy"); alert("Kopiert (Fallback)."); }
}
document.addEventListener("DOMContentLoaded", () => {
  load();
  document.querySelectorAll("textarea.cmt").forEach(t => {
    t.addEventListener("input", () => { mark(t); save(); });
  });
});
</script>""".replace("%RUN%", json.dumps(run))

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wissensfreund Review (Kommentar) — {e(run)} ({total} Artikel)</title>
  <style>{R.CSS}{EXTRA_CSS}</style>
</head>
<body>
  <div style="max-width:680px;margin:0 auto 24px;font-family:sans-serif;font-size:0.82rem;color:#555">
    <b>Sichtung mit Kommentaren</b> · {total} Artikel: {e(titles)}<br>
    Tippe Kommentare in die roten Felder (unter jedem Bild + pro Artikel). Sie werden automatisch
    im Browser gespeichert. Zum Schluss unten rechts <b>„Kommentare exportieren"</b> → kopieren
    oder als .txt herunterladen und mir schicken.
  </div>
  {bodies}
  <div id="cmtcount">0 Kommentar(e)</div>
  <div id="exportbar">
    <button onclick="openExport()">Kommentare exportieren ▸</button>
  </div>
  <div id="modal">
    <div class="box">
      <div style="font-family:sans-serif;font-weight:700;margin-bottom:8px">Deine Kommentare</div>
      <textarea id="modaltext" readonly></textarea>
      <div class="row">
        <button class="sec" style="background:#455a64;color:#fff" onclick="document.getElementById('modal').style.display='none'">Schließen</button>
        <button style="background:#455a64;color:#fff" onclick="download()">⬇ .txt herunterladen</button>
        <button style="background:#c62828;color:#fff" onclick="copyClip()">⧉ Kopieren</button>
      </div>
    </div>
  </div>
  {js}
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Artikel-JSONs → interaktive HTML-Sichtung mit Kommentarfeldern")
    parser.add_argument("--input", type=Path, default=ROOT / "articles" / "batch_new_20260708",
                        help="Ordner mit Artikel-JSONs")
    parser.add_argument("--output", type=Path, default=None, help="Ausgabepfad (Default: <input>/_review_kommentar.html)")
    args = parser.parse_args()

    input_dir: Path = args.input.resolve()
    if not input_dir.is_dir():
        print(f"Fehler: Ordner nicht gefunden: {input_dir}"); raise SystemExit(1)

    json_files = sorted(f for f in input_dir.glob("*.json")
                        if not f.name.startswith("_") and not f.stem.endswith("_report"))
    if not json_files:
        print(f"Keine *.json in {input_dir}"); raise SystemExit(1)

    articles = []
    for jf in json_files:
        try:
            articles.append(json.loads(jf.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"  Übersprungen ({jf.name}): {exc}")

    articles.sort(key=lambda a: (a.get("meta", {}).get("title", "").lower(),
                                 a.get("meta", {}).get("age_level", 0)))

    out_path = args.output or (input_dir / "_review_kommentar.html")
    out_path.write_text(render_html(articles, input_dir), encoding="utf-8")
    print(f"Gespeichert: {out_path}  ({len(articles)} Artikel)")


if __name__ == "__main__":
    main()
