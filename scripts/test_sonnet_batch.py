#!/usr/bin/env python3
"""test_sonnet_batch.py — Verifikation: Anthropic Batch-API + thinking + tool-use.

EIN Wal-S2-Artikel über die Message-Batches-API mit extended thinking + forced-ish
tool-use (tool_choice=auto, da forced mit thinking inkompatibel). Prüft, ob die
Kombination im Batch funktioniert und ob das Modell den emit-Tool-Block liefert.

Reiner Verifikationstest, kein Pipeline-Code. KEIN Commit.
"""
import anthropic, json, time, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'))
sys.path.insert(0, 'scripts')

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from generate_grounded import build_grounded_sources_block, wortziel_for, count_article_words

GENERATOR_MODEL = "claude-sonnet-4-6"
THINKING_BUDGET = 8192
MAX_TOKENS = 32768

from stage_models import ARTICLE_SCHEMA  # zentralisiert (geteilt mit Trim/Box/Generator)

cp = json.load(open("articles/wegb_stage1_20260625/stage1_checkpoint.json", encoding="utf-8"))
wal = cp["topics"]["Wal"]
primary_title = wal.get("resolved_title", "Wale")
primary_text = wal["primary_text"]
companion_texts = wal["companion_texts"]
images = wal["images"]

system_prompt = Path("wissensfreund_generator_prompt_v4_production.md").read_text(encoding="utf-8")
system_prompt += (
    "\n\n## AUSGABE-MODUS (tool-use)\n"
    "Gib den Artikel AUSSCHLIESSLICH über das Tool `emit` aus (rufe es IMMER auf). "
    "Kein Freitext, kein <planung>-Block im Output — deine Planung gehört in den "
    "Denkprozess. Das emit-Tool-Input ist das vollständige Artikel-JSON."
)

stufe = 2
wmin, wmax, _ = wortziel_for("Wal", stufe)
pool = sorted([i for i in images if i.get("ab_stufe", 1) <= stufe],
              key=lambda x: (-x.get("relevanz", 0), -int(x.get("hero_candidate", False))))[:15]
img_block = json.dumps([{
    "index": i, "filename": im.get("filename", ""), "alt": im.get("beschreibung", ""),
    "caption": im.get("caption", ""), "is_hero": im.get("is_hero", False),
    "ab_stufe": im.get("ab_stufe", 1), "thumb_url": im.get("thumb_url", "")
} for i, im in enumerate(pool)], ensure_ascii=False, indent=2)

sources_block = build_grounded_sources_block(
    primary_title, primary_text, list(companion_texts.keys()), companion_texts)

user_msg = (
    f"Thema: Wal\nStufe: S{stufe}\nWortziel: {wmax} Wörter (±10%)\n"
    f"Bilder-Pool ({len(pool)}):\n{img_block}\n\n{sources_block}"
)

client = anthropic.Anthropic()

batch = client.messages.batches.create(requests=[{
    "custom_id": "wal_l2",
    "params": {
        "model": GENERATOR_MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "enabled", "budget_tokens": THINKING_BUDGET},
        "tools": [{"name": "emit",
                   "description": "Gib den vollständigen Artikel als JSON-Objekt aus.",
                   "input_schema": ARTICLE_SCHEMA}],
        "tool_choice": {"type": "auto"},
        "system": [{"type": "text", "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": user_msg}]}],
    },
}])

print(f"Batch erstellt: {batch.id}, Status: {batch.processing_status}")

while batch.processing_status == "in_progress":
    time.sleep(15)
    batch = client.messages.batches.retrieve(batch.id)
    c = batch.request_counts
    print(f"  ...{batch.processing_status} (ok={c.succeeded} err={c.errored} proc={c.processing})")

for result in client.messages.batches.results(batch.id):
    print(f"\ncustom_id: {result.custom_id}, type: {result.result.type}")
    if result.result.type == "succeeded":
        msg = result.result.message
        print(f"stop_reason: {msg.stop_reason}")
        print(f"content-Blöcke: {[b.type for b in msg.content]}")
        article = None
        for b in msg.content:
            if b.type == "tool_use" and b.name == "emit":
                article = b.input
                break
        if article is None:
            print("FEHLER: kein emit-tool_use-Block! (tool_choice=auto → Modell hat emit ausgelassen)")
            print("Text-Blöcke:", [b.text[:200] for b in msg.content if b.type == "text"])
        else:
            print("✅ emit-Block gefunden")
            wc = count_article_words(article)
            secs = len(article.get("sections", []))
            imgs_used = len([s for sec in article.get("sections", [])
                             for s in sec.get("sentences", []) if s.get("img_index", -1) >= 0])
            print(f"  Wortzahl: {wc} (Ziel {wmax})")
            print(f"  Sections: {secs} | Bilder vergeben: {imgs_used}/{len(pool)}")
            print(f"  Quiz-Fragen: {len(article.get('quiz',{}).get('questions',[]))}")
            print(f"  Tokens: in={msg.usage.input_tokens} out={msg.usage.output_tokens} "
                  f"cache_read={getattr(msg.usage,'cache_read_input_tokens',0)}")
            Path("articles/test_sonnet_batch").mkdir(parents=True, exist_ok=True)
            json.dump(article, open("articles/test_sonnet_batch/wal_l2.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            print("  Gespeichert: articles/test_sonnet_batch/wal_l2.json")
    else:
        print(f"FEHLER-Detail: {result.result}")
