#!/usr/bin/env python3
"""story_mode_v2.py — Wissensgeschichte (4–8 J.) MIT Bildern.

Liest den Stage-1-Checkpoint (Quelle + Companions + Vision-Pool) und erzeugt je
Thema und Modell (Sonnet vs Flash 3.5) eine bild-bewusste Geschichte:
  - Das Modell kennt VOR dem Schreiben die verfügbaren Bilder und setzt Inline-
    Marker [BILD:N], wo die Geschichte ein Bild WIRKLICH zeigt (garantiert
    angezeigt; keine erfundenen Bildverweise).
  - Es wählt ein Hero-Bild und schreibt zu JEDEM Bild einen beschreibenden,
    kindgerechten Alt-Titel + Caption (Originaltitel + Beschreibung + Alter).
  - Rest des Pools (S1 ungenutzt + S2 „zum Weiterschauen") → Galerie am Ende.

  python -X utf8 scripts/story_mode_v2.py \
      --checkpoint articles/story_v2_20260710/stage1_checkpoint.json \
      --out-dir "C:/Users/Andreas/Desktop" --suffix 20260710
"""
from __future__ import annotations
import argparse, html, json, re, sys, time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemini_client

COMP_CAP = 4000          # Companion-Zeichen kappen
WMIN, WMAX = 600, 720    # Wortziel Geschichte

# ── Prompt ────────────────────────────────────────────────────────────────────
STORY_SYSTEM = """Du schreibst eine WISSENSGESCHICHTE für Kinder von etwa 4 bis 8 Jahren — wie eine kurze Hörspiel-Folge oder eine Geschichte aus der Sendung mit der Maus. Du verpackst echtes Wissen in eine warme Geschichte zum Vorlesen. Sie ist für die ganze Spanne 4 bis 8 Jahre. Schreib so, dass ein Vierjähriger mühelos folgen kann und einem Achtjährigen nicht langweilig wird: klar und greifbar für die Kleinen, mit genug Gehalt für die Größeren.

SPRACHE & TON:
- Klare, nicht zu lange Sätze — meist bis etwa 15 Wörter, sparsames Passiv, ein Gedanke pro Satz. Ruhig erzählt, nicht abgehackt. Ein klarer Anfang, eine kleine Entdeckungsreise, ein ruhiger Schluss.
- Nüchtern und klar: Adjektive nur, wo sie eine belegte Eigenschaft schärfen („der große Wal"). KEINE stimmungsmalenden Zusätze, die eine ungedeckte Bedeutung eintragen („sanfte Riesen", „schlaue Töne", „singt für seine Familie").
- Anschaulich, nicht hinzudichtend: Vergleiche und Bilder machen belegte Fakten greifbar, fügen aber nichts hinzu — keine erfundenen Gefühle oder Absichten, keine ausgemalten Details, keine Verstärker über die Quelle hinaus. Ein Vergleich färbt die Sprache; er verändert die Tatsache nicht.
- Erkläre schwierige Wörter beiläufig in der Geschichte, nie als Lexikon-Einschub.

GREIFBAR MACHEN (die Kleinen mitnehmen):
- Nutze greifbare Vergleiche aus der Kinderwelt (so groß wie ein Auto, so schwer wie ein Bus) — aber der Vergleich muss STIMMEN. Prüfe jede Größe im Kopf: ein Kinderarm ist etwa so lang wie ein großes Buch, keine zehn Zentimeter. Lieber gar kein Vergleich als ein falscher.
- Keine großen oder abstrakten Zahlen. Eine Zahl nur, wenn sie klein und zum Staunen ist.
- Bei abstrakten Themen mach das Schwer-Vorstellbare greifbar, indem du es an Bekanntem verankerst, bevor du ins Größere gehst. Eine kleine Merkhilfe oder ein Reim darf ruhig helfen.

FIGUREN & ERZÄHLROLLEN (klare Trennung — trägt auch die spätere Vertonung):
- Erzähl mit ZWEI Figuren: einem neugierigen Kind (staunt, fragt, reagiert) und einer erwachsenen Person, die sich auskennt (z. B. Opa, Oma, eine Pflegerin) und die alles erklärt. Gib beiden einfache Namen.
- Der ERZÄHLER beschreibt NUR die unmittelbare Umgebung und was die beiden gerade tun und sehen. Er erklärt nichts und trägt kein Sachwissen bei.
- Alles Erklärende — jedes Warum und Wie, jede Zahl, jeder Fakt — kommt von der erwachsenen Person im Gespräch. Das Kind bringt Fragen und Staunen.
- Direkte Ansprache an das zuhörende Kind („Weißt du was?") ist allein der erwachsenen Person vorbehalten, nie dem Erzähler.
- Plausibilität: Das Kind bemerkt nur, was wirklich zu sehen ist. Was man nicht sehen kann (die hohle Struktur eines Haars, die Haut unter dem Fell, etwas weit Entferntes), erklärt die erwachsene Person, die es weiß — es wird nicht „gesehen".

WAS DU ERZÄHLST (Auswahl & Tiefe):
- Sei INHALTSREICH: Das Kind soll aus der Geschichte richtig viel echtes Wissen mitnehmen. Schöpfe den Quellenstoff aus und bringe entlang des roten Fadens mehrere gedeckte Fakten unter — zu jedem Schlüsselmoment das Was, das Warum UND das Wie. „Tiefe" heißt reich und gründlich erzählt, nicht dünn oder inhaltsarm. Erreiche das Wortziel mit echtem Inhalt aus der Quelle, nicht mit Füllsätzen oder ausgemaltem Rahmen.
- Tiefe vor Breite meint: die gewählten Aspekte gründlich entwickeln (mehrere Fakten je Szene, jeweils mit Warum und Wie), statt viele Aspekte nur anzureißen. Verboten ist die zusammenhanglose Faktenliste — nicht der Informationsgehalt.
- Folge einem roten Faden statt einer lückenlosen Zeitleiste, aber fülle diesen Faden mit reichem, gedecktem Stoff. Das berühmteste, ikonische Beispiel muss dabei sein.
- Wähle bei Daten und Namen die GRÖBSTE Angabe, die noch reicht (Jahreszahl statt Datum, Rolle statt Name), außer der Tag oder Name trägt die Geschichte wirklich. Meide lange Namens- oder Länder-Aufzählungen ohne eigenen Reiz.
- Bei ernsten Themen (Krieg, Tod): konkrete, ehrliche Erfahrung, aber ANGSTFREI — keine Opferzahlen, keine expliziten Details, kein Ausmalen; für die Kleinsten eher andeuten. Ende friedlich. Kein verharmlosendes Wort für etwas Ernstes.

BILDER (du kennst sie VOR dem Schreiben):
- Dir liegt eine Liste GEEIGNETER BILDER vor (Index, Originaltitel, was zu sehen ist). Wenn deine Geschichte an einer Stelle etwas beschreibt, das eines dieser Bilder WIRKLICH zeigt, setze dort den Marker [BILD:N] mit dem passenden Index — direkt hinter dem Satz, zu dem das Bild gehört.
- Setze einen Marker NUR, wenn ein Bild aus der Liste das Gezeigte wirklich abbildet. Erfinde NIEMALS einen Bildverweis und schreibe nie „auf diesem Bild siehst du …", wenn es kein passendes Bild gibt. Kein Bild in der Liste passt? Dann erzähl einfach ohne Marker weiter.
- Nicht jeder Absatz braucht ein Bild. Nutze über die ganze Geschichte verteilt etwa 5 bis 7 Bilder, sofern passende da sind. Verwende jeden Index höchstens einmal.
- Wähle EIN Hero-Bild (hero_index) aus der Liste GEEIGNETER BILDER, das das Hauptthema am eindrucksvollsten zeigt.

ALT-TITEL & BILDUNTERSCHRIFTEN (zu JEDEM gelieferten Bild — geeignete UND Galerie):
- alt = ein kurzer, beschreibender, kindgerechter Titel (ein Satzfragment, kein ganzer Satz mit Punkt). Nenne den EIGENNAMEN oder ORT aus dem Originaltitel, wenn er erkennbar ist (z. B. „Der Vulkan Teide auf Teneriffa", „Die Mona Lisa von Leonardo da Vinci"). Ist kein Name/Ort erkennbar, ein knapper Sachtitel („Fließende Lava").
- caption = eine kurze, kindgerechte Bildunterschrift (ein Satz).
- Beschreibe in alt und caption NUR, was laut „zu sehen" WIRKLICH im Bild ist — erfinde keine Details aus dem Thema, die im Bild gar nicht sichtbar sind.

DIE EISERNE REGEL FÜR WISSEN (unverhandelbar):
- Der GESCHICHTEN-RAHMEN ist erfunden und DARF erfunden sein: die Figur, ihre Gefühle, ihre Fragen, der Schauplatz, die Dialoge.
- ABER JEDE Aussage über die ECHTE Welt — was das Thema ist, wie etwas entsteht, was passiert, jede Zahl, jeder Name, jeder Ort — muss aus dem gelieferten QUELLTEXT stammen. Erfinde NIEMALS einen Fakt. Was die Quelle nicht sagt, kommt nicht vor.

FORMAT: Antworte NUR als JSON nach dem vorgegebenen Schema: titel, story_markdown (Fließtext in Absätzen, mit [BILD:N]-Markern), hero_index, bilder (Liste je Index mit alt + caption)."""

STORY_SCHEMA = {
    "type": "object",
    "required": ["titel", "story_markdown", "hero_index", "bilder"],
    "properties": {
        "titel":          {"type": "string"},
        "story_markdown": {"type": "string"},
        "hero_index":     {"type": "integer"},
        "bilder": {"type": "array", "items": {
            "type": "object",
            "required": ["index", "alt", "caption"],
            "properties": {
                "index":   {"type": "integer"},
                "alt":     {"type": "string"},
                "caption": {"type": "string"}}}},
    },
}


def _orig_title(img: dict) -> str:
    """Lesbarer Commons-Originaltitel (Eigenname/Ort) aus wikimedia_id/filename."""
    t = (img.get("wikimedia_id") or img.get("filename") or "").strip()
    if t.lower().startswith("file:"):
        t = t[5:]
    t = re.sub(r"\.(jpe?g|png|gif|svg|tiff?|webp)$", "", t, flags=re.I)
    return t.replace("_", " ").strip()


def _src(filename: str) -> str:
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=420"


# ── Generierung ─────────────────────────────────────────────────────────────
def _call_json(model: str, system: str, schema: dict, body: str,
               max_tokens: int = 8192, retries: int = 4):
    """JSON-Call an Sonnet (Claude) oder Flash (Gemini), mit 503/429-Backoff."""
    for attempt in range(1, retries + 1):
        try:
            if model.startswith("claude"):
                import claude_client
                d = claude_client.call_claude_json(
                    system, body, schema, model=model,
                    max_tokens=max_tokens, call_name="story_v2")
                return d or {}
            raw = gemini_client.call_gemini(
                system, body, model=model,
                response_mime_type="application/json", response_schema=schema,
                call_name="story_v2")
            return json.loads(raw)
        except Exception as e:
            msg = str(e)[:120]
            transient = any(t in msg for t in ("503", "429", "overloaded",
                            "UNAVAILABLE", "RESOURCE_EXHAUSTED", "deadline", "timeout"))
            if attempt == retries or not transient:
                raise
            wait = min(60, 8 * attempt)
            print(f"      {model}: transient ({msg[:50]}) — retry {attempt}/{retries} in {wait}s")
            time.sleep(wait)


def _source_block(thema: str, td: dict) -> str:
    """Quelltext (Primär + Companions gekappt) — geteilt von Story-Gen und Lektorat."""
    src = [f"QUELLTEXT — HAUPTTHEMA {thema}:\n{td.get('primary_text','')}"]
    for name, txt in (td.get("companion_texts") or {}).items():
        src.append(f"\nQUELLTEXT — BEGLEITARTIKEL {name}:\n{txt[:COMP_CAP]}")
    return "\n".join(src)


def _cross_model(gen_model: str) -> str:
    """Kreuz-Prüfung: Sonnet-Story → Flash prüft; Flash-Story → Sonnet prüft."""
    return "gemini-3.5-flash" if gen_model.startswith("claude") else "claude-sonnet-5"


# ── Lektorat / Beleg-Pass ────────────────────────────────────────────────────
LEKTORAT_SYSTEM = """Du bist Lektor und Faktenprüfer für eine Kinder-WISSENSGESCHICHTE (4–8 Jahre). Du bekommst den QUELLTEXT (Wikipedia) und die GESCHICHTE. Prüfe JEDE Aussage über die ECHTE Welt streng gegen den Quelltext und greife so WENIG wie möglich ein.

WAS DU PRÜFST:
- Jeder Sachfakt (was etwas ist, wie es entsteht, jede Zahl, jeder Name, jeder Ort, jede Größe) muss durch den Quelltext gedeckt sein.
- Der erfundene RAHMEN (Figuren, ihre Namen, Gefühle, Fragen, Dialoge, Schauplatz) ist erlaubt und wird NICHT geprüft — auch nicht die kindgerechte Erzählweise.

WAS DU KORRIGIERST (minimal, nur das sachlich Falsche/Ungedeckte):
- Nicht gedeckter Fakt (steht so nicht in der Quelle) → streichen oder auf eine gedeckte Aussage zurückführen.
- Falscher Fakt (widerspricht der Quelle, falsche Zahl/falscher Name) → auf den Quellwert korrigieren.
- Überschuss/Übertreibung (z. B. „fast drei Jahre", wenn die Quelle „bis zu 2,5 Jahre" sagt; ein Größenvergleich, der nicht stimmt) → auf das gedeckte Maß zurücknehmen.
Fasse gute, gedeckte Prosa NICHT an. Ändere Ton, Figuren, Aufbau und Bildbezüge nicht. Erfinde selbst keine neuen Fakten.

FÜR JEDEN EINGRIFF gib:
- original: der EXAKTE, wörtliche Textausschnitt aus der Geschichte, den du ersetzt (so kurz wie möglich, aber eindeutig auffindbar — kopiere ihn zeichengenau).
- ersatz: der neue Text (oder "" wenn ersatzlos gestrichen).
- grund: kurz, warum.
- beleg: die belegende Stelle aus dem Quelltext (wörtliches Zitat) — oder „nicht in Quelle", wenn die Aussage nirgends gedeckt ist.

Antworte NUR als JSON: {"eingriffe": [{"original":"...","ersatz":"...","grund":"...","beleg":"..."}], "anmerkung":"..."}. Ist alles gedeckt: leere Liste."""

LEKTORAT_SCHEMA = {
    "type": "object",
    "required": ["eingriffe"],
    "properties": {
        "eingriffe": {"type": "array", "items": {
            "type": "object",
            "required": ["original", "ersatz", "grund", "beleg"],
            "properties": {
                "original": {"type": "string"},
                "ersatz":   {"type": "string"},
                "grund":    {"type": "string"},
                "beleg":    {"type": "string"}}}},
        "anmerkung": {"type": "string"},
    },
}


def run_lektorat(story_clean: str, source_block: str, lektor_model: str) -> dict:
    """Prüft die Geschichte gegen den Quelltext (Kreuz-Modell). Gibt {eingriffe, anmerkung}."""
    body = (
        "QUELLTEXT (Wikipedia — einzige erlaubte Faktenquelle):\n" + source_block + "\n\n"
        "GESCHICHTE (zu prüfen):\n" + story_clean + "\n\n"
        "AUFGABE: Prüfe jeden Sachfakt der Geschichte gegen den Quelltext und gib die Eingriffe "
        "als JSON. Nur sachlich Falsches/Ungedecktes/Übertriebenes ändern; guten, gedeckten Text "
        "nicht anfassen."
    )
    return _call_json(lektor_model, LEKTORAT_SYSTEM, LEKTORAT_SCHEMA, body, max_tokens=4096)


def build_story(thema: str, td: dict, model: str, max_images: int = 10) -> dict:
    """Erzeugt Story + Bildplatzierung + Galerie für ein Thema/Modell.
    max_images = Obergrenze GESAMT sichtbarer Bilder (Hero + Inline + Galerie)."""
    pool = td.get("images", [])
    # Nur ab_stufe<=2 überhaupt zeigen (S3 raus). S1 = im Text nutzbar; S2 = nur Galerie.
    usable = [(i, img) for i, img in enumerate(pool) if img.get("ab_stufe", 1) <= 1]
    gallery_only = [(i, img) for i, img in enumerate(pool) if img.get("ab_stufe", 1) == 2]

    def _imgline(i, img):
        return (f'[{i}] Originaltitel "{_orig_title(img)}" — zu sehen: '
                f'{(img.get("beschreibung") or "")[:180]}')

    source_block = _source_block(thema, td)

    img_usable = "\n".join(_imgline(i, img) for i, img in usable) or "(keine)"
    img_gal    = "\n".join(_imgline(i, img) for i, img in gallery_only) or "(keine)"

    body = (
        f"THEMA: {thema}\n"
        f"ZIELALTER: etwa 4 bis 8 Jahre.\n"
        f"LÄNGE: {WMIN}–{WMAX} Wörter.\n\n"
        + source_block + "\n\n"
        "GEEIGNETE BILDER (im Text mit [BILD:N] verwendbar UND Alt/Caption nötig):\n"
        + img_usable + "\n\n"
        "ZUSÄTZLICHE BILDER (nur Galerie — NICHT im Text markieren, aber Alt/Caption nötig):\n"
        + img_gal + "\n\n"
        "AUFGABE: Schreib EINE Wissensgeschichte nach deinen Regeln, streng nach Quelltext "
        "für alle echten Fakten. Setze [BILD:N]-Marker nur für GEEIGNETE Bilder, die eine "
        "Stelle wirklich zeigen. Wähle hero_index aus den GEEIGNETEN Bildern. Schreibe alt "
        "und caption für JEDEN Index (geeignete und zusätzliche)."
    )

    data = _call_json(model, STORY_SYSTEM, STORY_SCHEMA, body)

    # — Nachbearbeitung —
    story = (data.get("story_markdown") or "").strip()
    if story.startswith("```"):
        story = re.sub(r"^```[a-zA-Z]*\n?", "", story)
        story = re.sub(r"\n?```$", "", story).strip()

    usable_ix = {i for i, _ in usable}
    all_ix    = usable_ix | {i for i, _ in gallery_only}

    # Inline-Marker einsammeln (nur gültige, geeignete Indizes; Reihenfolge wie im Text)
    inline_order, seen = [], set()
    for m in re.finditer(r"\[BILD:\s*(\d+)\s*\]", story):
        ix = int(m.group(1))
        if ix in usable_ix and ix not in seen:
            inline_order.append(ix); seen.add(ix)
    # ungültige/ Dubletten-Marker aus dem Text entfernen
    def _strip(m):
        ix = int(m.group(1))
        return f"[BILD:{ix}]" if (ix in seen and ix in usable_ix) else ""
    story = re.sub(r"\[BILD:\s*(\d+)\s*\]", _strip, story)

    hero = data.get("hero_index")
    if hero not in usable_ix:
        hero = inline_order[0] if inline_order else (next(iter(usable_ix), None))

    # Alt/Caption-Map
    meta = {}
    for b in data.get("bilder", []):
        if isinstance(b, dict) and isinstance(b.get("index"), int):
            meta[b["index"]] = {"alt": (b.get("alt") or "").strip(),
                                "caption": (b.get("caption") or "").strip()}

    # Galerie = S1 (nicht inline, nicht hero) + alle S2 — relevanzsortiert, S1 vor S2
    used = set(inline_order) | ({hero} if hero is not None else set())
    gal_s1 = sorted([i for i in usable_ix if i not in used],
                    key=lambda i: -pool[i].get("relevanz", 0))
    gal_s2 = sorted([i for i, _ in gallery_only if i not in used],
                    key=lambda i: -pool[i].get("relevanz", 0))
    # Gesamt-Deckel: Hero + Inline + Galerie <= max_images (S1 vor S2 in der Galerie)
    budget = max(0, max_images - len(inline_order) - (1 if hero is not None else 0))
    gallery = (gal_s1 + gal_s2)[:budget]

    story_clean = re.sub(r"\s*\[BILD:\d+\]", "", story).strip()   # Prosa fürs Lektorat
    wc = len([w for line in story_clean.splitlines()
              if not line.strip().startswith("#") for w in line.split()])

    return {"titel": data.get("titel", thema), "story": story, "story_clean": story_clean,
            "hero": hero, "inline": inline_order, "gallery": gallery, "meta": meta,
            "wc": wc, "pool": pool}


# ── HTML-Rendering ───────────────────────────────────────────────────────────
def _fig(pool, meta, ix, cls="inline"):
    img = pool[ix]
    m = meta.get(ix, {})
    alt = m.get("alt") or _orig_title(img)
    cap = m.get("caption") or ""
    s2 = ' <span class=s2>S2 · zum Weiterschauen</span>' if img.get("ab_stufe") == 2 else ""
    return (f'<figure class="{cls}"><img loading=lazy src="{_src(img["filename"])}" alt="{alt}">'
            f'<figcaption><span class=cap>{cap}</span>'
            f'<span class=alt><b>alt:</b> {alt}{s2}</span>'
            f'<span class=fn>[{ix}] {img["filename"][:52]} · r{img.get("relevanz","?")}'
            f' Q{img.get("bildqualitaet","?")}</span></figcaption></figure>')


def _lektorat_table(eingriffe: list, applied: list) -> str:
    if not eingriffe:
        return '<p class=okmsg>✓ Keine Eingriffe — alle Sachfakten durch die Quelle gedeckt.</p>'
    rows = []
    for i, e in enumerate(eingriffe):
        nf = "" if applied[i] else ' <span class=nf>(nicht im Text gefunden)</span>'
        orig  = html.escape((e.get("original") or "")[:140])
        ers   = html.escape((e.get("ersatz") or "")[:140]) or "<i>(gestrichen)</i>"
        grund = html.escape((e.get("grund") or "")[:180])
        beleg = html.escape((e.get("beleg") or "")[:240])
        rows.append(f"<tr><td>{i+1}{nf}</td><td><del>{orig}</del> → <ins>{ers}</ins></td>"
                    f"<td>{grund}</td><td class=beleg>{beleg}</td></tr>")
    return ("<table class=lek><tr><th>#</th><th>Änderung</th><th>Grund</th>"
            "<th>Beleg (Quelltext)</th></tr>" + "".join(rows) + "</table>")


def _apply_marked(story: str, eingriffe: list) -> tuple[str, dict, list]:
    """Wendet die Lektorat-Eingriffe AUF die markierte Story an (Korrektur übernommen),
    ersetzt jeden Treffer durch ein Token und liefert token→Markup-Span (ersatz sichtbar
    hervorgehoben, Streichung als kleiner Marker). Gibt (story_mit_tokens, spanmap, applied)."""
    spanmap, applied = {}, []
    for i, e in enumerate(eingriffe):
        orig = e.get("original") or ""
        if orig and orig in story:
            tok = f"\x01{i}\x01"
            story = story.replace(orig, tok, 1)
            applied.append(True)
            ers   = e.get("ersatz") or ""
            title = html.escape(f"war: {orig} · {e.get('grund') or ''}", quote=True)
            if ers:
                spanmap[tok] = f'<mark class=lekfix title="{title}">{html.escape(ers)}</mark>'
            else:
                spanmap[tok] = f'<sup class=lekdel title="{title}">✂</sup>'
        else:
            applied.append(False)
    return story, spanmap, applied


def _render_model(pool, res, model):
    lek  = res.get("lektorat")
    eing = (lek["result"].get("eingriffe", []) if lek else []) or []
    # Korrektur direkt in die (markierte) Story übernehmen + Änderungen sichtbar markieren
    story, spanmap, applied = _apply_marked(res["story"], eing)
    n_appl = sum(1 for a in applied if a)

    def _mark(text: str) -> str:
        for tok, span in spanmap.items():
            text = text.replace(tok, span)
        return text

    h = [f'<div class=model><h2>{model} · {res["wc"]} Wörter · '
         f'{len(res["inline"])} Bilder im Text + Hero + {len(res["gallery"])} in Galerie</h2>']
    h.append(f'<h3 class=titel>{_mark(res["titel"])}</h3>')
    if res["hero"] is not None:
        h.append('<div class=hero>' + _fig(pool, res["meta"], res["hero"], "hero") + '</div>')

    # Story: korrigierte Fassung; [BILD:N] als Block-Figur nach dem Absatz, Eingriffe markiert
    for para in re.split(r"\n\s*\n", story):
        para = para.strip()
        if not para:
            continue
        ix_here = [int(x) for x in re.findall(r"\[BILD:(\d+)\]", para)]
        text = re.sub(r"\s*\[BILD:\d+\]", "", para).strip()
        if text.startswith("## "):
            h.append(f"<h4>{_mark(text[3:].strip())}</h4>")
        elif text.startswith("# "):
            h.append(f"<h4>{_mark(text[2:].strip())}</h4>")
        elif text:
            h.append(f"<p>{_mark(text)}</p>")
        for ix in ix_here:
            h.append(_fig(pool, res["meta"], ix, "inline"))

    if res["gallery"]:
        h.append('<h4 class=galh>🔎 Galerie — Zum Weiterschauen</h4><div class=gal>')
        for ix in res["gallery"]:
            h.append(_fig(pool, res["meta"], ix, "galitem"))
        h.append('</div>')

    if lek:
        h.append(f'<h4 class=lekh>📝 Lektorat / Beleg — geprüft von {lek["model"]} · '
                 f'{n_appl} Änderung(en) automatisch übernommen (im Text '
                 f'<mark class=lekfix>grün</mark> markiert)</h4>')
        h.append('<p class=note>Übernommen wie bei S3. Passt dir eine Änderung nicht, '
                 'vermerke sie — sie wird dann zurückgenommen.</p>')
        h.append(_lektorat_table(eing, applied))
        if lek["result"].get("anmerkung"):
            h.append(f'<p class=note>Anmerkung: {html.escape(lek["result"]["anmerkung"])}</p>')
    h.append('</div>')
    return "\n".join(h)


def render_theme(thema: str, results: dict, out_path: Path):
    css = """
body{font-family:Georgia,serif;margin:0;background:#f4f2ee;color:#222}
.wrap{max-width:1500px;margin:0 auto;padding:20px}
h1{font-family:sans-serif;font-size:26px;border-bottom:3px solid #c0392b;padding-bottom:8px}
.cols{display:flex;gap:24px;align-items:flex-start}
.model{flex:1;background:#fff;border:1px solid #ddd;border-radius:10px;padding:18px 22px;min-width:0}
.model h2{font-family:sans-serif;font-size:15px;color:#c0392b;margin:0 0 4px;border-bottom:1px solid #eee;padding-bottom:6px}
.titel{font-size:22px;margin:10px 0 14px}
p{line-height:1.65;font-size:17px;margin:12px 0}
h4{font-family:sans-serif;font-size:16px;margin:20px 0 6px;color:#333}
h4.galh{margin-top:26px;color:#2c3e50;border-top:2px dashed #ccc;padding-top:14px}
figure{margin:14px 0;background:#faf9f7;border:1px solid #e3e0da;border-radius:8px;padding:8px}
figure.inline{max-width:460px}
figure img{width:100%;height:auto;border-radius:5px;display:block;background:#eee}
figure.hero img{max-height:340px;object-fit:cover}
figcaption{font-family:sans-serif;font-size:12px;margin-top:6px;display:flex;flex-direction:column;gap:2px}
.cap{font-size:14px;color:#333}
.alt{color:#666}
.alt b{color:#c0392b}
.fn{color:#aaa;font-size:10px;word-break:break-all}
.s2{background:#2c3e50;color:#fff;padding:0 5px;border-radius:3px;font-size:10px}
.gal{display:flex;flex-wrap:wrap;gap:10px}
.gal figure.galitem{width:220px;margin:0}
.gal figure.galitem img{height:150px;object-fit:cover}
.note{font-family:sans-serif;font-size:13px;color:#555;margin:6px 0 18px}
h4.lekh{margin-top:26px;color:#8e44ad;border-top:2px dashed #d6bce6;padding-top:14px}
.redline{background:#fbf9fc;border:1px solid #eadcf3;border-radius:8px;padding:2px 16px;margin:8px 0}
.redline p{font-size:16px}
del{color:#b30000;text-decoration:line-through}
ins{color:#0a7d28;text-decoration:none;background:#e7f7ea;padding:0 2px;border-radius:2px}
mark.lekfix{background:#e7f7ea;color:#0a7d28;padding:0 2px;border-radius:2px;cursor:help}
sup.lekdel{color:#b30000;cursor:help;font-size:11px}
.okmsg{font-family:sans-serif;color:#0a7d28;font-size:14px;font-weight:bold}
table.lek{border-collapse:collapse;width:100%;font-family:sans-serif;font-size:12px;margin:10px 0}
table.lek th,table.lek td{border:1px solid #e0d6ea;padding:6px 8px;text-align:left;vertical-align:top}
table.lek th{background:#f3ebf8}
table.lek td.beleg{color:#555;font-style:italic}
.nf{color:#c00;font-weight:bold}
"""
    html = [f"<meta charset=utf-8><title>Story-Modus v2 — {thema}</title><style>{css}</style>",
            "<div class=wrap>",
            f"<h1>Story-Modus v2 (4–8 J.) — {thema}</h1>",
            "<p class=note>Bild-bewusste Geschichte: das Modell kannte die Bilder vor dem Schreiben, "
            "setzt Inline-Bilder per Marker, wählt ein Hero-Bild und schreibt Alt-Titel + Caption zu "
            "jedem Bild. Galerie = restlicher Pool (S1 ungenutzt + S2 zum Weiterschauen). "
            "r = Vision-Relevanz, Q = Bildqualität.</p>",
            "<div class=cols>"]
    for model, res in results.items():
        html.append(_render_model(res["pool"], res, model))
    html.append("</div></div>")
    out_path.write_text("\n".join(html), encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────────────
def _load_topics(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("topics") or d.get("topics_data") or d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out-dir", required=True, help="Zielordner für die HTML-Dateien")
    ap.add_argument("--suffix", default="v2", help="Dateisuffix")
    ap.add_argument("--themen", nargs="*", default=None)
    ap.add_argument("--models", nargs="+", default=["claude-sonnet-5", "gemini-3.5-flash"])
    ap.add_argument("--max-images", type=int, default=12,
                    help="Obergrenze GESAMT sichtbarer Bilder (Hero+Inline+Galerie); harte Grenze 15 (Speicher)")
    ap.add_argument("--lektorat", action=argparse.BooleanOptionalAction, default=True,
                    help="Beleg-/Lektorat-Pass (Kreuz-Modell) an/aus (--no-lektorat)")
    args = ap.parse_args()

    topics = _load_topics(Path(args.checkpoint))
    themen = args.themen or list(topics.keys())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []

    for thema in themen:
        td = topics.get(thema)
        if not td:
            print(f"! {thema}: nicht im Checkpoint"); continue
        pool_n = len(td.get("images", []))
        print(f"\n=== {thema} ({pool_n} Bilder im Pool) ===")
        results = {}
        for model in args.models:
            print(f"  Story ({model}) …")
            try:
                res = build_story(thema, td, model, max_images=args.max_images)
                results[model] = res
                print(f"    {res['wc']} W · Text-Bilder {res['inline']} · Hero {res['hero']} "
                      f"· Galerie {len(res['gallery'])}")
            except Exception as e:
                print(f"    FEHLER {model}: {str(e)[:140]}")
        if not results:
            continue

        # Beleg-/Lektorat-Pass — Kreuz-Modell (Sonnet-Story→Flash prüft, Flash-Story→Sonnet prüft)
        if args.lektorat:
            src_block = _source_block(thema, td)
            for gen_model, res in results.items():
                lm = _cross_model(gen_model)
                print(f"  Lektorat: {gen_model}-Story → geprüft von {lm} …")
                try:
                    lek = run_lektorat(res["story_clean"], src_block, lm)
                    res["lektorat"] = {"model": lm, "result": lek}
                    print(f"    {len(lek.get('eingriffe', []))} Eingriff(e)")
                except Exception as e:
                    print(f"    Lektorat-FEHLER ({lm}): {str(e)[:120]}")
        safe = re.sub(r"[^\w]+", "_", thema).strip("_")
        out_path = out_dir / f"_story_v2_{safe}_{args.suffix}.html"
        render_theme(thema, results, out_path)
        index.append((thema, out_path))
        print(f"  -> {out_path}")

    print("\n==== FERTIG ====")
    for thema, p in index:
        print(f"  {thema}: {p}")


if __name__ == "__main__":
    main()
