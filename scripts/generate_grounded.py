#!/usr/bin/env python3
"""
generate_grounded.py
Zwei-Phasen-Artikel-Generierung mit Kompass-Companion-Grounding + Vision-Bildpool.

Phase 1 (KOMPASS, einmal pro Thema):
  Gemini schlägt Begleitartikel frei aus Wissen vor (kein Link-Pool).
  Validierung: Wikipedia-Existenz prüfen + Weiterleitungen auflösen.
  Shared über alle Stufen desselben Themas.

Phase 2 (je Stufe):
  Primärtext + Companion-Volltexte als stabiler Prefix → Prompt-Caching.
  Stufenspezifische AGE_LEVEL-Anweisung am Ende.

Usage:
    python scripts/generate_grounded.py
    python scripts/generate_grounded.py --articles indianer_l1 indianer_l2 indianer_l3
"""

import argparse
import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
import cost_tracker                      # noqa: E402
from generate_articles import (          # noqa: E402
    fetch_wikipedia_text,
    resolve_lemma,
    parse_article_json,
    _repair_article_quotes,
    validate_article,
    _resolve_bks,
    _wp_get,
    _flash_check_doppelbedeutung,
    WIKIPEDIA_API,
    USER_AGENT,
    MIN_SENTENCES_PER_ARTICLE,
    MAX_SENTENCES_PER_ARTICLE,
)
import gemini_client                     # noqa: E402
from image_vision_filter import (        # noqa: E402
    fetch_image_candidates,
    fetch_lead_image,
    download_image,
    analyze_with_vision,
    load_cached_image_bytes,
    opus_recheck,
)
from lektorat_common import (            # noqa: E402
    COMPANION_CHAR_CAP,
    FACT_LEKTORAT_MODEL,
    PROBLEMATIC_VERDICTS,
    build_grounded_sources_block,
    build_lektorat_parts,
    annotate_article_lektorat_v2,
    run_fact_lektorat_flash,
)

GEMINI_MODEL       = "gemini-3.5-flash"
KOMPASS_MODEL         = "gemini-3.5-flash"   # Primär (KEIN 2.5-flash-Fallback — PO-Regel)
OUT_DIR            = ROOT / "articles" / "test_grounded"
CATALOG_PATH       = ROOT / "catalog_full.json"

_RUN_ID: str = ""   # wird in main() gesetzt (--run-id)
SYSTEM_PROMPT_PATH   = ROOT / "wissensfreund_generator_prompt_v5_2.md"   # Erzähltext (Sachprosa)
HOERSPIEL_PROMPT_PATH = ROOT / "wissensfreund_hoerspiel_prompt_v2_B.md"  # Hörspiel (Story-first, Paket B)
# System-Prompt je Inhaltstyp — Erzähltext = v5.2 (unverändert), Hörspiel = eigenes Genre.
PROMPT_PATHS: dict[str, Path] = {
    "hoerspiel":   HOERSPIEL_PROMPT_PATH,
    "erzaehltext": SYSTEM_PROMPT_PATH,
}
_PROMPT_CACHE: dict[str, str] = {}


def system_prompt_for(content_type: str) -> str:
    """System-Prompt-Text je Inhaltstyp (gecacht). Fallback = Erzähltext-Prompt."""
    path = PROMPT_PATHS.get(content_type, SYSTEM_PROMPT_PATH)
    key = str(path)
    if key not in _PROMPT_CACHE:
        _PROMPT_CACHE[key] = path.read_text(encoding="utf-8")
    return _PROMPT_CACHE[key]

APPEAL_TARGET     = {"high": 15, "medium": 10, "low": 6}
# Textbegleitende Bilder je Appeal — der Rest des Pools wird Galerie.
INLINE_TARGET     = {"high": 8, "medium": 6, "low": 4}
# Bildzuordnung laeuft in einem EIGENEN Aufruf nach der Prosa (assign_images_pass).
DEFER_IMAGES      = True
# Hero = Startbild ueber dem Text (App/Handy). MUSS Querformat sein, sonst wird
# zu stark beschnitten oder das Bild zu klein (PO-Befund 2026-07-22).
HERO_MIN_ASPECT   = 1.2   # Breite/Hoehe; darunter kein Hero-Kandidat
MAX_VISION_CHECKS = 40
MAX_IMG_PRIMARY   = 20
MAX_IMG_COMPANION = 6

# Companion-Cap gestaffelt nach Appeal (kein Auffüllen)
COMPANION_CAP = {"low": 4, "medium": 5, "high": 6}

# ── Inhaltstypen (Stufen-Umbau 2026-07, STUFEN_UMBAU_PLAN.md) ──────────────────
# Zwei Inhaltstypen statt drei Lesestufen. Profil bleibt dreistufig (App-Ebene).
#   hoerspiel   = 4–9 J. (ersetzt altes S1+S2), dramatisiert → Prompt-Genre in Paket B
#   erzaehltext = 10–12 J. (= altes S3, inhaltlich unverändert)
CONTENT_TYPES: tuple[str, ...] = ("hoerspiel", "erzaehltext")

# Ergiebigkeits-Bänder je Inhaltstyp: (Wlo, Whi). Wortziel = Kurve über Ergiebigkeits-Score.
# PO 2026-07-18: Hörspiel-Körperband = altes S3 (225,975) — Inhaltstiefe vor Kürze.
ERG_BANDS: dict[str, tuple[int, int]] = {
    # PO 2026-07-21: Hörspiel-Obergrenze leicht angehoben (975→1100), damit neben
    # weniger Kind-Einwürfen Platz für 1–2 zusätzliche Aspekte am Rande entsteht.
    "hoerspiel":   (275, 1100),
    "erzaehltext": (225, 975),
}
# Ergiebigkeits-Score-Quelle je Typ (ergiebigkeit_scores.json hat noch S1/S2/S3).
# Interim (Paket A): Hörspiel nutzt S2 (ersetzt S1+S2, S1 war zu schwach); Erzähltext S3.
# TODO(Datenrebuild §9): build_ergiebigkeit_scores.py auf Typ-Scores umstellen.
_ERG_SCORE_KEY: dict[str, str] = {"hoerspiel": "S2", "erzaehltext": "S3"}
# Sprach-/Altersstufe für den System-Prompt (AGE_LEVEL). Erzähltext = 3 (= altes S3).
# Hörspiel interim = 2 (7–9-Sprache); Paket B ersetzt das Genre komplett.
_PROMPT_AGE_LEVEL: dict[str, int] = {"hoerspiel": 2, "erzaehltext": 3}

RETRY_FLOOR_FRAC   = 0.70   # Retry-Untergrenze als Bruchteil des Ziels (nur klares Untertreiben nachfordern)
WORD_FLOOR_MIN     = 400    # PO 2026-07-20: harte Wort-Untergrenze — unter ~400 Wörtern trägt keine
                            # Geschichte (Spartacus zeigte: ~440 reichen). Klemmt wmin für gering-ergiebige
                            # Themen hoch; wmax wird mitgehoben, damit das Band kohärent bleibt (wmax>wmin).
ERG_FALLBACK_SCORE = 6      # medium, wenn Thema (noch) nicht gerated — sichtbar geloggt
APPEAL_TIER_HIGH   = 7.0    # Erg-Mittel ≥ → high   (steuert Companion-/Bildmenge)
APPEAL_TIER_MED    = 4.0    # Erg-Mittel ≥ → medium, sonst low
CAP_GRACE_FRAC     = 0.05   # Toleranz über wmax, bevor getrimmt wird (0.0 = strikt ≤ Cap)
TRIM_MAX_ATTEMPTS  = 2      # max. Trim-Pässe, danach review_flag

AGE_RANGES: dict[str, str] = {"hoerspiel": "4-9 Jahre", "erzaehltext": "10-12 Jahre"}


def image_stufe_for(content_type: str, age_floor: int) -> int:
    """Bild-Freigabestufe nach jüngstem Zuschauer (Plan §4).

    Erzähltext (10–12) → 3. Hörspiel folgt dem age_floor: floor 1 → Stufe 1
    (jüngster Zuschauer 4 J. → nur ab_stufe=1), floor 2 → Stufe 2 (jüngster 7 J.)."""
    if content_type == "erzaehltext":
        return 3
    return max(1, min(2, int(age_floor)))


def content_type_from_age_level(age_level: int) -> str:
    """Back-compat für TEST_JOBS/Alt-Jobs ohne content_type: 1|2 → hoerspiel, 3 → erzaehltext."""
    return "erzaehltext" if int(age_level) >= 3 else "hoerspiel"


def _job_ct(job: dict) -> str:
    """Inhaltstyp eines Jobs, mit Back-compat für Alt-Jobs (age_level)."""
    return job.get("content_type") or content_type_from_age_level(job.get("age_level", 2))


def _load_ergiebigkeit() -> dict[str, dict]:
    """Lädt ergiebigkeit_scores.json → key (thema.lower) → {S1,S2,S3}."""
    path = ROOT / "ergiebigkeit_scores.json"
    if not path.exists():
        log.warning("ergiebigkeit_scores.json fehlt (%s) — Wortziel/Appeal nutzen Fallback", path)
        return {}
    data = json.load(path.open(encoding="utf-8"))
    return data.get("scores", data)  # toleriert {_meta,scores}- oder flaches Format

_ERGIEBIGKEIT: dict[str, dict] = _load_ergiebigkeit()


def wortziel_for(thema: str, content_type: str) -> tuple[int, int, str]:
    """(wmin_retry_floor, wmax_target, source) aus Ergiebigkeit + Kurve.

    wmax = round(Wlo + clamp((Erg-2)/6, 0, 1) * (Whi-Wlo))   (Bänder = ERG_BANDS[typ])
    wmin = round(wmax * RETRY_FLOOR_FRAC)
    Score-Quelle je Typ = _ERG_SCORE_KEY (Hörspiel S2, Erzähltext S3).
    Kein gerateter Score → ERG_FALLBACK_SCORE, sichtbar geloggt (nie still mis-sizen).
    """
    lo, hi = ERG_BANDS.get(content_type, (225, 975))
    score_key = _ERG_SCORE_KEY.get(content_type, "S3")
    rec = _ERGIEBIGKEIT.get(thema.strip().lower())
    if rec is None:
        erg, source = ERG_FALLBACK_SCORE, "fallback-medium"
        log.warning("  Ergiebigkeit fehlt für '%s' (%s/%s) → Fallback-Score %d",
                    thema, content_type, score_key, erg)
    else:
        erg, source = int(rec.get(score_key, ERG_FALLBACK_SCORE)), "ergiebigkeit"
    frac = max(0.0, min(1.0, (erg - 2) / 6))
    wmax = round(lo + frac * (hi - lo))
    wmin = round(wmax * RETRY_FLOOR_FRAC)
    if wmin < WORD_FLOOR_MIN:                       # harter Wort-Floor (s. WORD_FLOOR_MIN)
        wmin = WORD_FLOOR_MIN
        wmax = max(wmax, round(WORD_FLOOR_MIN / RETRY_FLOOR_FRAC))
    return wmin, wmax, source


def ergiebigkeit_for(thema: str, content_type: str) -> int:
    """Roher Ergiebigkeits-Score (1–10) für Thema+Typ; Fallback wenn ungerated."""
    rec = _ERGIEBIGKEIT.get(thema.strip().lower())
    if rec is None:
        return ERG_FALLBACK_SCORE
    return int(rec.get(_ERG_SCORE_KEY.get(content_type, "S3"), ERG_FALLBACK_SCORE))


def appeal_for(thema: str, job_appeal: str | None = None) -> tuple[str, str]:
    """Appeal-Tier (high/medium/low) aus Ergiebigkeit (Mittel der 3 Stufen).

    Steuert NUR Companion-Anzahl + Bildmenge — NICHT das Wortbudget.
    Gerated → Tier aus Erg-Mittel; sonst Job-Wert; sonst 'medium' (sichtbar geloggt).
    """
    rec = _ERGIEBIGKEIT.get(thema.strip().lower())
    if rec is not None:
        s = [int(rec.get(f"S{i}", ERG_FALLBACK_SCORE)) for i in (2, 3)]
        mean = sum(s) / 2
        tier = "high" if mean >= APPEAL_TIER_HIGH else ("medium" if mean >= APPEAL_TIER_MED else "low")
        return tier, "ergiebigkeit"
    if job_appeal in ("low", "medium", "high"):
        return job_appeal, "job"
    log.warning("  Appeal: kein Ergiebigkeits-Score für '%s' → Fallback 'medium'", thema)
    return "medium", "fallback-medium"


EIGNUNG_STRICT = False  # True VOR dem Bulk: Themen ohne Urteil werden blockiert statt zugelassen


def _load_eignung() -> dict[str, dict]:
    """Lädt eignung_verdicts.json → key (thema.lower) → {eignung,age_floor,framing_note}."""
    path = ROOT / "eignung_verdicts.json"
    if not path.exists():
        log.warning("eignung_verdicts.json fehlt (%s) — Themen laufen über Eignungs-Fallback", path)
        return {}
    raw = json.load(path.open(encoding="utf-8"))
    data = raw.get("verdicts", raw)
    # Keys auf lowercase normieren — eignung_for() sucht mit .lower()
    return {k.strip().lower(): v for k, v in data.items()}


_EIGNUNG: dict[str, dict] = _load_eignung()

# Safety-Backstop: positive Exclude-Liste aus dem XLSX (reproduzierbar via build_eignung_exclude.py)
try:
    _EXCLUDE_SET = set(json.load(open(ROOT / "eignung_exclude.json", encoding="utf-8")).get("exclude", []))
    log.info("  Eignung: %d Excludes geladen (Backstop)", len(_EXCLUDE_SET))
except FileNotFoundError:
    _EXCLUDE_SET = set()
    log.warning("  Eignung: eignung_exclude.json fehlt — Exclude-Backstop INAKTIV")


def eignung_for(thema: str) -> dict:
    """Eignungs-Urteil: {eignung, age_floor, framing_note, source}. Kein Urteil → Fallback (sichtbar)."""
    key = thema.strip().lower()
    if key in _EXCLUDE_SET:
        return {"eignung": "exclude", "age_floor": 1, "framing_note": "", "source": "exclude-set"}
    rec = _EIGNUNG.get(key)
    if rec is None:
        if EIGNUNG_STRICT:
            log.warning("  Eignung: kein Urteil für '%s' → STRICT: blockiert", thema)
            return {"eignung": "exclude", "age_floor": 1, "framing_note": "", "source": "fallback-strict"}
        log.warning("  Eignung: kein Urteil für '%s' → Default include/S1 (ungeprüft)", thema)
        return {"eignung": "include", "age_floor": 1, "framing_note": "", "source": "fallback-permissive"}
    # Neues Schema: exclude:true statt eignung:"exclude"; age_floor direkt als int
    eignung_val = "exclude" if rec.get("exclude") else rec.get("eignung", "include")
    return {
        "eignung":      eignung_val,
        "age_floor":    int(rec.get("age_floor", 1)),
        "framing_note": rec.get("framing_note", "") or "",
        "source":       "verdict",
    }


def count_article_words(article: dict) -> int:
    """Zählt Wörter in Fließtext + Boxen (ohne Quiz, ohne Überschriften)."""
    words = 0
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            words += len(s.get("text", "").split())
        for box in sec.get("boxes", []):
            words += len((box.get("text") or "").split())
            words += len((box.get("reveal_text") or "").split())
    return words


def _make_thinking_config(model: str, budget_for_2_5: int) -> types.ThinkingConfig:
    """Gibt das modellspezifische ThinkingConfig zurück (medium)."""
    if "2.5" in model:
        cfg = types.ThinkingConfig(thinking_budget=budget_for_2_5)
        log.info("  ThinkingConfig: thinking_budget=%d (Modell=%s)", budget_for_2_5, model)
        return cfg
    cfg = types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM)
    log.info("  ThinkingConfig: thinking_level=MEDIUM (Modell=%s)", model)
    return cfg


# ── Test-Jobs ─────────────────────────────────────────────────────────────────

TEST_JOBS: dict[str, dict] = {
    "indianer_l1": {
        "article_id":        "indianer_l1",
        "thema":             "Indianer",
        "primaer_wikipedia": "Indianer",
        "title":             "Indianer",
        "age_level":         1,
        "topic_interest":    "high",
        "sensibel":          True,
        "pattern":           "history_person",
        "category_top":      "laender_und_kulturen",
        "category_sub":      "voelker_und_kulturen",
    },
    "indianer_l2": {
        "article_id":        "indianer_l2",
        "thema":             "Indianer",
        "primaer_wikipedia": "Indianer",
        "title":             "Indianer",
        "age_level":         2,
        "topic_interest":    "high",
        "sensibel":          True,
        "pattern":           "history_person",
        "category_top":      "laender_und_kulturen",
        "category_sub":      "voelker_und_kulturen",
    },
    "indianer_l3": {
        "article_id":        "indianer_l3",
        "thema":             "Indianer",
        "primaer_wikipedia": "Indianer",
        "title":             "Indianer",
        "age_level":         3,
        "topic_interest":    "high",
        "sensibel":          True,
        "pattern":           "history_person",
        "category_top":      "laender_und_kulturen",
        "category_sub":      "voelker_und_kulturen",
    },
    "biene_l1": {
        "article_id":        "biene_l1",
        "thema":             "Biene",
        "primaer_wikipedia": "Biene",
        "title":             "Biene",
        "age_level":         1,
        "topic_interest":    "high",
        "sensibel":          False,
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "insekten",
    },
    "biene_l2": {
        "article_id":        "biene_l2",
        "thema":             "Biene",
        "primaer_wikipedia": "Biene",
        "title":             "Biene",
        "age_level":         2,
        "topic_interest":    "high",
        "sensibel":          False,
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "insekten",
    },
    "biene_l3": {
        "article_id":        "biene_l3",
        "thema":             "Biene",
        "primaer_wikipedia": "Biene",
        "title":             "Biene",
        "age_level":         3,
        "topic_interest":    "high",
        "sensibel":          False,
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "insekten",
    },
    "demokratie_l1": {
        "article_id":        "demokratie_l1",
        "thema":             "Demokratie",
        "primaer_wikipedia": "Demokratie",
        "title":             "Demokratie",
        "age_level":         1,
        "topic_interest":    "medium",
        "sensibel":          True,
        "pattern":           "tech_science",
        "category_top":      "gesellschaft",
        "category_sub":      "staat_und_recht",
    },
}


# ── Phase-1-Prompt (Kompass) ─────────────────────────────────────────────────

COMPANION_SYSTEM_PROMPT = (
    "Du waehlst Wikipedia-Begleitartikel fuer einen Kinderwissens-Artikel aus.\n"
    "Antworte ausschliesslich mit gueltigem JSON ohne Markdown.\n"
    'Format: {"companions": ["Lemma1","Lemma2",...]}'
)

# JSON-Schema für forced tool-use (anthropic-Pfad) — Äquivalent zu companions_schema (Gemini)
_KOMPASS_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {"type": "string"},
        "companions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plan", "companions"],
}

COMPANION_PROMPT_TMPL = """\
THEMA: {thema}
APPEAL: {appeal} (low/medium/high)
PRIMAERARTIKEL (Anfang):
{lead}

## 1. DEINE ROLLE
Du bist Chef-Rechercheur für das deutsche Kinderlexikon **Wissensfreund**. Du überlegst ZUERST, was dieser Kinderartikel erzählen soll, und wählst DANN die Begleitartikel (Companions), die genau dazu passen — sie geben dem Thema Tiefe, Anschaulichkeit und narrative Anker für Kinder.

## 2. ARBEITE IN ZWEI SCHRITTEN (Reihenfolge einhalten)

**SCHRITT 1 — Schreibplan (Feld "plan"):**
Entscheide zuerst in 2–4 Sätzen, WELCHE Aspekte des Themas der Artikel behandeln soll. Einziger Maßstab: Wie interessant und spannend ist ein Aspekt für den Leser? Nimm die fesselndsten aus VERSCHIEDENEN Blickwinkeln (ein ikonischer Vertreter, ein kultureller/historischer Anker, eine überraschende Facette) — aber KEINE Aufzählung ähnlicher Unterarten oder Vertreter derselben Sorte (nicht vier Walarten): ein starker Aspekt je Blickwinkel schlägt eine Reihe naher Verwandter. **Einer dieser Blickwinkel ist fast immer die Geschichte der MENSCHEN DAHINTER — wie das Thema entdeckt, erforscht, umkämpft oder errungen wurde** (die Entdecker, ihre Rivalität, ein Abenteuer, ein berühmter Irrtum, ein Wettlauf). Diese Menschheits-/Entdeckungsgeschichte ist für Kinder oft der lebendigste, spannendste Stoff — plane sie aktiv ein, wo es sie gibt (z. B. bei Dinosauriern der erbitterte Ausgrabungs-Wettstreit der Knochenkriege; bei einem Planeten das Wettrennen der Entdecker; bei einer Krankheit der Kampf um das Heilmittel), und wähle den passenden Companion dazu. **Wähle das KONKRETE Belegstück, nicht den Oberbegriff:** Wird ein Aspekt an einem berühmten Fundstück, Bauwerk, Werk oder Ort greifbar, nimm dieses als Companion statt der allgemeinen Kategorie — das Konkrete kann ein Kind sich vorstellen, der Oberbegriff nicht (also der berühmte Übergangsfossil-Fund statt „Vögel", der benannte Einschlagkrater statt „Asteroid", das eine berühmte Gemälde statt „Malerei"). Steht der Oberbegriff bereits im Haupttext, gewinnt der konkrete Beleg den Companion-Platz. **Ein dramatisches Ereignis oder Schicksal schlägt ein technisches Nebenphänomen:** Gibt es zum Thema eine berühmte Katastrophe, einen Untergang, eine Rettung, einen Konflikt (bei „Vulkan" der Untergang Pompejis), dann plane DIESE als eigenen, ausführlichen Companion — vor technischen Randaspekten (etwa „Geysir", „Gesteinsarten"), die höchstens am Rande gestreift werden. Kinder erinnern die Geschichte, nicht die Klassifikation.
**Schöpfe für den Plan aus deinem WELTWISSEN über das Thema** — was ist das Berühmteste, Ikonischste, für Kinder Spannendste, woran denkt man beim Thema als ERSTES? Der Primärartikel oben ist nur EIN Hinweisgeber und oft gekürzt; verlasse dich NICHT darauf, dass jeder wichtige Aspekt darin steht (bei „Vulkan" gehört Pompeji/der Vesuv-Ausbruch in den Plan, auch wenn der Artikelanfang ihn nicht nennt). **Wichtige Trennung:** Weltwissen ist hier NUR erlaubt, um die Aspekte und Companions AUSZUWÄHLEN — die späteren Sachaussagen im Artikel stammen ausschließlich aus den geladenen Quellen (kein erfundener Fakt). Jeder geplante Aspekt MUSS sich einem ECHTEN Wikipedia-Artikel (Companion) zuordnen lassen, der ihn mit Stoff füllt; findest du keinen, lass den Aspekt weg.

**SCHRITT 2 — Companions (Feld "companions"):**
Wähle DANN die Begleitartikel, die genau diese geplanten Aspekte mit echtem Wikipedia-Stoff füllen. Jeder Companion muss einem geplanten Aspekt dienen — nimm keinen Companion ohne Bezug zum Plan.

Maßstab bei jedem Companion ist allein, wie interessant und spannend der Aspekt für den Leser ist — gleichwertig, ob er eine kulturelle oder historische Perspektive (Mythos, berühmtes Ereignis) oder eine besonders faszinierende Facette des Themas selbst (ein verwandtes Phänomen, ein extremes oder exotisches Beispiel) öffnet. Vermeide nur blasse Füll-Lemmata ohne eigenen Reiz. WICHTIG (gilt für JEDES Thema): Das ikonische Aushängeschild eines Themas — das, WORAN MAN BEI DEM THEMA ALS ERSTES DENKT — gehört bevorzugt zu den Companions, auch wenn es Teil des Hauptthemas ist. Das kann eine weltberühmte Dinosaurier-Art (Tyrannosaurus rex) oder ein weltbekanntes Einzeltier sein, GENAUSO aber das berühmteste Einzelwerk, Wahrzeichen oder die berühmteste Erfindung eines Schöpfers oder Ortes (das ikonische Gemälde, Bauwerk, Buch oder die Erfindung) — bei einer Künstlerin/einem Künstler also die bekanntesten Werke selbst. Nimm die EIN bis ZWEI bekanntesten solcher Aushängeschilder ausdrücklich mit; die übrigen Companions weiterhin für neue Blickwinkel.

## 3. AUSWAHL-VORGABEN

**Nachrangig — Fach-/Stoff-Sachkunde:** Gesteins-/Materialarten, Formations- oder Klassifikations-Artikel (z. B. „Lava" als Stoff, „Basalt", Säulen-/Kristallformen, Untergruppen-Taxonomie) sind trockene Sachkunde. Wähle sie NIEMALS anstelle eines lebendigen Ereignisses/Beispiels — nur ergänzend, wenn nach dem ikonischen Anker und den lebendigen Aspekten noch Platz für EINEN wirklich anschaulichen Prozess frei ist.

**A. Menge & Qualität (Das APPEAL-Level entscheidet)**
- **APPEAL low:** Wähle 2–3 Companions.
- **APPEAL medium / high:** Wähle 3–5 Companions.
- **Qualität vor Quantität:** Fülle niemals mit unpassenden Artikeln auf. Jeder Companion muss einen eigenen, starken Mehrwert bringen.
- **Vielfalt (hart):** **Höchstens ZWEI Vertreter derselben Kategorie** (z. B. nicht vier Walarten, nicht drei Planeten hintereinander). Jeder weitere Companion muss einen NEUEN Blickwinkel öffnen — Kultur/Geschichte, ein verwandtes Phänomen, ein Extrembeispiel — nicht denselben Aspekt in einer weiteren Art.

**B. Die 3 Säulen eines guten Companions (Prioritäten)**
1. **Kinderwelt & Fantasie:** Was kennen Kinder aus ihrem echten Alltag, aus Büchern oder Filmen? (Beispiele: Dinosaurier im Buch, Gewitter, Mondschein).
2. **Dynamik & Leben — bild-konkret:** Sichtbare Lebewesen, Orte und Ereignisse, die sich für Kinder FOTOGRAFIEREN lassen, schlagen statische Zustände und abstrakte Prozesse. Bei ähnlich starken Kandidaten gewinnt der fotografierbare (ein konkretes Tier, eine Pflanze, ein Ort) gegen einen, der real nur als Diagramm existiert. (Beispiele: Vulkanausbruch, ein Regenwald-Tier statt „Photosynthese").
3. **Kultur & Menschliches (PFLICHT, wenn vorhanden):** Das eine berühmte Ereignis, Werk oder Beispiel, an das die meisten Menschen beim Thema ZUERST denken (Beispiele: Moby Dick bei Wal, **Pompeji/Vesuv bei Vulkan**, ein berühmtes Bauwerk bei einem Baumeister). Ein solcher lebendiger Anker ist der stärkste narrative Aufhänger für Kinder — WENN es ihn für das Thema gibt, MUSS er unter den Companions sein, und zwar als EINER DER ERSTEN. **Eine bloße Wortherkunft oder ein Namensgeber (z. B. der Gott Vulcanus als Ursprung des Wortes „Vulkan") ERSETZT diesen Anker NICHT.** Gibt es ein berühmtes dramatisches Ereignis (eine verschüttete Stadt, ein großes Unglück, eine berühmte Rettung/Entdeckung), hat es Vorrang vor Mythos, Etymologie und technischer Sachkunde — beides darf ergänzen, aber nie den ikonischen Ereignis-Anker verdrängen.

**C. Harte Ausschlusskriterien (Was du NICHT wählst)**
- **Statische Geologie & Zustände:** Keine starren Strukturen ohne erlebbare Dynamik (Erdmantel, Pangaea).
- **Nur-Diagramm / Nur-Modell:** Keine abstrakten Theorien oder Kategorien, die ein Kind sich nicht bildlich vorstellen kann — und keine Themen, die real überwiegend als Diagramm, Lehrpfad-Modell oder Nachbildung existieren (z. B. ein Planetenweg): Sie liefern keine echten Kinderbilder des Gegenstands.
- **Reine Bezeichnungen:** Fotos oder bloße Namen (z.B. "Blue Marble") sind keine echten Themen.
- **Trauma ohne Sachkern:** Ernste Themen (Unglücke, Konflikte) sind erlaubt, aber nur, wenn sie einen kindgerechten, lehrreichen Kern haben (Mut, Technik, Ausgrabung) – niemals für reinen Schockwert.

## 4. AUSGABE
Generiere AUSSCHLIESSLICH ein valides JSON-Objekt: zuerst dein Schreibplan, dann die exakten deutschsprachigen Wikipedia-Lemmata. Kein Markdown, keine Erklärungen.
{{"plan": "…", "companions": ["Lemma1", "Lemma2", "Lemma3"]}}"""


# ── Legacy-Funktionen (von batch_run.py importiert) ──────────────────────────

def fetch_wikipedia_links(session: requests.Session, title: str) -> list[str]:
    """Legacy: holt interne Links (Namespace 0). Noch von batch_run.py genutzt."""
    all_links: list[str] = []
    params = {
        "action": "query", "format": "json",
        "titles": title, "redirects": "1",
        "prop": "links", "plnamespace": 0, "pllimit": 500,
    }
    while True:
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            for lnk in page.get("links", []):
                t = lnk.get("title", "")
                if t:
                    all_links.append(t)
        cont = data.get("continue", {})
        if "plcontinue" not in cont:
            break
        params["plcontinue"] = cont["plcontinue"]
        time.sleep(0.2)
    return all_links


def check_articles_exist(session: requests.Session, titles: list[str]) -> dict[str, bool]:
    """Legacy: prüft Artikel-Existenz ohne Redirect-Auflösung. Noch von batch_run.py genutzt."""
    result: dict[str, bool] = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i+20]
        params = {
            "action": "query", "format": "json",
            "titles": "|".join(chunk), "redirects": "1",
            "prop": "info",
        }
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        normalizations = {
            n["from"].lower(): n["to"]
            for n in data.get("query", {}).get("normalized", [])
        }
        redirects = {
            r["from"].lower(): r["to"]
            for r in data.get("query", {}).get("redirects", [])
        }
        for t in chunk:
            result[t] = any(
                "missing" not in page
                for page in pages.values()
                if page.get("title", "").lower() in (
                    t.lower(),
                    normalizations.get(t.lower(), "").lower(),
                    redirects.get(t.lower(), "").lower(),
                )
            )
        time.sleep(0.1)
    return result


def validate_companions(
    session: requests.Session,
    raw_companions: list[str],
    link_set: set[str],
) -> tuple[list[str], list[dict]]:
    """Legacy: validiert gegen Link-Set. Noch von batch_run.py genutzt."""
    valid: list[str] = []
    rejected: list[dict] = []
    link_set_lower = {t.lower() for t in link_set}
    for comp in raw_companions:
        if comp.lower() not in link_set_lower:
            rejected.append({"title": comp, "reason": "nicht in Link-Liste des Primärartikels"})
            continue
        valid.append(comp)
    if valid:
        existence = check_articles_exist(session, valid)
        confirmed: list[str] = []
        for comp in valid:
            if existence.get(comp, False):
                confirmed.append(comp)
            else:
                rejected.append({"title": comp, "reason": "Wikipedia-Artikel nicht gefunden"})
        valid = confirmed
    return valid, rejected


# ── Phase 1: Kompass-Auswahl ─────────────────────────────────────────────────

# Schreibplan des letzten KOMPASS-Calls — Stage 1 kann ihn nach dem Aufruf lesen
# und in den Checkpoint schreiben (spaetere Weitergabe an Stage 2 / Pass 1).
_LAST_KOMPASS_PLAN: str = ""


def _capture_kompass(data: dict) -> list[str]:
    """Stasht den Schreibplan modulweit + loggt ihn, gibt die Companion-Liste zurueck."""
    global _LAST_KOMPASS_PLAN
    _LAST_KOMPASS_PLAN = str(data.get("plan", "") or "").strip()
    if _LAST_KOMPASS_PLAN:
        log.info("  Kompass-Schreibplan: %s", _LAST_KOMPASS_PLAN)
    return [str(c) for c in data.get("companions", [])][:10]


def get_last_kompass_plan() -> str:
    """Schreibplan des zuletzt ausgefuehrten select_companions_raw (oder '')."""
    return _LAST_KOMPASS_PLAN


def select_companions_raw(
    client: genai.Client,
    thema: str,
    primary_text: str,
    model: str = GEMINI_MODEL,
    appeal: str = "medium",
) -> tuple[list[str], dict]:
    """Kompass: Modell schlägt Begleitartikel frei vor. Gibt (companions, usage_dict) zurück.

    Provider/Modell aus stage_models["kompass"]. anthropic → forced tool-use (claude_client),
    gemini → response_schema + 503-Fallback (unverändert). Prompts bleiben wortgleich.
    """
    # Reset: sonst leckt bei einem gescheiterten Call (0 Companions) der Plan des
    # vorigen Topics durch get_last_kompass_plan() (Bug im Nachmittags-Flash-Test).
    global _LAST_KOMPASS_PLAN
    _LAST_KOMPASS_PLAN = ""
    # Plan-first: KOMPASS soll erst den Schreibplan skizzieren, dann Companions
    # dazu waehlen -> mehr Hauptartikel-Kontext (nicht nur die Einleitung).
    # Der Primärtext ist nur EIN Hinweisgeber für den Plan — die ikonischen Aspekte
    # holt Kompass aus dem Weltwissen (s. COMPANION_PROMPT_TMPL SCHRITT 1), nicht aus
    # den Artikelzeichen. Deshalb reicht ein knapper Lead (Thema/Disambiguierung);
    # kein großer Ausschnitt nötig, um weit hinten genannte Ereignisse zu „sehen".
    lead = primary_text[:6000]
    prompt = COMPANION_PROMPT_TMPL.format(thema=thema, lead=lead, appeal=appeal)

    from stage_models import get_stage_config
    cfg = get_stage_config("kompass")
    if cfg["provider"] == "anthropic":
        from claude_client import call_claude_json, get_last_usage
        log.info("  Phase 1 Kompass-Auswahl (Provider=anthropic, Modell=%s, forced tool-use)",
                 cfg["model"])
        try:
            data = call_claude_json(
                system_prompt=COMPANION_SYSTEM_PROMPT,
                user_message=prompt,
                json_schema=_KOMPASS_SCHEMA,
                model=cfg["model"],
                call_name="kompass",
            )
            lu = get_last_usage()
            usage = {"input_tok": lu.get("input_tokens", 0), "output_tok": lu.get("output_tokens", 0),
                     "cached_tok": 0, "thoughts_tok": 0}
            return _capture_kompass(data), usage
        except Exception as e:
            log.error("  Kompass (anthropic) Fehler: %s", e)
            return [], {}

    # ── Gemini-Pfad (unverändert) ───────────────────────────────────────────────
    # Der Kompass läuft bewusst auf Gemini (Flash). Ist der Run-GENERATOR ein
    # Claude-Modell (--gen-model claude-*, A/B-Test), darf dieser Name NICHT an den
    # Gemini-Endpunkt (→ 404) — dann das konfigurierte Kompass-Gemini-Modell nehmen.
    if model.lower().startswith("claude"):
        model = cfg.get("model") or KOMPASS_MODEL
    thinking = _make_thinking_config(model, budget_for_2_5=1024)
    log.info("  Phase 1 Kompass-Auswahl (Modell=%s, structured_output=JSON)", model)

    companions_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "plan": types.Schema(type=types.Type.STRING),
            "companions": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            )
        },
        required=["plan", "companions"],
    )

    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COMPANION_SYSTEM_PROMPT,
                    temperature=0.3,
                    thinking_config=thinking,
                    response_mime_type="application/json",
                    response_schema=companions_schema,
                ),
            )
            um = getattr(response, "usage_metadata", None)
            usage: dict = {}
            if um:
                usage = {
                    "input_tok":    int(getattr(um, "prompt_token_count", 0) or 0),
                    "output_tok":   int(getattr(um, "candidates_token_count", 0) or 0),
                    "cached_tok":   int(getattr(um, "cached_content_token_count", 0) or 0),
                    "thoughts_tok": int(getattr(um, "thoughts_token_count", 0) or 0),
                }
            text = (response.text or "").strip()
            data = json.loads(text)
            return _capture_kompass(data), usage
        except json.JSONDecodeError as e:
            log.warning("  Phase 1 JSON-Fehler (V%d): %s | raw=%r", attempt, e, (response.text or "")[:120])
            return [], {}
        except Exception as e:
            err = str(e)
            e_low = err.lower()
            # Guthaben leer: KEIN Retry (Retry ist zwecklos bis zum Auffuellen).
            # Sofort mit klarer Meldung raus, statt 6x mit Backoff zu warten.
            if gemini_client.is_billing_depleted(err):
                log.error("  ⛔ Phase 1 abgebrochen: Gemini-Prepaid-Guthaben aufgebraucht "
                          "(429 RESOURCE_EXHAUSTED). Im AI Studio auffuellen, dann neu starten.")
                return [], {}
            is_transient = (
                "503" in err or "429" in err or "unavailable" in e_low or "overloaded" in e_low
                or "timeout" in e_low or "timed out" in e_low or "deadline" in e_low
                or "connection" in e_low or "reset" in e_low
                or "499" in err or "cancelled" in e_low or "canceled" in e_low
            )
            if attempt < max_attempts and is_transient:
                wait = min(60 * (2 ** (attempt - 1)), 300)
                log.warning("  Phase 1 transient (V%d/%d): %s -- warte %ds ...",
                            attempt, max_attempts, err[:80], wait)
                time.sleep(wait)
            elif is_transient:
                # KEIN Modell-Fallback: gemini-2.5-flash ist als Generator/Helfer
                # generell ausgeschlossen (Qualitaet unzureichend, PO-Regel). Bei
                # transienter Erschoepfung liefert Phase 1 keine Companions → der
                # Job schlaegt sauber fehl und der Nachtlauf laeuft ihn off-peak
                # erneut an, statt auf 2.5-flash abzurutschen.
                log.error("  Phase 1 transient erschöpft auf %s — kein 2.5-flash-Fallback, "
                          "Job wird off-peak neu angelaufen.", model)
                return [], {}
            else:
                log.error("  Phase 1 Fehler: %s", e)
                return [], {}

    return [], {}


def _companion_target_ok(
    session: requests.Session, title: str | None, orig_bks: str
) -> tuple[bool, str]:
    """Prüft ein BKS-Auflösungsziel: existiert, KONKRET (keine BKS), ≠ Ausgangs-BKS.

    Verhindert, dass ein Companion auf die BKS selbst (oder eine weitere BKS) fällt —
    sonst würde der spätere fetch_wikipedia_text() erneut größenbasiert fehlauflösen.
    """
    if not title or not title.strip():
        return False, "kein Zielvorschlag (child_lemma leer)"
    if title.strip().lower() == orig_bks.strip().lower():
        return False, "Ziel = Ausgangs-BKS"
    _params = {
        "action": "query", "format": "json", "redirects": "1",
        "titles": title, "prop": "info|pageprops",
    }
    try:
        resp = _wp_get(session, _params)
        pages = resp.json().get("query", {}).get("pages", {})
    except Exception as e:
        return False, f"Ziel-Prüfung API-Fehler: {e}"
    for page in pages.values():
        if "missing" in page:
            return False, "Zielartikel fehlt"
        if "disambiguation" in (page.get("pageprops") or {}):
            return False, "Ziel ist erneut BKS"
    return True, "ok"


def validate_and_resolve_companions(
    session: requests.Session,
    raw_companions: list[str],
    primary_title: str,
    cap: int = 5,
) -> tuple[list[str], list[dict], list[dict]]:
    """
    Prüft Wikipedia-Existenz, löst Weiterleitungen auf, dedupliziert.

    BKS-Companions (Begriffsklärung) werden erkannt (pageprops.disambiguation) und
    NICHT größenbasiert (über _resolve_bks allein) aufgelöst — der größenbasierte
    Kandidat wird mit _flash_check_doppelbedeutung plausibilisiert (gleiche Mechanik
    wie der Primär-Lemma-Pfad). Plausibel → nehmen; sonst Companion VERWERFEN statt
    falsch auflösen (ein falscher Companion kontaminiert das Grounding, ein fehlender
    ist harmlos).

    Gibt (valid_canonical, rejected_log, resolution_log) zurück. resolution_log
    hält den Ausgang JE Companion fest (für persistente Sichtbarkeit im report.json).
    """
    if not raw_companions:
        return [], [], []

    params = {
        "action": "query", "format": "json",
        "titles": "|".join(raw_companions[:10]),
        "redirects": "1",
        "prop": "info|pageprops",   # pageprops → BKS-Erkennung (disambiguation)
    }
    try:
        resp = _wp_get(session, params)
        query = resp.json().get("query", {})
    except Exception as e:
        log.error("  Companion-Validierung API-Fehler: %s", e)
        rej = [{"title": c, "resolved": None, "reason": f"API-Fehler: {e}"}
               for c in raw_companions]
        return [], rej, [dict(r, outcome="rejected") for r in rej]

    # Auflösungskette aufbauen: Normalisierung + Weiterleitungen
    resolve: dict[str, str] = {}
    for n in query.get("normalized", []):
        resolve[n["from"]] = n["to"]
    for r in query.get("redirects", []):
        resolve[r["from"]] = r["to"]

    def follow(title: str) -> str:
        seen_chain: set[str] = set()
        t = title
        while t in resolve and t not in seen_chain:
            seen_chain.add(t)
            t = resolve[t]
        return t

    existing: set[str] = {
        page["title"]
        for page in query.get("pages", {}).values()
        if "missing" not in page
    }
    bks_titles: set[str] = {
        page["title"]
        for page in query.get("pages", {}).values()
        if "disambiguation" in (page.get("pageprops") or {})
    }

    valid: list[str] = []
    rejected: list[dict] = []
    resolution: list[dict] = []
    seen_resolved: set[str] = set()
    primary_lower = primary_title.lower()

    def _reject(comp, resolved, reason):
        rejected.append({"title": comp, "resolved": resolved, "reason": reason})
        resolution.append({"input": comp, "resolved": resolved,
                            "outcome": "rejected", "reason": reason})
        log.warning("  Verworfen: '%s'%s (%s)", comp,
                    f" -> '{resolved}'" if resolved != comp else "", reason)

    for comp in raw_companions:
        resolved = follow(comp)

        if resolved not in existing:
            # Such-Fallback: Companion nicht direkt/per Redirect auflösbar (Haiku liefert
            # oft beschreibende statt exakter Lemmata). resolve_lemma versucht zusätzlich
            # die WP-Suche (list=search) und rettet so Treffer wie
            # 'Menschliches Gehirn' → 'Gehirn'. Guard: _companion_target_ok (existiert,
            # keine BKS). Keine Flash-Plausibilisierung — semantische Drift akzeptiert.
            _r   = resolve_lemma(session, comp)
            _neu = _r.get("resolved_title")
            if _neu and _r.get("source") in ("direct", "redirect", "search"):
                _ok, _grund = _companion_target_ok(session, _neu, comp)
                if not _ok:
                    _reject(comp, _neu, f"Such-Fallback verworfen: {_grund}")
                    continue
                log.info("  Companion gerettet: '%s' -> '%s' (%s)",
                         comp, _neu, _r.get("source"))
                resolved = _neu
                # KEIN continue: gerettetes Lemma läuft durch primary/dup-Checks unten
            else:
                _reject(comp, resolved, "nicht gefunden (auch Suche erfolglos)")
                continue

        # ── BKS-Companion: plausibilisieren statt größenbasiert auflösen ──────────
        bks_note = None
        if resolved in bks_titles:
            orig_bks = resolved
            cand = _resolve_bks(session, orig_bks)   # größenbasierter Kandidat (nur Eingabe)
            if not cand:
                _reject(comp, orig_bks, "BKS ohne Artikel-Link")
                continue
            vc = _flash_check_doppelbedeutung(session, comp, cand)
            verdict = vc.get("verdict", "a")
            if verdict in ("a", "b"):
                target, why = cand, f"Flash {verdict}, plausibel"
            else:  # verdict "c": größenbasierter Kandidat unplausibel → Flash-Vorschlag
                target, why = vc.get("child_lemma"), f"Flash c → child_lemma '{vc.get('child_lemma')}'"
            # Ziel muss existieren, ein KONKRETER Artikel sein (keine BKS) und nicht
            # die Ausgangs-BKS selbst — sonst würde der spätere Fetch wieder
            # größenbasiert falsch auflösen. Kein plausibles Ziel → verwerfen.
            ok, reason = _companion_target_ok(session, target, orig_bks)
            if not ok:
                _reject(comp, orig_bks,
                        f"BKS unplausibel ({reason}; größenbasiert '{cand}', Flash {verdict})")
                continue
            bks_note = f"BKS '{orig_bks}' → '{target}' ({why})"
            resolved = target
            log.warning("  Companion-BKS: %s", bks_note)

        resolved_lower = resolved.lower()
        if resolved_lower == primary_lower:
            _reject(comp, resolved, "= Primaerartikel")
            continue
        if resolved_lower in seen_resolved:
            _reject(comp, resolved, "Duplikat")
            continue

        seen_resolved.add(resolved_lower)
        if resolved != comp:
            log.info("  Companion aufgeloest: '%s' -> '%s'", comp, resolved)
        valid.append(resolved)
        resolution.append({"input": comp, "resolved": resolved,
                           "outcome": ("bks_resolved" if bks_note else "kept"),
                           "reason": bks_note or "ok"})

    return valid[:cap], rejected, resolution


# ── Bildpool ──────────────────────────────────────────────────────────────────

def build_image_pool(
    session: requests.Session,
    client: genai.Client,
    thema: str,
    primary_wikipedia: str,
    companion_titles: list[str],
    appeal: str,
    sensibel: bool = False,
    anthropic_api_key: str | None = None,
) -> tuple[list[dict], dict]:
    all_candidates: list[dict] = []
    sources: dict[str, int] = {}

    # LEITBILDER zuerst (kanonisch/bekannt): das Infobox-Bild von Haupt- und JEDEM
    # Companion-Artikel gezielt holen und voranstellen. generator=images liefert nur
    # alphabetisch und kappt das Leitbild sonst weg (z. B. die Mona Lisa, das Selbstbildnis).
    lead_titles = [primary_wikipedia] + list(companion_titles)
    for lt in lead_titles:
        lead = fetch_lead_image(session, lt)
        time.sleep(0.3)
        if lead:
            lead["_source"] = f"{lt} (Leitbild)"
            all_candidates.append(lead)
            log.info("    Leitbild aus '%s': %s", lt, lead["filename"][:60])

    primary_imgs = fetch_image_candidates(
        session, primary_wikipedia, max_candidates=MAX_IMG_PRIMARY
    )
    sources[primary_wikipedia] = len(primary_imgs)
    for img in primary_imgs:
        img["_source"] = primary_wikipedia
    all_candidates.extend(primary_imgs)
    log.info("    Bilder aus '%s': %d (cap=%d)", primary_wikipedia, len(primary_imgs), MAX_IMG_PRIMARY)

    for comp_title in companion_titles:
        time.sleep(0.5)
        comp_imgs = fetch_image_candidates(
            session, comp_title, max_candidates=MAX_IMG_COMPANION
        )
        sources[comp_title] = len(comp_imgs)
        for img in comp_imgs:
            img["_source"] = comp_title
        all_candidates.extend(comp_imgs)
        log.info("    Bilder aus '%s': %d (cap=%d)", comp_title, len(comp_imgs), MAX_IMG_COMPANION)

    seen: set[str] = set()
    unique: list[dict] = []
    for img in all_candidates:
        fn = img["filename"]
        if fn not in seen:
            seen.add(fn)
            unique.append(img)

    to_check = unique[:MAX_VISION_CHECKS]
    log.info("    Kandidaten gesamt (dedupliziert): %d, Vision-Check: %d",
             len(unique), len(to_check))

    accepted: list[dict] = []
    rejected_vision: list[dict] = []
    target = APPEAL_TARGET.get(appeal, 10)
    _consecutive_dl_failures = 0

    for img in to_check:
        # Stopp sobald genug ab_stufe=1-Bilder für die restriktivste Stufe gesammelt
        if sum(1 for a in accepted if a.get("ab_stufe", 1) == 1) >= target:
            log.info("    Target %d S1-Bilder erreicht -- Vision-Check gestoppt", target)
            break

        img_bytes = download_image(session, img["thumb_url"])
        if img_bytes is None:
            rejected_vision.append({**img, "reason": "Download fehlgeschlagen"})
            _consecutive_dl_failures += 1
            if _consecutive_dl_failures >= 3:
                log.warning("    3 Downloads fehlgeschlagen -- 60s Wikimedia-Cooldown ...")
                time.sleep(60)
                _consecutive_dl_failures = 0
            else:
                time.sleep(10.0)
            continue

        _consecutive_dl_failures = 0
        mime = "image/jpeg"

        result, vision_usage = analyze_with_vision(client, img_bytes, mime, thema)
        if vision_usage:
            cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                                schritt="vision", modell="gemini-2.5-flash", **vision_usage)
        if result is None:
            rejected_vision.append({**img, "reason": "Vision-Fehler"})
            time.sleep(2.0)
            continue

        ab_stufe = result.get("ab_stufe", 0)
        confidence = result.get("confidence", "hoch")
        beschreibung = result.get("beschreibung", "")

        # Konservatives Hochstufen: unsicheres S1-Urteil → S2
        if confidence == "niedrig" and ab_stufe == 1:
            ab_stufe = 2
            log.info("    confidence=niedrig: %s → ab_stufe 1→2 (konservativ hochgestuft)",
                     img["filename"][:50])

        if ab_stufe == 0:
            rejected_vision.append({**img, "reason": f"gesperrt: {beschreibung}"})
        elif result.get("relevanz", 0) < 4:
            rejected_vision.append({**img, "reason": f"relevanz={result['relevanz']} < 4"})
        else:
            accepted.append({
                **img,
                "ab_stufe":       ab_stufe,
                "confidence":     confidence,
                "relevanz":       result.get("relevanz", 5),
                "hero_candidate": result.get("hero_candidate", False),
                "beschreibung":   beschreibung,
            })

        time.sleep(10.0)

    # ── Hero-Gate: nur Querformat darf Hero-Kandidat sein ────────────────────
    # Das Startbild steht in der App ueber dem Text; Hochformat muesste stark
    # beschnitten werden oder wird zu klein. Bilder ohne Maße (aspect=0) fallen
    # ebenfalls raus, damit kein ungeprueftes Hochformat durchrutscht.
    for a in accepted:
        if a.get("aspect", 0) < HERO_MIN_ASPECT and a.get("hero_candidate"):
            log.info("    Hero verworfen (kein Querformat, aspect=%.2f): %s",
                     a.get("aspect", 0), a["filename"][:45])
            a["hero_candidate"] = False
    if not any(a.get("hero_candidate") for a in accepted):
        quer = [a for a in accepted if a.get("aspect", 0) >= HERO_MIN_ASPECT]
        if quer:
            quer.sort(key=lambda x: (-x.get("relevanz", 0), -x.get("aspect", 0)))
            quer[0]["hero_candidate"] = True
            log.info("    Hero nachnominiert (Querformat): %s (aspect=%.2f, relevanz=%s)",
                     quer[0]["filename"][:45], quer[0].get("aspect", 0),
                     quer[0].get("relevanz"))
        else:
            log.warning("    KEIN Querformat-Bild im Pool — Hero bleibt offen")

    accepted.sort(key=lambda x: (-x["relevanz"], -int(x.get("hero_candidate", False))))

    # ── Bild-Recheck: sensible Themen, NUR unsichere Bilder (confidence=niedrig) ─
    # Nur wenn in stage_models aktiviert (provider 'anthropic'); sonst Gemini-Urteil.
    opus_overrides = 0
    opus_blocked   = 0
    from stage_models import image_recheck_model
    _recheck_model = image_recheck_model()
    if sensibel and anthropic_api_key and accepted and _recheck_model:
        opus_kandidaten = [img for img in accepted if img.get("confidence") == "niedrig"]
        stable          = [img for img in accepted if img.get("confidence") != "niedrig"]
        log.info("    Sensibles Thema '%s': Bild-Recheck (%s) fuer %d unsichere Bilder (von %d akzeptierten)",
                 thema, _recheck_model, len(opus_kandidaten), len(accepted))
        rechked: list[dict] = list(stable)
        for img in opus_kandidaten:
            img_bytes = load_cached_image_bytes(img["thumb_url"])
            if img_bytes is None:
                log.warning("    Opus-Recheck: Cache fehlt fuer %s -- Gemini-Urteil behalten",
                            img["filename"][:45])
                rechked.append(img)
                continue
            new_ab, new_desc, usage = opus_recheck(anthropic_api_key, img_bytes, thema,
                                                   model=_recheck_model)
            if usage:
                cost_tracker.track(
                    run_id=_RUN_ID, thema=thema, stufe="S0",
                    schritt="vision_recheck", modell=_recheck_model,
                    input_tok=usage.get("input_tok", 0),
                    output_tok=usage.get("output_tok", 0),
                )
            if new_ab is None:
                log.warning("    Opus-Recheck fehlgeschlagen: %s -- Gemini-Urteil behalten",
                            img["filename"][:45])
                rechked.append(img)
            elif new_ab == 0:
                opus_blocked += 1
                log.info("    Opus SPERRT: %s (%s)", img["filename"][:45], new_desc[:60])
            else:
                if new_ab != img.get("ab_stufe", 1):
                    opus_overrides += 1
                    log.info("    Opus ueberschreibt: %s ab_stufe %d→%d",
                             img["filename"][:45], img.get("ab_stufe", 1), new_ab)
                rechked.append({**img, "ab_stufe": new_ab, "beschreibung": new_desc})
        accepted = rechked
        log.info("    Opus-Recheck abgeschlossen: %d Bilder im Pool, %d ueberschrieben, %d gesperrt",
                 len(accepted), opus_overrides, opus_blocked)

    report = {
        "sources":           sources,
        "candidates_total":  len(unique),
        "vision_checked":    len(accepted) + len(rejected_vision),
        "accepted":          len(accepted),
        "rejected":          len(rejected_vision),
        "target":            target,
        "sensibel":          sensibel,
        "opus_overrides":    opus_overrides,
        "opus_blocked":      opus_blocked,
        "hero":              next(
            (a["filename"] for a in accepted if a.get("hero_candidate", False)),
            accepted[0]["filename"] if accepted else None,
        ),
    }
    return accepted, report


def _is_svg(img: dict) -> bool:
    return img.get("filename", "").lower().endswith(".svg")


def select_images_for_stufe(pool: list[dict], stufe: int, appeal: str,
                            drop_svg: bool = False) -> list[dict]:
    """Filtert Bildpool auf Altersfreigabe (ab_stufe <= stufe), cap nach APPEAL_TARGET.

    drop_svg: SVGs ganz aus dem Pool (fuer Hoerspiel — dort sind technische
    Diagramme wie Becken-Zeichnungen fehl am Platz; PO 2026-07-23). Beim Erzaehltext
    bleiben SVGs im Pool, landen aber nie im Text, nur in der Galerie (assign_images_pass).

    Companion-Abdeckung zuerst: Ein reiner Relevanz-Cap hat ganze Companions
    weggeschnitten — die 6 Archaeopteryx-Bilder fielen hinter die 20 Haupt-Dino-
    Bilder und waren beim Cap auf 15 weg, obwohl der Text ausdruecklich ueber
    Archaeopteryx spricht (PO 2026-07-23). Deshalb sichern wir pro Quelle
    (Companion) das beste Bild in den Pool, BEVOR wir mit dem relevantesten Rest
    auffuellen. So bekommt assign_images_pass fuer jeden Companion mindestens ein
    Bild zum Zuordnen."""
    def base(src: str) -> str:                # "Archaeopteryx (Leitbild)" -> "Archaeopteryx"
        return (src or "").split(" (")[0].strip()

    filtered = [img for img in pool if img.get("ab_stufe", 1) <= stufe
                and not (drop_svg and _is_svg(img))]
    filtered.sort(key=lambda x: (-x.get("relevanz", 0), -int(x.get("hero_candidate", False))))
    cap = APPEAL_TARGET.get(appeal, 10)
    if len(filtered) <= cap:
        return filtered

    picked: list[dict] = []
    seen_src: set[str] = set()
    for img in filtered:                      # je Quelle das relevanteste Bild sichern
        if len(picked) >= cap:
            break
        src = base(img.get("_source", ""))
        if src and src not in seen_src:
            picked.append(img)
            seen_src.add(src)
    for img in filtered:                      # mit dem relevantesten Rest auffuellen
        if len(picked) >= cap:
            break
        if img not in picked:
            picked.append(img)
    # picked ist bereits <= cap; nur fuer die Ausgabe nach Relevanz ordnen (KEIN
    # erneutes Cappen — das wuerde die eben gesicherten Companion-Bilder wieder
    # herausschneiden).
    picked.sort(key=lambda x: (-x.get("relevanz", 0), -int(x.get("hero_candidate", False))))
    return picked


def enforce_landscape_hero(article: dict, pool: list[dict]) -> str | None:
    """Erzwingt ein QUERFORMAT-Hero (images[0]) nach der Generierung.

    Das Modell waehlt images[0] frei; die [HERO-KANDIDAT]-Markierung im Prompt
    allein reicht nachweislich nicht (PO-Befund: Hochformat landete trotzdem als
    Hero). Der Artikel selbst traegt keine Bildmaße, deshalb kommen sie aus dem
    Pool (per filename). Ist images[0] kein Querformat, wird es mit dem ersten
    Querformat-Bild des Artikels getauscht und ALLE img_index-Verweise werden
    mitgezogen. Nebenbei werden width/height/aspect in die Artikel-Bilder
    geschrieben, damit die App das Seitenverhaeltnis kennt.

    Rueckgabe: Meldung (fuer Log/Report) oder None, wenn nichts zu tun war."""
    imgs = article.get("images") or []
    if not imgs:
        return None
    by_name = {p.get("filename", ""): p for p in pool}

    for im in imgs:                       # Maße in den Artikel uebernehmen
        p = by_name.get(im.get("filename", ""))
        if p:
            im["width"]  = p.get("width", 0)
            im["height"] = p.get("height", 0)
            im["aspect"] = p.get("aspect", 0.0)

    def asp(im: dict) -> float:
        return float(im.get("aspect") or 0.0)

    if asp(imgs[0]) >= HERO_MIN_ASPECT:
        imgs[0]["is_hero"] = True
        return None

    # Bestes Querformat waehlen — Querformat ALLEIN reicht nicht: ein breites
    # Diagramm (SVG) waere ein schlechtes Startbild. Rangfolge: vom Vision-Filter
    # als hero_candidate markiert > hohe Relevanz > Foto statt Diagramm >
    # Seitenverhaeltnis nahe 1.5 (statt extremer Panorama-Streifen).
    def hero_score(i: int) -> tuple:
        im = imgs[i]
        p  = by_name.get(im.get("filename", ""), {})
        is_svg = im.get("filename", "").lower().endswith(".svg")
        return (
            int(bool(p.get("hero_candidate"))),
            int(not is_svg),
            int(p.get("relevanz", 0)),
            -abs(asp(im) - 1.5),
        )

    quer = [i for i in range(1, len(imgs)) if asp(imgs[i]) >= HERO_MIN_ASPECT]
    swap = max(quer, key=hero_score) if quer else None
    if swap is None:
        return (f"kein Querformat-Bild im Artikel — Hero bleibt "
                f"{imgs[0].get('filename', '?')} (aspect={asp(imgs[0])})")

    old_name = imgs[0].get("filename", "?")
    imgs[0], imgs[swap] = imgs[swap], imgs[0]
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            idx = s.get("img_index")
            if idx == 0:
                s["img_index"] = swap
            elif idx == swap:
                s["img_index"] = 0
    for im in imgs:
        im.pop("is_hero", None)
    imgs[0]["is_hero"] = True
    return (f"Hero getauscht: {old_name} (aspect={asp(imgs[swap])}) -> "
            f"{imgs[0].get('filename', '?')} (aspect={asp(imgs[0])})")


IMG_ASSIGN_SYSTEM = (
    "Du ordnest einem FERTIGEN Kindertext Bilder zu. Der Text ist unveraenderlich — "
    "du schreibst nichts um, du waehlst nur aus und beschriftest.\n\n"
    "REGELN:\n"
    "- Jeder Abschnitt soll moeglichst EIN eigenes, passendes Bild bekommen. Verteile "
    "die Bilder ueber ALLE Abschnitte, nie geballt an den Anfang, und lass keinen "
    "Abschnitt leer ausgehen, solange noch ein halbwegs passendes Bild frei ist — "
    "sonst zeigt die App dort einfach das Bild des vorigen Abschnitts.\n"
    "- Ein Bild kommt an die Zeile, die am besten dazu passt (es zeigt moeglichst "
    "genau das, wovon die Zeile handelt). Gibt es fuer einen Abschnitt kein exakt "
    "passendes Bild, waehle das thematisch am besten passende statt gar keins; nur "
    "wenn wirklich KEIN Bild einen Bezug zum Abschnitt hat, lass ihn frei.\n"
    "- Jedes Bild hoechstens EINMAL zuordnen.\n"
    "- hero_index: das repraesentativste Bild des HAUPTTHEMAS (nicht eines "
    "Nebenthemas). Es MUSS ein mit [QUER] markiertes Bild sein — Hochformat ist als "
    "Startbild unbrauchbar.\n"
    "- caption: eine kurze, kindgerechte Bildunterschrift (EIN Satz), die zum "
    "wirklich geschriebenen Text passt. Nutze den ORIGINALTITEL als verlaessliche "
    "Quelle fuer den Eigennamen des gezeigten Gegenstands/Exponats oder den Ort der "
    "Aufnahme und benenne ihn konkret (Originaltitel = Metadaten, kein erfundenes "
    "Detail); erfinde darueber hinaus keine im Bild nicht sichtbaren Szenendetails.\n"
    "- alt: kurzer deutscher Bild-Titel mit Eigenname/Ort aus dem Originaltitel "
    "(max. 6 Woerter, kein ganzer Satz, kein englischer Titel)."
)

IMG_ASSIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "hero_index": {"type": "integer"},
        "zuordnung": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "zeile": {"type": "integer"},
                    "img_index": {"type": "integer"},
                },
                "required": ["zeile", "img_index"],
            },
        },
        "captions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "img_index": {"type": "integer"},
                    "caption": {"type": "string"},
                    "alt": {"type": "string"},
                },
                "required": ["img_index", "caption", "alt"],
            },
        },
    },
    "required": ["hero_index", "zuordnung", "captions"],
}


def assign_images_pass(article: dict, pool: list[dict], thema: str, model: str,
                       max_inline: int) -> str:
    """Ordnet Bilder ZU, NACHDEM der Text steht — eigener Aufruf, eigener Prompt.

    Warum getrennt: Solange Prosa und Bildzuweisung im selben Aufruf entstanden,
    konkurrierten sie um dieselbe Modellaufmerksamkeit. Angezogene Bildregeln haben
    nachweislich den Text deformiert (erfundene Bild-Anker-Zeilen, Erzaehler-Labels,
    Stakkato; PO-Befund 2026-07-22). Das ist die Rueckkehr zu pass4_images aus der
    alten 6-Pass-Pipeline: der Text ist hier fertig und wird nicht mehr angefasst.

    Nebeneffekt: Bildunterschriften passen zum WIRKLICH geschriebenen Text, nicht
    nur zum Thema — das konnte der alte Weg prinzipiell nicht.

    Mutiert article['images'] und die img_index der Saetze. Rueckgabe: Log-Meldung."""
    secs = article.get("sections", [])
    sents: list[dict] = []
    sec_of: list[int] = []                # flacher Satzindex -> Abschnittsindex
    first_line: dict[int, int] = {}       # Abschnittsindex -> erster flacher Satzindex
    for si, sec in enumerate(secs):
        for s in sec.get("sentences", []):
            first_line.setdefault(si, len(sents))
            sec_of.append(si)
            sents.append(s)
    for s in sents:                       # Ausgangszustand: kein Bild
        s["img_index"] = -1
    if not pool or not sents:
        article["images"] = []
        return "keine Bilder (Pool oder Text leer)"

    zeilen = "\n".join(f"{i}: {s.get('text','')}" for i, s in enumerate(sents))
    bilder = "\n".join(
        f"[{i}] Originaltitel \"{p.get('wikimedia_id') or p.get('filename','')}\""
        f"{' [QUER]' if float(p.get('aspect') or 0) >= HERO_MIN_ASPECT else ' [hoch]'}"
        f" — zu sehen: {(p.get('beschreibung') or p.get('alt') or '')[:200]}"
        for i, p in enumerate(pool)
    )
    body = (
        f"THEMA: {thema}\n\n"
        f"TEXT (Zeilennummer: Zeile):\n{zeilen}\n\n"
        f"BILDER (index: Originaltitel — zu sehen):\n{bilder}\n\n"
        f"Ordne HOECHSTENS {max_inline} Bilder zu (die uebrigen wandern automatisch "
        f"in eine Galerie — du musst sie nicht unterbringen). Gib fuer JEDES der "
        f"{len(pool)} Bilder eine caption und ein alt aus, auch fuer nicht zugeordnete."
    )

    try:
        raw = gemini_client.call_gemini(
            IMG_ASSIGN_SYSTEM, body, model=model,
            response_mime_type="application/json", response_schema=IMG_ASSIGN_SCHEMA,
            call_name="assign_images", max_output_tokens=8192,
        )
        data = json.loads(raw)
    except Exception as e:
        log.warning("  Bild-Zuordnung fehlgeschlagen: %s — alle Bilder in die Galerie", e)
        data = {}

    texts = {c.get("img_index"): c for c in data.get("captions", [])
             if isinstance(c, dict)}

    # Zuordnung einsammeln: pool-Index -> erste passende Zeile, jedes Bild nur einmal
    paare: list[tuple[int, int]] = []
    belegt: set[int] = set()
    for z in data.get("zuordnung", []):
        if not isinstance(z, dict):
            continue
        li, pi = z.get("zeile"), z.get("img_index")
        if not isinstance(li, int) or not isinstance(pi, int):
            continue
        if not (0 <= li < len(sents)) or not (0 <= pi < len(pool)) or pi in belegt:
            continue
        # SVGs (technische Diagramme) nie in den Text — sie bleiben Galerie (PO 2026-07-23).
        if _is_svg(pool[pi]):
            continue
        belegt.add(pi)
        paare.append((li, pi))
        if len(paare) >= max_inline:
            break

    # Abschnitt-Abdeckung: jeder Abschnitt bekommt ein eigenes Bild, sonst uebernimmt
    # die App das Bild des vorigen Abschnitts (PO 2026-07-25). Fehlt einem Abschnitt
    # ein Anker, haengt das beste noch freie Nicht-SVG-Bild an seine erste Zeile —
    # bestmoegliches Bild statt gar keins. Das darf max_inline ueberschreiten (eine
    # luekenlose Abdeckung geht der Ober-Obergrenze vor).
    def _img_rank(i: int) -> tuple[float, float]:
        p = pool[i]
        return (float(p.get("relevanz", 0) or 0), -abs(float(p.get("aspect") or 0) - 1.4))

    covered = {sec_of[li] for li, _pi in paare}
    for si in range(len(secs)):
        if si in covered:
            continue
        frei = [i for i in range(len(pool)) if i not in belegt and not _is_svg(pool[i])]
        if not frei:
            break
        best = max(frei, key=_img_rank)
        belegt.add(best)
        paare.append((first_line[si], best))
        covered.add(si)

    # Hero bestimmen — Modellwunsch nur, wenn Querformat UND kein SVG; sonst bestes Querformat.
    def quer(i: int) -> bool:
        return float(pool[i].get("aspect") or 0) >= HERO_MIN_ASPECT and not _is_svg(pool[i])

    hero = data.get("hero_index")
    if not (isinstance(hero, int) and 0 <= hero < len(pool) and quer(hero)):
        kandidaten = [i for i in range(len(pool)) if quer(i)]
        hero = max(
            kandidaten,
            key=lambda i: (int(bool(pool[i].get("hero_candidate"))),
                           int(not pool[i].get("filename", "").lower().endswith(".svg")),
                           int(pool[i].get("relevanz", 0)),
                           -abs(float(pool[i].get("aspect") or 0) - 1.5)),
        ) if kandidaten else None

    def bild(pi: int, placement: str) -> dict:
        p = pool[pi]
        t = texts.get(pi, {})
        return {
            "filename": p.get("filename", ""),
            "alt": (t.get("alt") or p.get("alt") or p.get("filename", ""))[:120],
            "caption": (t.get("caption") or "")[:300],
            "license": p.get("license", ""),
            "license_author": p.get("license_author", ""),
            "source_url": p.get("source_url", ""),
            "wikimedia_id": p.get("wikimedia_id", ""),
            "thumb_url": p.get("thumb_url", ""),
            "width": p.get("width", 0),
            "height": p.get("height", 0),
            "aspect": p.get("aspect", 0.0),
            "placement": placement,
        }

    # images[] aufbauen: Hero zuerst (App-Konvention), dann die zugeordneten,
    # dann der Rest als Galerie. pool-Index -> Artikel-Index mitfuehren.
    imgs: list[dict] = []
    pos: dict[int, int] = {}
    if hero is not None:
        pos[hero] = 0
        imgs.append(bild(hero, "inline"))
        imgs[0]["is_hero"] = True
    for _li, pi in paare:
        if pi not in pos:
            pos[pi] = len(imgs)
            imgs.append(bild(pi, "inline"))
    for li, pi in paare:
        sents[li]["img_index"] = pos[pi]
    for pi in range(len(pool)):
        if pi not in pos:
            imgs.append(bild(pi, "galerie"))

    article["images"] = imgs
    inline_n = sum(1 for im in imgs if im.get("placement") == "inline")
    hero_name = imgs[0]["filename"][:40] if imgs else "-"
    return (f"Bilder nachtraeglich zugeordnet: {len(paare)} Zeilen-Anker, "
            f"{inline_n} textbegleitend, {len(imgs) - inline_n} Galerie, "
            f"Hero={hero_name} (aspect={imgs[0].get('aspect') if imgs else 0})")


def append_gallery_images(article: dict, pool: list[dict]) -> str:
    """Trennt textbegleitende Bilder von der Galerie — deterministisch, nach der Generierung.

    Bildmenge und Prosaqualitaet duerfen nicht im selben Aufruf konkurrieren: solange
    der Prompt "schoepfe den Pool aus" verlangte, hat das Modell Zeilen erfunden, nur
    um Bilder zu verankern (PO-Befund 2026-07-22). Deshalb waehlt das Modell nur noch
    wenige Bilder FUER DEN TEXT; alles weitere Gute haengt hier der Code an.

    Jedes Bild bekommt `placement`:
      inline  — Hero (images[0]) und jedes Bild, auf das mindestens eine Zeile zeigt
      galerie — der Rest: vom Modell aufgenommen aber nie verankert (frueher "totes
                Bild"), plus alle uebrigen vom Vision-Filter akzeptierten Pool-Bilder

    Dadurch kann es per Konstruktion keine toten Bilder mehr geben."""
    imgs = article.get("images") or []
    if not imgs:
        return "keine Bilder"

    used = {s.get("img_index") for sec in article.get("sections", [])
            for s in sec.get("sentences", []) if isinstance(s.get("img_index"), int)}
    for i, im in enumerate(imgs):
        im["placement"] = "inline" if (i == 0 or i in used) else "galerie"
    demoted = sum(1 for i, im in enumerate(imgs)
                  if im["placement"] == "galerie" and i > 0)

    have = {im.get("filename", "") for im in imgs}
    added = 0
    for p in pool:
        fn = p.get("filename", "")
        if not fn or fn in have:
            continue
        imgs.append({
            "filename": fn,
            "alt": p.get("beschreibung") or p.get("alt") or fn,
            "caption": p.get("beschreibung") or "",
            "license": p.get("license", ""),
            "license_author": p.get("license_author", ""),
            "source_url": p.get("source_url", ""),
            "thumb_url": p.get("thumb_url", ""),
            "wikimedia_id": p.get("wikimedia_id", ""),
            "width": p.get("width", 0),
            "height": p.get("height", 0),
            "aspect": p.get("aspect", 0.0),
            "placement": "galerie",
        })
        have.add(fn)
        added += 1

    inline_n = sum(1 for im in imgs if im.get("placement") == "inline")
    return (f"Bilder: {inline_n} textbegleitend, {len(imgs) - inline_n} Galerie "
            f"({demoted} unverankert abgestuft, {added} aus Pool ergaenzt)")


# Das Modell schreibt den Erzaehler gelegentlich als Sprecher-Label in den Satztext
# ("Der Erzaehler berichtet: ...", "Erzaehler Professor erklaert, dass ..."). Der
# Text IST das Audio (Mitlese-Lupe) — solche Zeilen wuerden mitgesprochen und machen
# den Erzaehler zur handelnden Figur. Prompt-Verbot allein reicht nicht, deshalb hart
# pruefen (PO-Befund 2026-07-22).
ERZAEHLER_LABEL_RE = re.compile(
    r"^\s*(?:Der\s+)?Erzähler(?:\s+Professor)?\s+"
    r"(?:berichtet|beschreibt|erklärt|erzählt|schildert|sagt|schließt|fährt\s+fort)"
    r"\b|^\s*Erzähler\s*:",
    re.IGNORECASE,
)


def find_erzaehler_labels(article: dict) -> list[str]:
    """Zeilen, in denen der Erzaehler sich selbst als Sprecher benennt."""
    hits = []
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            if ERZAEHLER_LABEL_RE.search(s.get("text", "")):
                hits.append(s.get("text", "")[:70])
    return hits


def _variable_suffix(job: dict, wmax: int) -> str:
    """Variabler Suffix je Inhaltstyp: AGE_LEVEL + Bild-Stufen-Filter + WORTZIEL.
    Muss identisch in build_grounded_user_message und _split_grounded_user_message sein.

    AGE_LEVEL (Sprachstufe) und BILD-STUFEN-FILTER sind ENTKOPPELT: Hörspiele
    können 7–9-Sprache tragen (prompt_age_level 2), aber nach jüngstem Zuschauer
    nur ab_stufe=1-Bilder (image_stufe 1). Plan §4."""
    age_level   = job.get("prompt_age_level", job.get("age_level", 2))
    image_stufe = job.get("image_stufe", age_level)
    # STORY_PLAN (Hoerspiel, neue Mechanik): der in einem eigenen Aufruf vorab
    # erstellte <planung>-Block. Steht bewusst im variablen Suffix — er ist
    # artikelspezifisch und darf den geteilten Cache-Prefix nicht veraendern.
    plan = (job.get("story_plan") or "").strip()
    plan_block = ""
    if plan:
        plan_block = (
            "STORY_PLAN — SCHRITT 1 ist bereits erledigt. Der folgende "
            "<planung>-Block wurde vorab erstellt. UEBERNIMM ihn als verbindliche "
            "Grundlage (Rahmen, Fenster, Erzaehlfaden, Dialog-Rhythmus) und plane "
            "NICHT neu. Fuehre jetzt nur noch SCHRITT 2 aus: schreibe das "
            "Hoerspiel-JSON gemaess diesem Plan. Weiche nicht vom Rahmen und der "
            "Fenster-Auswahl ab.\n" + plan + "\n\n"
        )
    return (
        plan_block +
        f"AGE_LEVEL: {age_level}\n"
        f"BILD-STUFEN-FILTER: Ausschliesslich Bilder mit ab_stufe<={image_stufe} "
        f"verwenden. Bilder mit ab_stufe>{image_stufe} ignorieren.\n"
        f"WORTZIEL: Strebe {wmax} Woerter an und schoepfe den Wikipedia-Stoff so weit aus, "
        f"dass du nah an {wmax} herankommst. "
        f"{wmax} ist zugleich die harte Obergrenze — schreibe nicht darueber hinaus. "
        f"Wenn nach Erreichen von {wmax} noch Stoff uebrig ist, waehle die kindgerechtesten Aspekte aus, "
        f"statt alles aufzunehmen. "
        f"Kuerzer als {wmax} nur, wenn der Wikipedia-Stoff die Laenge nicht hergibt — niemals aufblaehen."
    )


def _merge_split_speech_tags(article: dict) -> int:
    """Hörspiel-Normalisierung: fasst eine über mehrere sentences[]-Einträge
    zerrissene Sprech-Handlung wieder zu EINEM Eintrag zusammen (wie Leo).

    Flash legt eine Sprech-Handlung stochastisch getrennt ab. Zwei Fälle, beide
    grammatisch unvollständig → der Eintrag wird mit dem/den Folge-Eintrag/en
    verschmolzen, bis er wieder vollständig ist:
      A) endet auf schließendes Anführungszeichen + Komma (»…!",«) → ein
         Redebegleitsatz muss folgen (»…!", ruft Theo.«).
      B) öffnet ein Anführungszeichen, das im selben Eintrag nicht schließt
         (mehr „ als ") → die wörtliche Rede läuft in den nächsten Eintrag weiter.
    Ausnahme: endet der Eintrag auf »,« UND öffnet der nächste eine NEUE Rede
    (führendes „), wird nicht gemergt (mehrdeutig → in Ruhe lassen).
    Gibt die Zahl der entfernten (verschmolzenen) Einträge zurück; bei >0 werden
    die Satz-IDs global neu vergeben (s001, s002 …).
    """
    CLOSE = "“"   # deutsches schließendes Anführungszeichen "
    OPEN  = "„"   # deutsches öffnendes Anführungszeichen „

    def _incomplete(t: str) -> bool:
        t = t.rstrip()
        return t.endswith(CLOSE + ",") or (t.count(OPEN) > t.count(CLOSE))

    removed = 0
    for sec in article.get("sections", []):
        sents = sec.get("sentences", []) or []
        out: list[dict] = []
        i = 0
        while i < len(sents):
            cur = dict(sents[i])
            txt = (cur.get("text") or "").rstrip()
            j = i + 1
            while _incomplete(txt) and j < len(sents):
                nxt_txt = (sents[j].get("text") or "").strip()
                # Fall A + Folge-Eintrag öffnet neue Rede → mehrdeutig, abbrechen.
                if txt.endswith(CLOSE + ",") and nxt_txt.startswith(OPEN):
                    break
                txt = (txt + " " + nxt_txt).rstrip()
                j += 1
                removed += 1
            cur["text"] = txt
            out.append(cur)
            i = j
        sec["sentences"] = out
    if removed:
        n = 0
        for sec in article.get("sections", []):
            for s in sec.get("sentences", []):
                n += 1
                s["id"] = f"s{n:03d}"
    return removed


# Gegenstueck zu _merge_split_speech_tags: eine Zeile darf hoechstens EINE
# woertliche Rede enthalten (im Hoerspiel = ein Sprecher). Steckt eine zweite
# Rede dahinter — erkennbar an einer schliessenden Rede, gefolgt von einem
# Redebegleitsatz bis zum Satzende, direkt vor einer NEU oeffnenden Rede —,
# gehoert sie in eine eigene Zeile. Sonst spricht spaeter die falsche Stimme und
# die Mitlese-Lupe verrutscht (PO 2026-07-23). Reine Satzlaenge ist KEIN Signal:
# ein langer durchgehender Erzaehlsatz ist voellig in Ordnung.
_DOUBLE_SPEECH_RE = re.compile(r'(“[^„“]*?[.!?])\s+(?=„)')


def _split_double_speech_lines(article: dict) -> int:
    """Trennt Hoerspiel-Zeilen mit mehr als einer Rede in je eigene Zeilen.
    Gibt die Zahl der neu entstandenen (zusaetzlichen) Zeilen zurueck; bei >0
    werden die Satz-IDs global neu vergeben."""
    added = 0
    for sec in article.get("sections", []):
        out: list[dict] = []
        for s in sec.get("sentences", []) or []:
            txt = (s.get("text") or "").strip()
            teile = [p.strip() for p in _DOUBLE_SPEECH_RE.split(txt) if p and p.strip()]
            if len(teile) <= 1:
                out.append(s)
                continue
            for k, t in enumerate(teile):
                neu = dict(s) if k == 0 else {"text": t, "img_index": -1}
                neu["text"] = t
                out.append(neu)
            added += len(teile) - 1
        sec["sentences"] = out
    if added:
        n = 0
        for sec in article.get("sections", []):
            for s in sec.get("sentences", []):
                n += 1
                s["id"] = f"s{n:03d}"
    return added


def find_multi_speech_lines(article: dict) -> list[str]:
    """Sicherheitsnetz: Zeilen, die NACH dem Auftrennen noch mehr als eine Rede
    tragen (z. B. verschachtelte Faelle, die die Regex nicht fasst)."""
    hits = []
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            t = s.get("text", "")
            if t.count("„") >= 2 and _DOUBLE_SPEECH_RE.search(t):
                hits.append(t[:80])
    return hits


# Flash schreibt gelegentlich englische Funktionswoerter in den deutschen Text —
# beobachtet: „But …" statt „Aber …" (spielzeug_hoerspiel, 3×; PO 2026-07-23).
# Deterministisch ersetzen: nur als eigenstaendiges Wort am Zeilen-/Satz-/Rede-
# Anfang, damit kein Eigenname (z. B. „Butler") getroffen wird.
_ENGL_SLIPS = [
    (re.compile(r'(^|["„»‚\s])But(\s+)'), r'\1Aber\2'),
    (re.compile(r'(^|["„»‚\s])And(\s+)'), r'\1Und\2'),
]


def fix_language_slips(article: dict) -> int:
    """Ersetzt vereinzelte englische Funktionswoerter im Fliesstext. Gibt die
    Zahl der geaenderten Zeilen zurueck."""
    n = 0
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            orig = s.get("text", "")
            fixed = orig
            for rx, repl in _ENGL_SLIPS:
                fixed = rx.sub(repl, fixed)
            if fixed != orig:
                s["text"] = fixed
                n += 1
    return n


# Box-Anti-Redundanz: eine Callout-Box (WOW/FAKT/STIMMT-DAS) soll etwas NEUES
# bringen, nicht einen Satz aus dem Fliesstext wiederholen. Der alte Box-Pass
# (pipeline_new.pass3_boxes) hatte dafuer Prompt-Regel UND Code-Check; beim Umbau
# auf den Einzel-Call ging beides verloren, die Wiederholungen kamen zurueck
# (PO 2026-07-23, v. a. Vulkan). Leichter Schwellwert: nur bei starker Ueberlappung
# mit EINEM Satz melden.
_BOX_STOP = {"eine", "einen", "einem", "einer", "eines", "und", "oder", "aber",
             "der", "die", "das", "den", "dem", "des", "sich", "auch", "sehr",
             "wird", "werden", "kann", "koennen", "sind", "haben", "diese",
             "dieser", "dieses", "nach", "beim", "durch", "noch", "sein",
             "seine", "ihre", "mehr", "etwa", "wenn", "dann", "hier", "dort"}
# Anteil der Box-Inhaltswoerter, die schon IRGENDWO im Fliesstext stehen. Empirie
# (PO-Review 2026-07-23): die als „Wiederholung" monierten Vulkan-Boxen lagen bei
# 62–94 %, die als gut befundenen Dino-Boxen bei 25–30 % — 0.60 trennt mit Abstand.
_BOX_TEXT_OVERLAP = 0.60
# Fast woertliche Dopplung EINES Satzes (auch wenn die Box neue Begriffe streut).
_BOX_SENT_OVERLAP = 0.8
_BOX_MIN_CONTENT_WORDS = 5


def _box_content_words(text: str) -> set:
    toks = re.findall(r"[a-zA-ZäöüÄÖÜß]+", (text or "").lower())
    return {t for t in toks if len(t) >= 4 and t not in _BOX_STOP}


def _redundant_box_refs(article: dict) -> list[tuple]:
    """Wie find_redundant_boxes, aber mit Position: (sec_index, box_index, box, overlap)."""
    sentences = [s.get("text", "") for sec in article.get("sections", [])
                 for s in sec.get("sentences", [])]
    sent_words = [_box_content_words(t) for t in sentences]
    text_words: set = set().union(*sent_words) if sent_words else set()
    refs = []
    for si, sec in enumerate(article.get("sections", [])):
        for bi, box in enumerate(sec.get("boxes", []) or []):
            full = (box.get("text", "") + " " + box.get("reveal_text", "")).strip()
            bw = _box_content_words(full)
            if len(bw) < _BOX_MIN_CONTENT_WORDS:
                continue
            whole = len(bw & text_words) / len(bw)
            per_sent = max((len(bw & sw) / len(bw) for sw in sent_words if sw), default=0)
            if whole >= _BOX_TEXT_OVERLAP or per_sent >= _BOX_SENT_OVERLAP:
                refs.append((si, bi, box, whole))
    return refs


def find_redundant_boxes(article: dict) -> list[str]:
    """Boxen, die nichts Neues bringen: entweder stehen fast alle ihre
    Inhaltswoerter schon irgendwo im Fliesstext (Aussage nur zusammengefasst),
    oder sie doppeln fast woertlich EINEN Satz. Der alte Box-Pass hatte den
    Schutz, der Einzel-Call verlor ihn (PO 2026-07-23, v. a. Vulkan)."""
    return [f"[{(box.get('type','box') or 'box').upper()}] {box.get('text','')[:70]} ({whole:.0%} im Text)"
            for _si, _bi, box, whole in _redundant_box_refs(article)]


_REGEN_BOX_SYSTEM = (
    "Du ersetzt Callout-Boxen in einem fertigen Kinderlexikon-Artikel. Jede "
    "genannte Box WIEDERHOLT nur den Fliesstext — das ist wertlos. Schreibe fuer "
    "jede eine NEUE Box, die etwas bringt, das NICHT im Artikel steht.\n\n"
    "REGELN:\n"
    "- Der Box-Inhalt stammt AUSSCHLIESSLICH aus dem gelieferten QUELLTEXT "
    "(kein erfundener Fakt, keine Zahl aus dem Gedaechtnis).\n"
    "- Der neue Fakt darf NICHT schon im Artikeltext stehen — bring etwas Neues, "
    "Ueberraschendes, das ein Kind staunen laesst.\n"
    "- Typ beibehalten. Bei 'stimmt_das': text = kurze Frage, reveal_text = "
    "Antwort. Bei 'wow'/'fakt'/'warnung': der ganze Inhalt in text, KEIN reveal_text.\n"
    "- Hoechstens ein bis zwei Saetze, kindgerecht.\n"
    "- Findest du in der Quelle keinen passenden NEUEN Fakt fuer eine Box, gib "
    "fuer sie text: \"\" zurueck (dann wird sie entfernt)."
)

_REGEN_BOX_SCHEMA = {
    "type": "object",
    "properties": {
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "type": {"type": "string"},
                    "text": {"type": "string"},
                    "reveal_text": {"type": "string"},
                },
                "required": ["index", "text"],
            },
        },
    },
    "required": ["boxes"],
}


def regenerate_redundant_boxes(article: dict, primary_text: str,
                               companion_texts: dict, thema: str, model: str) -> str:
    """Ersetzt Boxen, die den Fliesstext wiederholen, durch NEUE Boxen aus
    Quell-Fakten, die im Artikel fehlen (PO 2026-07-23: Boxen behalten, aber
    inhaltlich neu — nicht loeschen). Analog zu assign_images_pass: eigener
    Aufruf auf dem fertigen Text. Scheitert der Aufruf (503), bleiben die alten
    Boxen stehen und werden geflaggt (kein Datenverlust)."""
    refs = _redundant_box_refs(article)
    if not refs:
        return ""

    sects = article.get("sections", [])
    artikel_txt = "\n".join(s.get("text", "") for sec in sects
                            for s in sec.get("sentences", []))
    quelle = primary_text[:6000]
    for comp, txt in (companion_texts or {}).items():
        if txt:
            quelle += f"\n\n=== {comp} ===\n{txt[:1500]}"

    liste = "\n".join(
        f"[{i}] Typ={box.get('type','fakt')} | Abschnitt „{sects[si].get('heading','')}\" "
        f"| wiederholt: {box.get('text','')[:80]}"
        for i, (si, bi, box, _ov) in enumerate(refs))
    body = (
        f"THEMA: {thema}\n\n"
        f"ARTIKELTEXT (schon gesagt — NICHTS hieraus wiederholen):\n{artikel_txt}\n\n"
        f"QUELLTEXT (nur hieraus schoepfen):\n{quelle}\n\n"
        f"ZU ERSETZENDE BOXEN:\n{liste}\n\n"
        f"Gib fuer jeden Index eine neue Box zurueck."
    )
    try:
        raw = gemini_client.call_gemini(
            _REGEN_BOX_SYSTEM, body, model=model,
            response_mime_type="application/json", response_schema=_REGEN_BOX_SCHEMA,
            call_name="regen_boxes", max_output_tokens=2048)
        data = json.loads(raw)
    except Exception as e:
        log.warning("  Box-Neugenerierung fehlgeschlagen: %s — alte Boxen bleiben, geflaggt", e)
        return f"FEHLER: {len(refs)} redundante Boxen nicht ersetzt ({str(e)[:40]})"

    by_index = {b.get("index"): b for b in data.get("boxes", []) if isinstance(b, dict)}
    ersetzt, entfernt = 0, 0
    # Von hinten arbeiten, damit box_index beim Entfernen stabil bleibt.
    for i, (si, bi, _box, _ov) in sorted(enumerate(refs), key=lambda x: -x[1][1]):
        neu = by_index.get(i)
        boxes = sects[si].get("boxes", [])
        if not (0 <= bi < len(boxes)):
            continue
        new_text = (neu or {}).get("text", "").strip()
        if not new_text:
            boxes.pop(bi)
            entfernt += 1
            continue
        typ = boxes[bi].get("type", "fakt")
        boxes[bi]["text"] = new_text
        if typ == "stimmt_das":
            rt = (neu or {}).get("reveal_text", "").strip()
            if rt:
                boxes[bi]["reveal_text"] = rt
        else:
            boxes[bi].pop("reveal_text", None)
        ersetzt += 1

    # Nachkontrolle: ist eine neue Box wieder redundant?
    rest = len(_redundant_box_refs(article))
    return (f"Box-Neugenerierung: {ersetzt} ersetzt, {entfernt} entfernt "
            f"(kein Quell-Fakt), {rest} weiterhin redundant")


# ── SCHRITT 7: Kinder-Lektorat (Hoerspiel) ───────────────────────────────────
# Finaler Pruef-/Korrektur-Pass auf dem FERTIGEN Hoerspiel, analog einem Lektorat
# (PO-Wunsch 2026-07-24: „ein 7. Schritt wie ein Lektorat"). Er raeumt die drei
# Dinge weg, die Flash trotz Prompt-Regel bei geschichtslastigen Themen liegen
# laesst — ein enger Gemini-Umschreibe-Pass NUR auf den betroffenen Zeilen (Rest
# woertlich), 503-sicher. Die Regeln stehen laengst im Prompt und werden ignoriert,
# darum ein deterministischer Backstop.
#
# Nuance Jahreszahlen (PO 2026-07-24): NICHT „null Jahreszahlen", sondern
#   • AUSGESCHRIEBENE Jahreszahlen ('achtzehnhundert…', 'nach Christus') → NIE erlaubt
#   • nackte Ziffern-Jahre → in Massen ok; erst ueber einem Deckel die ueberzaehligen
#     relativieren (die wichtigsten bleiben konkret).
#   • Tagesdaten ('28. Januar 1958') → auf grobe Zeit reduzieren.
#   • Waffen-/Bomben-Vergleiche ('Hiroshima-Bomben') → harmloses Bild.
_HOERSPIEL_NAKED_YEAR_CAP = 3

_SPELLED_YEAR_PATTERNS = [
    # ausgeschriebene historische Jahre (…hundert…); „zweitausend…" bewusst NICHT,
    # sonst wuerde die relative Wendung „vor fast zweitausend Jahren" faelschlich
    # als Jahreszahl gewertet (genau die gewuenschte Korrektur).
    re.compile(r'(?:sechzehn|siebzehn|achtzehn|neunzehn)hundert', re.IGNORECASE),
    re.compile(r'\b(?:nach|vor)\s+Christus\b', re.IGNORECASE),
    re.compile(r'\b[nv]\.\s?Chr\.?', re.IGNORECASE),
]
_NAKED_YEAR = re.compile(r'(?<!\d)(?:1[0-9]\d\d|20\d\d)(?!\d)')
_DAY_DATE = re.compile(r'\b\d{1,2}\.\s?(?:Januar|Februar|März|Maerz|April|Mai|Juni|Juli|'
                       r'August|September|Oktober|November|Dezember)\b')
# Waffen-/Bomben-Bezug als Vergleich (NICHT die Geologie-'Vulkanbombe' treffen):
_WEAPON_CMP = re.compile(r'\b(?:hiroshima|nagasaki|atombombe\w*|atomwaffe\w*|'
                         r'kernwaffe\w*|wasserstoffbombe\w*|nuklear\w*)\b', re.IGNORECASE)


def _lektorat_issue_rows(article: dict) -> tuple[list, int]:
    """Pro Zeile die Verstoss-Gruende + Gesamtzahl nackter Jahreszahlen.
    Rueckgabe: ([(si, sj, text, reasons:set)], naked_total)."""
    rows, naked_total = [], 0
    for si, sec in enumerate(article.get("sections", [])):
        for sj, s in enumerate(sec.get("sentences", [])):
            t = s.get("text", "") or ""
            reasons = set()
            if any(rx.search(t) for rx in _SPELLED_YEAR_PATTERNS):
                reasons.add("spelled_year")
            if _DAY_DATE.search(t):
                reasons.add("day_date")
            if _WEAPON_CMP.search(t):
                reasons.add("weapon")
            nk = len(_NAKED_YEAR.findall(t))
            if nk:
                naked_total += nk
                reasons.add("naked_year")
            if reasons:
                rows.append((si, sj, t, reasons))
    return rows, naked_total


def find_kinder_lektorat_issues(article: dict) -> list[str]:
    """Kurzliste verbleibender harter Verstoesse (fuer Report/Review-Flag).
    Nackte Jahreszahlen UNTER dem Deckel zaehlen NICHT als Verstoss (erlaubt)."""
    rows, naked_total = _lektorat_issue_rows(article)
    over = naked_total > _HOERSPIEL_NAKED_YEAR_CAP
    out = []
    for _si, _sj, t, reasons in rows:
        hard = {r for r in reasons if r in ("spelled_year", "day_date", "weapon")}
        if over and "naked_year" in reasons:
            hard.add(f"zu_viele_jahreszahlen({naked_total})")
        if hard:
            out.append(f"{', '.join(sorted(hard))} :: {t[:70]}")
    return out


_KINDER_LEKTORAT_SYSTEM = (
    "Du bist Kinder-Lektor fuer ein Hoerspiel (4-9 Jahre) und korrigierst EINZELNE "
    "gelieferte Zeilen. Zu jeder Zeile stehen ihre PROBLEME dabei. Behebe GENAU diese "
    "Probleme und aendere sonst NICHTS:\n"
    "- 'ausgeschriebene Jahreszahl' (z. B. 'achtzehnhundertdreiundsechzig', 'im Jahr "
    "neunundsiebzig nach Christus'): mach die Zeit RELATIV ('vor sehr langer Zeit', "
    "'vor fast zweitausend Jahren', 'vor mehr als hundert Jahren'). Eine ausgeschriebene "
    "Jahreszahl ist IMMER verboten.\n"
    "- 'exaktes Tagesdatum' (z. B. 'am 28. Januar 1958'): auf grobe Zeit reduzieren "
    "('vor vielen Jahrzehnten').\n"
    "- 'Waffen-/Bomben-Vergleich': ersetze ihn durch ein harmloses, greifbares Bild "
    "(ein gewaltiges Gewitter, ein ganzer Berg) oder lass die Groesse weg.\n"
    "- 'zu viele Jahreszahlen': Insgesamt duerfen HOECHSTENS ZWEI, DREI konkrete "
    "Ziffern-Jahreszahlen im ganzen Stueck bleiben - die erzaehlerisch WICHTIGSTEN. "
    "Mach die uebrigen Ziffern-Jahreszahlen in diesen Zeilen relativ; die eine, zwei "
    "wichtigsten darfst du als Ziffer stehen lassen.\n\n"
    "STRENGE REGELN: Erhalte den GESAMTEN Rest der Zeile WOERTLICH - Redebegleitsatz "
    "('sagt Oma Rosa'), typografische Anfuehrungszeichen, Namen, Sachfakten, Satzzeichen. "
    "Erfinde KEINE neue Jahreszahl und KEINEN neuen Fakt. Gib EXAKT so viele Eintraege "
    "zurueck wie geliefert, jeder mit seinem index."
)

_KINDER_LEKTORAT_SCHEMA = {
    "type": "object",
    "properties": {
        "zeilen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
            },
        },
    },
    "required": ["zeilen"],
}

# Reason-Code -> Klartext fuer den Lektorats-Auftrag.
_LEKTORAT_REASON_TEXT = {
    "spelled_year": "ausgeschriebene Jahreszahl",
    "day_date":     "exaktes Tagesdatum",
    "weapon":       "Waffen-/Bomben-Vergleich",
    "naked_year":   "zu viele Jahreszahlen",
}


def kinder_lektorat_pass(article: dict, content_type: str, thema: str, model: str) -> str:
    """SCHRITT 7 – Kinder-Lektorat (nur Hoerspiel): ausgeschriebene Jahreszahlen und
    Tagesdaten relativieren, Waffen-/Bomben-Vergleiche entschaerfen, ueberzaehlige
    Ziffern-Jahreszahlen ueber dem Deckel reduzieren. Einzelne Ziffern-Jahre bleiben
    erlaubt (PO 2026-07-24). Ein enger Gemini-Pass auf den betroffenen Zeilen;
    scheitert er (503), bleiben die Zeilen und der Aufrufer flaggt zum Review."""
    if content_type != "hoerspiel":
        return ""
    rows, naked_total = _lektorat_issue_rows(article)
    over_cap = naked_total > _HOERSPIEL_NAKED_YEAR_CAP

    fix = []   # (si, sj, text, reason_codes_to_fix)
    for si, sj, t, reasons in rows:
        todo = {r for r in reasons if r in ("spelled_year", "day_date", "weapon")}
        if over_cap and "naked_year" in reasons:
            todo.add("naked_year")   # nur bei Uebermass anfassen
        if todo:
            fix.append((si, sj, t, todo))
    if not fix:
        return ""

    liste = "\n".join(
        f"[{i}] PROBLEME: {'; '.join(_LEKTORAT_REASON_TEXT[r] for r in sorted(todo))}\n"
        f"    ZEILE: {t}"
        for i, (_si, _sj, t, todo) in enumerate(fix))
    body = (f"THEMA: {thema}\n\nZU KORRIGIERENDE ZEILEN:\n{liste}\n\n"
            f"Gib fuer jeden Index die korrigierte Zeile zurueck.")
    try:
        raw = gemini_client.call_gemini(
            _KINDER_LEKTORAT_SYSTEM, body, model=model,
            response_mime_type="application/json", response_schema=_KINDER_LEKTORAT_SCHEMA,
            call_name="kinder_lektorat", max_output_tokens=2048)
        data = json.loads(raw)
    except Exception as e:
        log.warning("  Kinder-Lektorat fehlgeschlagen: %s — Zeilen bleiben, geflaggt", e)
        return f"FEHLER: {len(fix)} Zeilen nicht lektoriert ({str(e)[:40]})"

    by_index = {b.get("index"): b for b in data.get("zeilen", []) if isinstance(b, dict)}
    sects = article.get("sections", [])
    ersetzt = 0
    for i, (si, sj, _t, todo) in enumerate(fix):
        neu = (by_index.get(i) or {}).get("text", "").strip()
        if not neu:
            continue
        # Sicherheitsnetz: die HARTEN Verstoesse (ausgeschrieben/Datum/Waffe) muessen
        # in der neuen Zeile wirklich weg sein, sonst nicht uebernehmen.
        if "spelled_year" in todo and any(rx.search(neu) for rx in _SPELLED_YEAR_PATTERNS):
            continue
        if "day_date" in todo and _DAY_DATE.search(neu):
            continue
        if "weapon" in todo and _WEAPON_CMP.search(neu):
            continue
        try:
            sects[si]["sentences"][sj]["text"] = neu
            ersetzt += 1
        except (IndexError, KeyError):
            continue
    rest = len(find_kinder_lektorat_issues(article))
    return (f"Kinder-Lektorat (Schritt 7): {ersetzt}/{len(fix)} Zeilen korrigiert, "
            f"{rest} harte Verstoesse verbleibend")


# ── Phase-2-User-Message ──────────────────────────────────────────────────────

def build_grounded_user_message(
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    companion_order: list[str],
    images: list[dict],
) -> str:
    """
    Baut die User-Message mit stabilem Quell-Prefix und variablem AGE_LEVEL am Ende.
    Stabiler Prefix (gleich für alle Stufen eines Themas) → Prompt-Caching greift.
    """
    thema = job.get("thema", job["title"])
    primaer_src = job.get("primaer_wikipedia", job["title"])
    parts: list[str] = []

    # ── Stabiler Prefix: Wikipedia-Texte ─────────────────────────────────────
    parts += [f"WIKIPEDIA_TEXT_1 (Primaarartikel: {primaer_src}):", primary_text, ""]
    for i, comp in enumerate(companion_order, 2):
        text = companion_texts.get(comp, "")
        if text:
            parts += [f"WIKIPEDIA_TEXT_{i} (Begleitartikel: {comp}):", text[:COMPANION_CHAR_CAP], ""]

    # Stabile Metadaten
    parts.append(f"ARTICLE_TITLE: {thema}")
    if job.get("topic_interest"):
        parts.append(f"TOPIC_INTEREST: {job['topic_interest']}")
    if companion_order:
        parts.append(f"VERWENDETE_BEGLEITTEXTE: {', '.join(companion_order)}")
    dd = job.get("doppelbedeutung_directive", "")
    if dd:
        parts.append(f"DOPPELBEDEUTUNG: {dd}")
    fr = job.get("framing_note", "")
    if fr:
        parts.append(f"FRAMING: {fr}")
    # Kompass-Schreibplan: die in Phase 1 gewaehlten Aspekte/Fenster. Ohne diese
    # Weitergabe erzeugt Kompass zwar den Plan (inkl. Companions wie Moby Dick),
    # die Generierung ignoriert ihn aber und faellt auf Default-Sachkunde zurueck.
    # Typ-agnostisch (gilt fuer Hoerspiel + Erzaehltext) → bleibt im stabilen Prefix.
    plan = (job.get("kompass_plan") or "").strip()
    if plan:
        parts.append(
            "SCHREIBPLAN (in Phase 1 gewaehlte Aspekte/Fenster fuer diese Folge — "
            "richte deine Fenster danach aus und setze die genannten Aspekte "
            "TATSAECHLICH um, besonders die erzaehlerisch reichen Hoehepunkte "
            "(beruehmte Geschichten, Ereignisse, Verwandte); lass keinen im Plan "
            "genannten Hoehepunkt aus):\n" + plan
        )

    # Bildpool (stabil — gleiche Images für alle Stufen).
    # Leer, wenn die Zuordnung nachgelagert laeuft (DEFER_IMAGES): dann darf der
    # Bildpool die Prosa gar nicht erst erreichen — siehe assign_images_pass().
    if not images:
        parts += [
            "",
            "BILDER: Fuer diesen Artikel werden die Bilder NACHTRAEGLICH zugeordnet, "
            "wenn dein Text fertig ist. Gib deshalb images als LEERES Array aus "
            "(\"images\": []) und setze in JEDER Zeile img_index auf -1. "
            "Denke beim Schreiben nicht an Bilder: schreibe keine Zeile, um ein Bild "
            "unterzubringen, und dehne keine Stelle fuer eine Bildbeschreibung. "
            "Der Text steht fuer sich allein.",
        ]
    if images:
        parts += [
            "",
            "AVAILABLE_IMAGES (kindgerecht geprueft, mit Beschreibung):",
        ]
        for idx, img in enumerate(images):
            author = img.get("license_author", "")[:40]
            desc = img.get("beschreibung", "")
            hero_flag = " [HERO-KANDIDAT]" if img.get("hero_candidate") else ""
            line = (
                f"[{idx}] {img['filename']} | ab_stufe={img.get('ab_stufe', 1)} | {img['thumb_url']} | "
                f"{img['license']} | {author}"
            )
            if desc:
                line += f"\n    Beschreibung: {desc}{hero_flag} Relevanz: {img['relevanz']}/10"
            parts.append(line)
        # Nur noch die TEXTBEGLEITENDEN Bilder werden hier verlangt. Alles weitere
        # Gute aus dem Pool haengt der Code danach als Galerie an (append_gallery_images).
        # Vorher forderte der Prompt "SCHOEPFE den Pool AUS" + "jedes Bild muss verankert
        # sein" — das erzeugte Bild-Anker-Zeilen und hat die Prosa deformiert
        # (Erzaehler-Labels, Stakkato; PO-Befund 2026-07-22).
        _inline_band = {"high": "6–8", "medium": "5–7", "low": "3–5"}.get(
            job.get("resolved_appeal", "medium"), "5–7"
        )
        parts += [
            "",
            "Bildauswahl-Regeln:",
            "- images[0] = Hero-Bild: das repraesentativste Foto des HAUPTTHEMAS (nicht eines Companions). Es MUSS eines der mit [HERO-KANDIDAT] markierten Bilder sein — diese sind garantiert QUERFORMAT. Hochformat ist als Hero unbrauchbar, weil es in der App ueber dem Text steht und sonst stark beschnitten wird.",
            "- thumb_url in images[] = URL aus AVAILABLE_IMAGES (exakt uebernehmen)",
            "- img_index in sentences = 0-basierter Index in DEINEM images[]-Array",
            "- Jede Datei nur EINMAL in images[] aufnehmen (keine Dubletten im Array)",
            f"- {_inline_band} textbegleitende Bilder (zzgl. Hero) — mehr nicht. Waehle nur Bilder, zu denen es OHNEHIN eine Zeile gibt, und verteile sie auf verschiedene Stationen des Textes.",
            "- DER TEXT FUEHRT, NIE DAS BILD: Schreibe niemals eine Zeile, nur damit ein Bild einen Anker bekommt, und dehne keine Stelle, um ein Bild unterzubringen. Passt zu einer Zeile kein angebotenes Bild, dann `img_index: -1` — das ist der Normalfall, kein Mangel.",
            "- Uebrige gute Bilder musst du NICHT unterbringen: was du nicht textbegleitend brauchst, haengt die App automatisch als Galerie ans Ende. Nimm sie also gar nicht erst in images[] auf.",
            "- Fuer jedes Bild: filename, alt, caption, license, license_author, source_url, thumb_url befuellen",
        ]

    # ── Variabler Suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL je Typ ─
    wmin, wmax, _wz_src = wortziel_for(thema, _job_ct(job))
    parts.append(_variable_suffix(job, wmax))

    return "\n".join(parts)


def _split_grounded_user_message(
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    companion_order: list[str],
    images: list[dict],
) -> tuple[str, str]:
    """Teilt die User-Message in (stabiler_prefix, variabler_suffix).

    stabiler_prefix: Wikipedia-Texte + Metadaten + Bilder (gleich für alle Stufen)
    variabler_suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL (je Stufe verschieden)
    """
    full = build_grounded_user_message(
        job, primary_text, companion_texts, companion_order, images
    )
    thema  = job.get("thema", job.get("title", ""))
    wmin, wmax, _wz_src = wortziel_for(thema, _job_ct(job))
    variable = _variable_suffix(job, wmax)
    stable = full[: len(full) - len(variable)].rstrip("\n")
    return stable, variable


# ── Gemini Context Cache ─────────────────────────────────────────────────────

def try_create_gemini_cache(
    client: genai.Client,
    model: str,
    system_prompt: str,
    stable_prefix: str,
    ttl: str = "900s",
) -> str | None:
    """Versucht, einen Gemini Context Cache für den stabilen Quellblock zu erstellen.

    Gibt den Cache-Namen zurück (z.B. 'cachedContents/abc123') oder None bei Fehler.
    Mindestens ~4 000 Tokens Inhalt nötig (je Modell); bei nicht unterstütztem Modell
    oder Fehler: graceful fallback (None → volle Message senden).

    ttl: Cache-Lebensdauer. Für synchrone Nutzung: "900s" (Standard).
    Für Batch-Modus: "3600s" wählen (Batch-Latenz kann >15 min sein).
    """
    try:
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                contents=[{"role": "user", "parts": [{"text": stable_prefix}]}],
                ttl=ttl,
            ),
        )
        log.info("  Gemini-Cache erstellt: %s (~%d Zeichen stable_prefix)",
                 cache.name, len(stable_prefix))
        return cache.name
    except Exception as e:
        log.info("  Gemini Context Cache nicht verfügbar (%s) — sende vollen Kontext", e)
        return None


# ── Phase-1-Orchestrierung: einmal pro Thema ─────────────────────────────────

def prepare_topic_sources(
    session: requests.Session,
    client: genai.Client,
    primary_wikipedia: str,
    thema: str,
    appeal: str,
    model: str,
    skip_images: bool,
    sensibel: bool = False,
    anthropic_api_key: str | None = None,
) -> tuple[str, list[str], dict[str, str], list[dict], dict]:
    """
    Phase 1 + Quellen-Fetch, einmalig pro Thema.
    Gibt (primary_text, valid_companions, companion_texts, images, phase1_report) zurück.
    """
    # Primärtext
    log.info("  Hole Primaertext: '%s'", primary_wikipedia)
    time.sleep(2.0)
    primary_text = fetch_wikipedia_text(session, primary_wikipedia)
    log.info("  Primaertext: %d Zeichen", len(primary_text))

    if len(primary_text) < 300:
        raise ValueError(f"Primaertext zu kurz: {len(primary_text)} Zeichen")

    # Kompass-Auswahl
    raw_companions, kompass_usage = select_companions_raw(client, thema, primary_text, model, appeal=appeal)
    if kompass_usage:
        cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                            schritt="kompass", modell=model, **kompass_usage)
    log.info("  Kompass-Vorschlag: %s", raw_companions)

    # Validierung + Weiterleitungsauflösung (cap gestaffelt nach Appeal)
    companion_cap = COMPANION_CAP.get(appeal, 5)
    valid_companions, rejected, companion_resolution = validate_and_resolve_companions(
        session, raw_companions, primary_wikipedia, cap=companion_cap
    )
    log.info("  Validiert (final): %s", valid_companions)

    phase1_report: dict = {
        "raw_companions":       raw_companions,
        "valid_companions":     valid_companions,
        "rejected":             rejected,
        "companion_resolution": companion_resolution,
    }

    # Companion-Volltexte holen
    companion_texts: dict[str, str] = {}
    for comp in valid_companions:
        try:
            time.sleep(0.5)
            ct = fetch_wikipedia_text(session, comp)
            companion_texts[comp] = ct
            log.info("  Companion-Text '%s': %d Zeichen", comp, len(ct))
        except Exception as e:
            log.warning("  Companion-Text '%s' Fehler: %s", comp, e)

    # Bildpool (optional)
    if skip_images:
        images: list[dict] = []
        log.info("  Bildpool: uebersprungen (--skip-images)")
    else:
        fetched_companions = [c for c in valid_companions if c in companion_texts]
        log.info("  Baue Bildpool (Primaer + %d Companions) ...", len(fetched_companions))
        images, img_report = build_image_pool(
            session, client, thema, primary_wikipedia, fetched_companions, appeal,
            sensibel=sensibel, anthropic_api_key=anthropic_api_key,
        )
        log.info("  Bildpool: %d akzeptiert, Hero=%s",
                 img_report["accepted"], img_report["hero"])
        phase1_report["images"] = img_report

    return primary_text, valid_companions, companion_texts, images, phase1_report


TRIM_SYSTEM_PROMPT = (
    "Du bist Lektor für ein deutsches Kinderlexikon. Du erhältst einen fertigen Artikel als JSON "
    "und eine Wort-Obergrenze. Kürze den Artikel auf höchstens diese Wortzahl. "
    "ERLAUBT: Sätze in sections[].sentences straffen oder einzelne Sätze entfernen; "
    "maximal EINEN ganzen Abschnitt entfernen (sections[]-Element), wenn unvermeidbar. "
    "VERBOTEN: Boxen (sections[].boxes) entfernen — alle Boxen bleiben vollständig erhalten. "
    "Bewahre Faktentreue, Tonfall, Stil, Sprachstufe und Quiz. Erfinde nichts hinzu. "
    "Gib AUSSCHLIESSLICH das gekürzte JSON nach demselben Schema zurück — kein Vortext."
)


# Normalisierte Usage des letzten Trim-/Box-Repair-Passes (cost_tracker-Schlüssel
# input_tok/output_tok/cached_tok/thoughts_tok + verwendetes Modell). Wird von beiden
# Provider-Pfaden gesetzt, damit run_batch die Kosten provider-unabhängig auslesen kann.
_last_trim_usage: dict = {}
_last_box_usage: dict = {}


def _loads_tolerant(s: str):
    """Parst ein als String serialisiertes JSON-Feld robust.

    1. Quote-Repair (deutscher „…"-ASCII-Schluss) + json.loads
    2. roher String (falls Repair etwas verschlimmbessert)
    3. raw_decode: erstes vollständiges Value, ignoriert Trailing-Müll
       (deckt seltene „Extra data"-Artefakte des Modells ab).
    """
    repaired = _repair_article_quotes(s)
    for cand in (repaired, s):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
    obj, _ = json.JSONDecoder().raw_decode(repaired.lstrip())
    return obj


def _destringify_article(d: dict) -> dict:
    """Repariert tool-use-Felder, die als JSON-STRING statt strukturiert ankommen.

    Anthropic (Batch UND teils Sync) serialisiert große, textlastige Felder
    (sections/source_passages/images/quiz/related_terms) gelegentlich als String.
    Diese tragen denselben „…"-ASCII-Schluss-Defekt → tolerantes Parsen.
    Felder, die bereits strukturiert sind, bleiben unangetastet.
    """
    for key in ("sections", "source_passages", "images", "quiz", "related_terms"):
        val = d.get(key)
        if isinstance(val, str):
            d[key] = _loads_tolerant(val)
    return d


def _trim_article_to_cap(article: dict, word_limit: int, model: str, thinking_config) -> tuple[dict, int]:
    """Kürzt einen zu langen Artikel per Modell-Lektorat auf ≤ word_limit. Rückgabe: (article, word_count).

    Provider aus stage_models["trim"]: gemini → call_gemini (unverändert);
    anthropic → call_claude_json (forced tool-use, dict direkt, kein parse_article_json).
    """
    global _last_trim_usage
    from stage_models import get_stage_config, ARTICLE_SCHEMA
    cfg        = get_stage_config("trim")
    provider   = cfg["provider"]
    trim_model = cfg["model"]

    trim_msg = (
        f"WORT-OBERGRENZE: {word_limit}\n"
        f"Der folgende Artikel hat zu viele Wörter. Kürze ihn auf höchstens {word_limit} Wörter.\n\n"
        f"ARTIKEL_JSON:\n{json.dumps(article, ensure_ascii=False)}"
    )

    if provider == "anthropic":
        import claude_client
        trimmed = claude_client.call_claude_json(
            system_prompt=TRIM_SYSTEM_PROMPT,
            user_message=trim_msg,
            json_schema=ARTICLE_SCHEMA,
            model=trim_model,
            max_tokens=32000,       # Trim echot den ganzen Artikel → großer Cap nötig
            thinking_budget=4096,   # → tool_choice=auto-Pfad
            call_name="trim",
            stream=True,            # großer max_tokens → Streaming-Pflicht (SDK)
        )
        trimmed = _destringify_article(trimmed)
        u = claude_client.get_last_usage()
        _last_trim_usage = {
            "input_tok":    u.get("input_tokens", 0),
            "output_tok":   u.get("output_tokens", 0),
            "cached_tok":   0,
            "thoughts_tok": 0,
            "model":        trim_model,
        }
    else:
        # Der Trim echot den GANZEN Artikel zurück → großes Output-Budget nötig,
        # sonst schneidet Gemini die Antwort ab (unbalanciertes JSON, s. Dino 1370 W).
        raw = gemini_client.call_gemini(
            TRIM_SYSTEM_PROMPT, trim_msg, model=model, thinking_config=thinking_config,
            response_mime_type="application/json", max_output_tokens=16384,
        )
        trimmed = parse_article_json(raw)
        u = getattr(gemini_client, "_last_usage", {}) or {}
        _last_trim_usage = {**u, "model": model}

    trimmed.setdefault("meta", {}).update(article.get("meta", {}))
    return trimmed, count_article_words(trimmed)


BOX_REPAIR_SYSTEM_PROMPT = (
    "Du bist Lektor für ein deutsches Kinderlexikon. Du erhältst einen fertigen Artikel als JSON, "
    "dessen Callout-Boxen schlecht verteilt sind. Ordne JEDE vorhandene Box dem inhaltlich passenden "
    "Abschnitt zu, sodass keine zwei Boxen am Stück am Ende stehen und bei zwei oder mehr Boxen "
    "mindestens eine im mittleren Drittel sitzt. Du änderst AUSSCHLIESSLICH die Box-Platzierung. "
    "Box-Inhalt (type/text/reveal_text), Abschnittsreihenfolge, Überschriften und ALLE Sätze bleiben "
    "wortgleich. Nichts hinzufügen, nichts löschen, nichts umformulieren. Gib NUR das JSON nach "
    "demselben Schema zurück — kein Vortext."
)


def _box_lint(article: dict) -> str | None:
    """Prüft Box-Verteilung deterministisch. Rückgabe: Verstoßgrund oder None (ok)."""
    secs = article.get("sections", [])
    counts = [len(s.get("boxes", []) or []) for s in secs]
    total, n = sum(counts), len(secs)
    if total < 2 or n < 2:
        return None
    if counts[-1] >= 2:
        return "Box-Clusterung: >=2 Boxen im letzten Abschnitt"
    if n >= 3:
        lo, hi = n // 3, (2 * n + 2) // 3
        if not any(counts[i] > 0 for i in range(lo, hi)):
            return "Box-Verteilung: keine Box im mittleren Drittel"
    return None


def _box_signature(article: dict):
    """Inhalts-Fingerabdruck (positionsunabhängig): Box-Multiset + Abschnittssätze."""
    boxes = sorted(
        (b.get("type", ""), (b.get("text", "") or "").strip(), (b.get("reveal_text", "") or "").strip())
        for s in article.get("sections", []) for b in (s.get("boxes", []) or [])
    )
    sentences = [
        (s.get("heading", ""),
         tuple((x.get("text", "") or "").strip() for x in (s.get("sentences", []) or [])))
        for s in article.get("sections", [])
    ]
    return boxes, sentences


def _box_repair_pass(article: dict, model: str, thinking_config) -> dict:
    """Modell ordnet vorhandene Boxen den passenden Abschnitten zu (Inhalt unverändert).

    Provider aus stage_models["box_repair"]: gemini → call_gemini (unverändert);
    anthropic → call_claude_json (forced tool-use, dict direkt).
    """
    global _last_box_usage
    from stage_models import get_stage_config, ARTICLE_SCHEMA
    cfg       = get_stage_config("box_repair")
    provider  = cfg["provider"]
    box_model = cfg["model"]

    msg = (
        "Die Callout-Boxen sind schlecht verteilt. Ordne sie den passenden Abschnitten zu — "
        "nur Platzierung, Inhalt/Sätze/Reihenfolge wortgleich.\n\n"
        f"ARTIKEL_JSON:\n{json.dumps(article, ensure_ascii=False)}"
    )

    if provider == "anthropic":
        import claude_client
        repaired = claude_client.call_claude_json(
            system_prompt=BOX_REPAIR_SYSTEM_PROMPT,
            user_message=msg,
            json_schema=ARTICLE_SCHEMA,
            model=box_model,
            max_tokens=32000,       # Box-Repair echot den ganzen Artikel → großer Cap nötig
            thinking_budget=4096,   # → tool_choice=auto-Pfad
            call_name="box_repair",
            stream=True,            # großer max_tokens → Streaming-Pflicht (SDK)
        )
        repaired = _destringify_article(repaired)
        u = claude_client.get_last_usage()
        _last_box_usage = {
            "input_tok":    u.get("input_tokens", 0),
            "output_tok":   u.get("output_tokens", 0),
            "cached_tok":   0,
            "thoughts_tok": 0,
            "model":        box_model,
        }
    else:
        raw = gemini_client.call_gemini(
            BOX_REPAIR_SYSTEM_PROMPT, msg, model=model, thinking_config=thinking_config,
            response_mime_type="application/json",
        )
        repaired = parse_article_json(raw)
        u = getattr(gemini_client, "_last_usage", {}) or {}
        _last_box_usage = {**u, "model": model}

    repaired.setdefault("meta", {}).update(article.get("meta", {}))
    return repaired


# ── Phase-2-Generierung: je Stufe ────────────────────────────────────────────

def _generate_erzaehltext_6pass(
    job: dict, primary_text: str, companion_texts: dict[str, str],
    valid_companions: list[str], images: list[dict], phase1_report: dict,
    model: str, skip_images: bool,
) -> tuple[dict | None, dict]:
    """Erzaehltext (10-12 J. = altes S3) ueber das 6-Schritt-System (pipeline_new)
    statt ueber den Einzel-Call.

    Der Stufen-Umbau (2026-07-19) hatte den Erzaehltext versehentlich auf den
    Einzel-Call gelegt, obwohl der Plan „S3 unveraendert" vorsah — die getrennten
    Arbeitsschritte (eigener Plan-, Prosa-, Box-, Bild-, Quiz-Pass) waren aber der
    Grund fuer die gute S3-Qualitaet. Hier wird der Text-Motor wiederhergestellt.
    NUR der Text-Motor: Naming ({slug}_erzaehltext), Meta-Felder, Bild-nach-Text
    und der geteilte Kompass bleiben. Das Hoerspiel ist NICHT betroffen (laeuft
    weiter durch generate_one_level). PO-Entscheidung 2026-07-23.

    pipeline_new.generate_article_new macht pass1-6 komplett (Plan, Prosa,
    Boxen inkl. Redundanz-Check, Belege, Bilder-nach-Text, Quiz). Wir legen nur
    die drei Meta-Felder nach, die pipeline_new nicht kennt, und die neuen Fixes,
    die es noch nicht hat (Sprach-Slip But->Aber, Querformat-Hero)."""
    import pipeline_new  # lazy: pipeline_new importiert aus generate_grounded (Zirkel)

    article_id = job["article_id"]
    thema      = job.get("thema", job.get("title", ""))
    appeal     = job.get("resolved_appeal", "medium")
    report: dict = {
        "article_id": article_id, "thema": thema,
        "primaer_wikipedia": job.get("primaer_wikipedia", thema),
        "phase1": phase1_report,
        "phase2": {"pipeline": "pass1-6 (6-Schritt-System, S3-Wiederherstellung)"},
        "errors": [],
    }
    log.info("  Phase 2: Erzaehltext ueber 6-Schritt-System (pipeline_new), Thema: %s", thema)

    # generate_article_new liest job["age_level"] als Stufe (erzaehltext -> 3).
    job2 = {**job, "age_level": job.get("prompt_age_level", 3)}
    try:
        article, pnrep = pipeline_new.generate_article_new(
            job2, primary_text, companion_texts, valid_companions,
            model=model, images=([] if skip_images else images), appeal=appeal,
        )
    except Exception as e:
        log.error("  6-Schritt-System fehlgeschlagen: %s", e)
        report["errors"] = [f"pipeline_new: {e}"]
        return None, report
    report["phase2"]["pipeline_new_report"] = pnrep
    if article is None:
        report["errors"] = pnrep.get("errors", ["pipeline_new: keine Ausgabe"])
        return None, report

    # Meta-Felder, die pipeline_new nicht setzt (Paritaet mit dem Einzel-Call —
    # App liest age_level, Review-Docx/historie lesen content_type).
    m = article.setdefault("meta", {})
    m["content_type"] = "erzaehltext"
    m["age_floor"]    = int(job.get("age_floor", job.get("_catalog_age_floor", 1)))
    m["image_stufe"]  = job.get("image_stufe", 3)

    # Neue Fixes, die pipeline_new noch nicht hat:
    n_slips = fix_language_slips(article)              # But->Aber u. a.
    if n_slips:
        log.info("  Sprach-Slip-Fix: %d Zeilen eingedeutscht", n_slips)
    if not skip_images and article.get("images"):
        hero_note = enforce_landscape_hero(article, images)   # Querformat-Hero
        if hero_note:
            log.info("  %s", hero_note)
            report["phase2"]["hero_fix"] = hero_note

    val_errors = validate_article(article, job, word_floor=pnrep.get("wmin"))
    if val_errors:
        for e in val_errors:
            log.warning("  Validierungsfehler: %s", e)
        m["review_flag"] = True
        m["review_reason"] = (m.get("review_reason", "") + "; "
                              + "; ".join(val_errors[:3])).lstrip("; ")
    report["phase2"]["validation_errors"]  = val_errors
    report["phase2"]["companions_fetched"] = list(companion_texts.keys())
    return article, report


# ── Hoerspiel: getrennter Story-Plan (SCHRITT 1) vor der Prosa (SCHRITT 2) ────
# Uebertraegt die Grundlehre des 6-Schritt-Systems (getrennte Arbeitsschritte)
# auf das Hoerspiel: Erst plant das Modell in einem eigenen Aufruf NUR den
# <planung>-Block (Rahmen, Fenster, Erzaehlfaden, Dialog-Rhythmus) — mit voller
# Aufmerksamkeit, ohne gleichzeitig Prosa+Quiz zu schreiben. Der fertige Plan
# geht dann als STORY_PLAN in den Schreib-Aufruf (SCHRITT 2).
#
# KEIN Qualitaets-Fallback (PO 2026-07-23): Faellt der Plan-Aufruf aus, wird das
# Hoerspiel NICHT im schwaecheren Einzel-Call erzeugt — der Job gilt als nicht
# generiert (generate_one_level gibt (None, report) zurueck) und der Nachtlauf
# laeuft ihn off-peak erneut an. Lieber ein spaeteres, gutes Hoerspiel (oder im
# Extremfall gar keines, klar geloggt) als ein stilles Downgrade. call_gemini
# wiederholt intern schon 5x mit Backoff, der Ausfall ist also ohnehin selten.
HOERSPIEL_PLAN_SPLIT = True
_PLANUNG_RE = re.compile(r"<planung>.*?</planung>", re.DOTALL | re.IGNORECASE)


def _hoerspiel_story_plan(
    system_prompt: str,
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    valid_companions: list[str],
    model: str,
) -> str | None:
    """Plan-only-Aufruf: gibt NUR den <planung>-Block zurueck (oder None bei Fehler).

    None bedeutet fuer den Aufrufer: Hoerspiel-Job schlaegt fehl (KEIN Einzel-Call-
    Fallback) → Nachtlauf laeuft ihn off-peak erneut an. Nutzt denselben Hoerspiel-
    System-Prompt wie der Schreib-Aufruf (keine Prompt-Duplikation) — nur die
    User-Message weist an, ausschliesslich SCHRITT 1 auszufuehren und nach
    </planung> zu stoppen. Bilder bleiben aussen vor (Plan braucht keinen Bildpool)."""
    try:
        base = build_grounded_user_message(
            job, primary_text, companion_texts, valid_companions, []
        )
    except Exception as e:
        log.warning("  Story-Plan: User-Message-Bau fehlgeschlagen (%s) — Job wird neu angelaufen", e)
        return None
    plan_msg = (
        base
        + "\n\n────────\n"
        "AUFGABE NUR FUER DIESEN AUFRUF: Fuehre ausschliesslich SCHRITT 1 aus "
        "(die Planung). Gib GENAU den vollstaendigen Block von <planung> bis "
        "</planung> aus und stoppe unmittelbar danach. Schreibe in diesem Aufruf "
        "KEIN Hoerspiel, KEINE sections, KEIN JSON — nur den <planung>-Block. "
        "Nimm dir fuer den Rahmen, die Fenster, den Erzaehlfaden und den "
        "Dialog-Rhythmus die volle Aufmerksamkeit; das Schreiben folgt spaeter."
    )
    try:
        thinking = _make_thinking_config(model, budget_for_2_5=8192)
        raw = gemini_client.call_gemini(
            system_prompt, plan_msg, model=model, thinking_config=thinking,
            response_mime_type="text/plain",
        )
    except Exception as e:
        log.warning("  Story-Plan-Aufruf fehlgeschlagen (%s) — Job wird off-peak neu angelaufen", e)
        return None
    if not raw or not raw.strip():
        log.warning("  Story-Plan leer — Job wird off-peak neu angelaufen")
        return None
    m = _PLANUNG_RE.search(raw)
    if m:
        plan = m.group(0).strip()
    else:
        # Kein Tag-Paar: nimm die Rohausgabe, wenn sie plausibel ein Plan ist
        # (enthaelt Plan-Marker), sonst Fallback.
        raw_s = raw.strip()
        if "FENSTER" in raw_s.upper() and "RAHMEN" in raw_s.upper():
            plan = raw_s if raw_s.lower().startswith("<planung>") else f"<planung>\n{raw_s}\n</planung>"
        else:
            log.warning("  Story-Plan ohne verwertbaren <planung>-Block — Job wird off-peak neu angelaufen")
            return None
    log.info("  Story-Plan erstellt (%d Zeichen) — SCHRITT 1 getrennt vorab", len(plan))
    return plan


def generate_one_level(
    client: genai.Client,
    system_prompt: str,
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    valid_companions: list[str],
    images: list[dict],
    phase1_report: dict,
    model: str,
    skip_images: bool,
    out_dir: Path,
    gemini_cache: str | None = None,
    sources_block: str = "",
    skip_lektorat: bool = False,
) -> tuple[dict | None, dict]:
    """Phase 2: Artikel für eine Stufe generieren (shared sources).

    gemini_cache: Cache-Name aus try_create_gemini_cache (optional).
    Wenn gesetzt: nur variabler Suffix (AGE_LEVEL + WORTZIEL) gesendet,
    stabiler Prefix aus Cache gelesen → ~75 % Token-Einsparung auf cached Tokens.
    """
    article_id       = job["article_id"]
    thema            = job.get("thema", job["title"])
    content_type     = _job_ct(job)

    # Erzaehltext (S3) laeuft ueber das alte 6-Schritt-System (bessere Prosa,
    # PO 2026-07-23). Nur Gemini-Generator; der Claude-A/B-Pfad bleibt beim
    # Einzel-Call. Hoerspiel ist NICHT betroffen.
    if content_type == "erzaehltext" and not model.lower().startswith("claude"):
        return _generate_erzaehltext_6pass(
            job, primary_text, companion_texts, valid_companions, images,
            phase1_report, model, skip_images)

    image_stufe      = job.get("image_stufe", job.get("prompt_age_level", 3))
    prompt_version   = PROMPT_PATHS.get(content_type, SYSTEM_PROMPT_PATH).stem.split("_v")[-1].split("_")[0]
    generation_method = f"{model}/medium/{content_type}-v{prompt_version}"

    # Bildauswahl nach jüngstem Zuschauer (Plan §4): nur Bilder mit ab_stufe <= image_stufe
    _appeal = job.get("resolved_appeal", "medium")
    images = select_images_for_stufe(images, image_stufe, _appeal,
                                     drop_svg=(content_type == "hoerspiel"))
    log.info("  Bildpool fuer %s (image_stufe<=%d): %d Bilder (appeal=%s)",
             content_type, image_stufe, len(images), _appeal)

    # Bildpool GEHT NICHT in die Generierung: Prosa und Bildzuweisung duerfen sich
    # nicht dieselbe Modellaufmerksamkeit teilen (assign_images_pass laeuft spaeter
    # auf dem fertigen Text). prompt_images bleibt leer, images bleibt der Pool.
    prompt_images: list[dict] = [] if DEFER_IMAGES else images
    max_inline = INLINE_TARGET.get(_appeal, 6)

    report: dict = {
        "article_id":        article_id,
        "thema":             thema,
        "primaer_wikipedia": job.get("primaer_wikipedia", thema),
        "phase1":            phase1_report,
        "phase2":            {"images": {"skipped": True} if skip_images else {}},
        "errors":            [],
    }

    log.info("  Phase 2: Artikel generieren (Thema: %s, Typ: %s, Modell: %s)",
             thema, content_type, model)

    phase2_thinking = _make_thinking_config(model, budget_for_2_5=8192)
    _GEN_MAX_ATTEMPTS = 4
    _GEN_RETRY_WAITS  = [30, 60, 120, 240]

    article     = None
    user_msg: str | None = None  # lazy für Wortzahl-Retry

    is_claude_gen = model.lower().startswith("claude")

    # Hoerspiel, neue Mechanik: SCHRITT 1 (Planung) in einem eigenen Aufruf
    # vorab — analog pass1 im 6-Schritt-System. Der fertige <planung>-Block
    # geht als STORY_PLAN in den Schreib-Aufruf. Nur Gemini (Claude-Pfad plant
    # weiter im selben Call). Faellt der Plan-Aufruf aus, KEIN Einzel-Call-
    # Fallback (PO 2026-07-23): der Job schlaegt fehl (return None) und der
    # Nachtlauf laeuft ihn off-peak erneut an — lieber spaeter gut als still
    # schwaecher.
    if (HOERSPIEL_PLAN_SPLIT and content_type == "hoerspiel"
            and not is_claude_gen and not job.get("story_plan")):
        plan = _hoerspiel_story_plan(
            system_prompt, job, primary_text, companion_texts, valid_companions, model
        )
        if plan:
            job["story_plan"] = plan
            report["phase2"]["story_plan_split"] = True
            report["phase2"]["story_plan_len"] = len(plan)
        else:
            msg = ("Story-Plan (SCHRITT 1) fehlgeschlagen — kein Fallback auf den "
                   "schwaecheren Einzel-Call (PO 2026-07-23). Hoerspiel gilt als "
                   "nicht erzeugt; der Nachtlauf laeuft es off-peak erneut an.")
            log.warning("  %s", msg)
            report["phase2"]["story_plan_split"] = False
            report["errors"].append(msg)
            return None, report

    for gen_attempt in range(1, _GEN_MAX_ATTEMPTS + 1):
        try:
            if is_claude_gen:
                # Claude als Generator (A/B-Test gegen Flash): kein Gemini-Context-Cache,
                # freier Text → parse_article_json (planung/Fences/„…"-Repair robust).
                import claude_client
                if user_msg is None:
                    user_msg = build_grounded_user_message(
                        job, primary_text, companion_texts, valid_companions, prompt_images
                    )
                    report["phase2"]["user_msg_len"] = len(user_msg)
                raw_response = claude_client.call_claude_text(
                    system_prompt, user_msg, model=model, max_tokens=32000,
                    thinking_budget=0, effort="low", call_name="article_gen",
                )
            elif gemini_cache:
                _, variable_suffix = _split_grounded_user_message(
                    job, primary_text, companion_texts, valid_companions, prompt_images
                )
                report["phase2"]["user_msg_len"] = len(variable_suffix)
                if gen_attempt == 1:
                    log.info("  Phase 2: Cache-Hit — sende nur variable Suffix (%d Zeichen)",
                             len(variable_suffix))
                raw_response = gemini_client.call_gemini(
                    system_prompt, variable_suffix, model=model, thinking_config=phase2_thinking,
                    response_mime_type="application/json", cached_content=gemini_cache,
                )
            else:
                if user_msg is None:
                    user_msg = build_grounded_user_message(
                        job, primary_text, companion_texts, valid_companions, prompt_images
                    )
                    report["phase2"]["user_msg_len"] = len(user_msg)
                raw_response = gemini_client.call_gemini(
                    system_prompt, user_msg, model=model, thinking_config=phase2_thinking,
                    response_mime_type="application/json",
                )

            # JSON-Parse
            try:
                article = parse_article_json(raw_response)
            except (json.JSONDecodeError, ValueError) as parse_err:
                errors_dir = out_dir / "_errors"
                errors_dir.mkdir(parents=True, exist_ok=True)
                (errors_dir / f"{article_id}_raw.txt").write_text(raw_response or "", encoding="utf-8")
                raise RuntimeError(f"JSON-Parse: {parse_err}") from parse_err

            # Plausibilitätsprüfung: Pflichtfelder, nicht 1-Token-Fragment
            n_secs  = len(article.get("sections", []))
            n_sents = sum(len(s.get("sentences", [])) for s in article.get("sections", []))
            if n_secs == 0 or n_sents < 3:
                raise RuntimeError(
                    f"Artikel nicht plausibel: {n_secs} Sections, {n_sents} Sätze"
                )

            if is_claude_gen:
                import claude_client
                _cu = claude_client.get_last_usage()
                _u = {"input_tok":  int(_cu.get("input_tokens", 0)),
                      "output_tok": int(_cu.get("output_tokens", 0))} if _cu else {}
            else:
                _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=content_type, schritt="article_gen",
                                    modell=model, **_u)
            break  # Erfolg

        except Exception as e:
            err_str = str(e)
            # Cache abgelaufen (TTL überschritten durch 503-Sturm) → Full-Context, kein Warten
            if gemini_cache and "CachedContent not found" in err_str:
                log.warning(
                    "  Phase 2 [%s]: Gemini-Cache abgelaufen/ungueltig — wechsle auf Full-Context",
                    article_id,
                )
                gemini_cache = None
                article = None
                continue
            if gen_attempt < _GEN_MAX_ATTEMPTS:
                wait = _GEN_RETRY_WAITS[gen_attempt - 1]
                log.warning(
                    "  Phase 2 [%s] Versuch %d/%d: %s — warte %ds",
                    article_id, gen_attempt, _GEN_MAX_ATTEMPTS, e, wait,
                )
                time.sleep(wait)
                article = None
            else:
                log.error(
                    "  Phase 2 [%s]: alle %d Versuche fehlgeschlagen: %s",
                    article_id, _GEN_MAX_ATTEMPTS, e,
                )
                report["errors"].append(
                    f"Phase 2 alle {_GEN_MAX_ATTEMPTS} Versuche fehlgeschlagen: {e}"
                )
                return None, report

    if article is None:
        # Alle Retries erschöpft (inkl. Cache-403-Sonderfall nach 503-Sturm,
        # der die for-Schleife per `continue` ohne Last-Attempt-Schutz verlässt)
        # → Stufe überspringen statt mit AttributeError den ganzen Batch killen
        log.error(
            "  Phase 2 [%s]: article is None nach Retry-Erschöpfung — Stufe übersprungen",
            article_id,
        )
        report["errors"].append(
            "Phase 2 alle Retries erschöpft (Cache-403/503) — Stufe übersprungen"
        )
        return None, report

    article.setdefault("meta", {})["id"]           = article_id
    article["meta"]["title"]                        = thema
    # Inhaltstyp-Felder in Code erzwingen (nicht dem Modell-Output vertrauen):
    article["meta"]["content_type"]                 = content_type
    article["meta"]["age_floor"]                     = int(job.get("age_floor", job.get("_catalog_age_floor", 1)))
    article["meta"]["image_stufe"]                   = image_stufe
    article["meta"]["age_level"]                     = job.get("prompt_age_level", 3)
    article["meta"]["generated_at"]                 = datetime.now(timezone.utc).isoformat()
    article["meta"]["grounding_companions"]          = valid_companions
    article["meta"]["generation_method"]             = generation_method
    _lemma_flags = job.get("lemma_flags", [])
    _review = [f for f in _lemma_flags if f.startswith(("BITTE PRUEFEN", "LEMMA_GEWECHSELT"))]
    if _review:
        article["meta"]["review_flag"]   = True
        article["meta"]["review_reason"] = "; ".join(_review)

    # ── Wortzahl-Check + ggf. Retry ──────────────────────────────────────────
    wmin, wmax, _wz_src = wortziel_for(thema, content_type)
    word_count = count_article_words(article)
    report["phase2"]["word_count"]  = word_count
    report["phase2"]["word_target"] = f"{wmin}–{wmax}"

    if word_count < wmin:
        log.warning("  Wortzahl zu kurz: %d Wörter (Ziel %d–%d) — Retry", word_count, wmin, wmax)
        if user_msg is None:
            user_msg = build_grounded_user_message(
                job, primary_text, companion_texts, valid_companions, prompt_images
            )
        retry_hint = (
            f"\n\nRETRY_FEEDBACK: Vorentwurf hatte {word_count} Wörter, Ziel {wmin}–{wmax}. "
            f"Entwickle die deklarierten Quellen voller — konkrete Fakten, Beispiele, "
            f"Mechanismen ausarbeiten. Harte Obergrenze {wmax} Wörter nicht überschreiten. "
            f"Kein Auffüllen ohne Quellbasis."
        )
        retry_msg = user_msg + retry_hint
        try:
            raw_retry = gemini_client.call_gemini(
                system_prompt, retry_msg, model=model, thinking_config=phase2_thinking,
                response_mime_type="application/json",
            )
            article_retry = parse_article_json(raw_retry)
            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=content_type, schritt="article_gen",
                                    modell=model, **_u)
            wc_retry = count_article_words(article_retry)
            report["phase2"]["retry_needed"]     = True
            report["phase2"]["retry_word_count"] = wc_retry
            log.info("  Retry Wortzahl: %d Wörter", wc_retry)
            # Metadaten auf Retry-Artikel übertragen
            article_retry.setdefault("meta", {})["id"]               = article_id
            article_retry["meta"]["title"]                            = thema
            article_retry["meta"]["content_type"]                     = content_type
            article_retry["meta"]["age_floor"]                        = article["meta"]["age_floor"]
            article_retry["meta"]["image_stufe"]                      = image_stufe
            article_retry["meta"]["age_level"]                        = job.get("prompt_age_level", 3)
            article_retry["meta"]["generated_at"]                     = article["meta"]["generated_at"]
            article_retry["meta"]["grounding_companions"]             = valid_companions
            article_retry["meta"]["generation_method"]                = generation_method
            article = article_retry
            word_count = wc_retry
            if word_count < wmin:
                log.warning("  Nach Retry immer noch zu kurz: %d Wörter → review_flag", word_count)
                article["meta"]["review_flag"]   = True
                article["meta"]["review_reason"] = f"Wortzahl nach Retry {word_count} < {wmin}"
        except Exception as e:
            log.error("  Retry fehlgeschlagen: %s", e)
            report["errors"].append(f"Retry fehlgeschlagen: {e}")
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = f"Retry fehlgeschlagen: {e}"
    else:
        report["phase2"]["retry_needed"] = False

    # ── Wortzahl-Guard: zu lang → Trim-Pass (harte Obergrenze) ───────────────
    cap = round(wmax * (1 + CAP_GRACE_FRAC))
    trims = 0
    while word_count > cap and trims < TRIM_MAX_ATTEMPTS:
        trims += 1
        log.warning("  Wortzahl zu lang: %d > Cap %d (Ziel %d) — Trim-Pass %d/%d",
                    word_count, cap, wmax, trims, TRIM_MAX_ATTEMPTS)
        try:
            article, word_count = _trim_article_to_cap(article, wmax, model, phase2_thinking)
            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=content_type, schritt="trim",
                                    modell=model, **_u)
            log.info("  Trim-Pass %d Ergebnis: %d Wörter", trims, word_count)
        except Exception as e:
            # z.B. abgeschnittenes JSON — nicht sofort aufgeben, sondern den
            # naechsten Trim-Versuch nutzen (continue statt break).
            log.error("  Trim-Pass %d fehlgeschlagen: %s — naechster Versuch", trims, e)
            report["errors"].append(f"Trim-Pass {trims} fehlgeschlagen: {e}")
            continue
    if trims:
        report["phase2"]["trim_passes"] = trims
        if word_count > cap:
            log.warning("  Nach %d Trim-Pass(es) weiter zu lang: %d > %d → review_flag",
                        trims, word_count, cap)
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = f"Wortzahl {word_count} > Cap {cap} nach Trim"

    report["phase2"]["word_count"] = word_count
    article["meta"]["word_count"]   = word_count
    article["meta"]["word_target"]  = f"{wmin}–{wmax}"
    article["meta"]["ergiebigkeit"] = ergiebigkeit_for(thema, content_type)

    # ── Box-Verteilungs-Guard: Clusterung → Auto-Reparatur, sonst review_flag ──
    box_issue = _box_lint(article)
    if box_issue:
        log.warning("  %s — Box-Reparatur-Pass", box_issue)
        try:
            repaired = _box_repair_pass(article, model, phase2_thinking)
            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=content_type, schritt="box_repair",
                                    modell=model, **_u)
            same_content = _box_signature(repaired) == _box_signature(article)
            if same_content and _box_lint(repaired) is None:
                article = repaired
                report["phase2"]["box_repaired"] = True
                log.info("  Box-Reparatur erfolgreich (Inhalt unverändert).")
            else:
                why = "Inhalt verändert" if not same_content else "Verteilung weiter verletzt"
                log.warning("  Box-Reparatur verworfen (%s) → review_flag", why)
                report["phase2"]["box_repaired"] = False
                article["meta"]["review_flag"]   = True
                article["meta"]["review_reason"] = (
                    article["meta"].get("review_reason", "") + f"; {box_issue}").lstrip("; ")
        except Exception as e:
            log.error("  Box-Reparatur fehlgeschlagen: %s", e)
            report["errors"].append(f"Box-Reparatur fehlgeschlagen: {e}")
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "") + f"; {box_issue}").lstrip("; ")

    # Hörspiel: getrennt abgelegte Rede + Redebegleitsatz wieder zusammenführen
    # (»„…!", / ruft Theo.« → EIN Eintrag), bevor validiert/lektoriert wird.
    # Englische Funktionswoerter (But/And …) deterministisch eindeutschen — beide
    # Inhaltstypen betroffen.
    n_slips = fix_language_slips(article)
    if n_slips:
        log.info("  Sprach-Slip-Fix: %d Zeilen eingedeutscht (But->Aber u. a.)", n_slips)

    if content_type == "hoerspiel":
        n_merged = _merge_split_speech_tags(article)
        if n_merged:
            log.info("  Redebegleitsatz-Merge: %d getrennte Rede-Zeilen zusammengefuehrt", n_merged)
        # Gegenrichtung: mehrere Reden in EINER Zeile wieder auftrennen (ein
        # Sprecher je Zeile). Das ist der echte Defekt, den der alte Satzzahl-
        # Waechter verfehlt hat (PO 2026-07-23).
        n_split = _split_double_speech_lines(article)
        if n_split:
            log.info("  Doppelrede-Split: %d Zeilen mit mehreren Reden aufgetrennt", n_split)
        # SCHRITT 7 – Kinder-Lektorat: ausgeschriebene Jahreszahlen/Tagesdaten
        # relativieren, Waffen-/Bomben-Vergleiche entschaerfen, zu viele Ziffern-
        # Jahre reduzieren (einzelne bleiben erlaubt, PO 2026-07-24).
        lekt_note = kinder_lektorat_pass(article, content_type, thema, model)
        if lekt_note:
            log.info("  %s", lekt_note)
            report["phase2"]["kinder_lektorat"] = lekt_note
        rest_issues = find_kinder_lektorat_issues(article)
        if rest_issues:
            for h in rest_issues:
                log.warning("  Kinder-Lektorat: harter Verstoss bleibt: %s", h)
            report["phase2"]["kinder_lektorat_rest"] = rest_issues
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "")
                + f"; {len(rest_issues)} Kinder-Lektorat-Verstoesse").lstrip("; ")

    # ── Bilder: eigener Aufruf auf dem FERTIGEN Text (Rueckkehr zu pass4_images) ──
    if DEFER_IMAGES and not skip_images:
        img_note = assign_images_pass(article, images, thema, model, max_inline)
        log.info("  %s", img_note)
        report["phase2"]["bildzuordnung"] = img_note
        if not any(im.get("placement") == "inline" and im.get("is_hero")
                   for im in article.get("images", [])):
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "") + "; kein Querformat-Hero").lstrip("; ")
        # Faellt der Zuordnungs-Aufruf aus (503), landet ALLES in der Galerie und der
        # Artikel haette kein einziges Bild im Text — das darf nicht still passieren.
        if not any(isinstance(s.get("img_index"), int) and s["img_index"] >= 0
                   for sec in article.get("sections", []) for s in sec.get("sentences", [])):
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "")
                + "; keine Bilder im Text (Zuordnung fehlgeschlagen)").lstrip("; ")
    else:
        # Alter Pfad (Bilder kamen aus der Generierung): Hero erzwingen, dann Galerie.
        hero_note = enforce_landscape_hero(article, images)
        if hero_note:
            log.info("  %s", hero_note)
            report["phase2"]["hero_fix"] = hero_note
            if hero_note.startswith("kein Querformat"):
                article["meta"]["review_flag"] = True
                article["meta"]["review_reason"] = (
                    article["meta"].get("review_reason", "") + "; Hero nicht im Querformat").lstrip("; ")
        gal_note = append_gallery_images(article, images)
        log.info("  %s", gal_note)
        report["phase2"]["galerie"] = gal_note

    # ── Erzaehler-Riegel: er darf sich nie selbst als Sprecher benennen ──
    erz_hits = find_erzaehler_labels(article)
    if erz_hits:
        for h in erz_hits:
            log.warning("  Erzaehler-Label im Text: %s", h)
        report["phase2"]["erzaehler_labels"] = erz_hits
        article["meta"]["review_flag"] = True
        article["meta"]["review_reason"] = (
            article["meta"].get("review_reason", "")
            + f"; {len(erz_hits)} Erzaehler-Label-Zeilen").lstrip("; ")

    # ── Doppelrede-Riegel: nach dem Auftrennen sollte keine Zeile mehr zwei Reden
    #    tragen. Bleibt doch eine uebrig, war der Fall zu verschachtelt → melden. ──
    if content_type == "hoerspiel":
        multi = find_multi_speech_lines(article)
        if multi:
            for h in multi:
                log.warning("  Zeile mit mehreren Reden (nicht auftrennbar): %s", h)
            report["phase2"]["multi_speech_lines"] = multi
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "")
                + f"; {len(multi)} Zeilen mit mehreren Reden").lstrip("; ")

    # ── Box-Redundanz: wiederholende Boxen NEU generieren (PO 2026-07-23: Boxen
    #    behalten, aber inhaltlich neu — nicht loeschen). Eigener Aufruf auf dem
    #    fertigen Text, analog assign_images_pass. ──
    redundant = find_redundant_boxes(article)
    if redundant:
        for h in redundant:
            log.info("  Box wiederholt den Text: %s", h)
        report["phase2"]["redundant_boxes"] = redundant
        box_note = regenerate_redundant_boxes(
            article, primary_text, companion_texts, thema, model)
        log.info("  %s", box_note)
        report["phase2"]["box_regen"] = box_note
        # Nur flaggen, wenn NACH der Neugenerierung noch etwas redundant ist
        # (oder der Aufruf scheiterte).
        rest = find_redundant_boxes(article)
        if rest or box_note.startswith("FEHLER"):
            article["meta"]["review_flag"] = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "")
                + f"; {len(rest)} Boxen weiterhin redundant").lstrip("; ")

    # ── SCHRITT 8 – Faktenlektorat (Gemini Flash) ────────────────────────────
    # Prüft Fakten UND Sprache gegen die Wikipedia-Quellen und baut die Korrekturen
    # sofort ein (Pruefbericht + ggf. review_flag). Ersetzt den früheren
    # nachgelagerten Sonnet-Batch samt separatem Sprachpass — Bakeoff 2026-07-25:
    # Flash ~10 % der Kosten bei gleicher/besserer Trefferquote (Eifel, Knochen).
    if not skip_lektorat and sources_block:
        lekt_result, lekt_usage = run_fact_lektorat_flash(
            article, sources_block, thema=thema, content_type=content_type,
            model=FACT_LEKTORAT_MODEL)
        annotate_article_lektorat_v2(article, lekt_result, thema=thema, stufe=content_type)
        pb = article.get("pruefbericht", {})
        log.info("  Faktenlektorat [Schritt 8, %s]: silent=%d korrigiert=%d pruefen=%d%s",
                 FACT_LEKTORAT_MODEL, pb.get("n_silent", 0), pb.get("n_korrigiert", 0),
                 pb.get("n_pruefen", 0),
                 " ⚠ review_flag" if pb.get("n_pruefen", 0) > 0 else "")
        report["phase2"]["faktenlektorat"] = {
            "modell":       FACT_LEKTORAT_MODEL,
            "n_silent":     pb.get("n_silent", 0),
            "n_korrigiert": pb.get("n_korrigiert", 0),
            "n_pruefen":    pb.get("n_pruefen", 0),
        }
        if lekt_usage:
            cost_tracker.track(
                run_id=_RUN_ID, thema=thema, stufe=content_type, schritt="lektorat",
                modell=FACT_LEKTORAT_MODEL,
                input_tok=lekt_usage.get("input_tok", 0),
                output_tok=lekt_usage.get("output_tok", 0) + lekt_usage.get("thoughts_tok", 0),
                cached_tok=lekt_usage.get("cached_tok", 0))

    val_errors = validate_article(article, job, word_floor=wmin)
    if val_errors:
        for e in val_errors:
            log.warning("  Validierungsfehler: %s", e)
        article["meta"]["review_flag"] = True
        existing_reason = article["meta"].get("review_reason", "")
        extra = "; ".join(val_errors[:3])
        article["meta"]["review_reason"] = (existing_reason + "; " + extra).lstrip("; ")

    report["phase2"]["validation_errors"]  = val_errors
    report["phase2"]["companions_fetched"] = list(companion_texts.keys())

    return article, report


# ── Catalog-Connector ─────────────────────────────────────────────────────────

def _build_catalog_jobs(themen: list[str], typen: list[str]) -> list[dict]:
    """Baut Job-Dicts aus catalog_full.json für die gegebenen Themen + Inhaltstypen.

    Je Thema ein Job pro Inhaltstyp (hoerspiel/erzaehltext). age_floor wird NICHT
    mehr zur Generierungszeit als Stufen-Skip genutzt (Plan §3: age_floor →
    Anbietezeit); der einzige generierungszeitliche Filter (Hörspiel-Drop bei
    age_floor 3, image_stufe) läuft autoritativ im Haupt-Loop über eignung_for."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog_full.json nicht gefunden: {CATALOG_PATH}")
    catalog: list[dict] = json.load(CATALOG_PATH.open(encoding="utf-8"))
    by_thema = {e["thema"].strip().lower(): e for e in catalog}

    jobs: list[dict] = []
    for thema in themen:
        entry = by_thema.get(thema.strip().lower())
        if entry is None:
            log.warning("  Catalog: Thema '%s' nicht gefunden — uebersprungen", thema)
            continue
        if entry.get("eignung") == "exclude" or thema.strip().lower() in _EXCLUDE_SET:
            log.info("  Catalog: '%s' ist exclude — uebersprungen", thema)
            continue
        canonical = entry["thema"]
        slug = canonical.lower().replace(" ", "_").replace("/", "_")
        for content_type in typen:
            jobs.append({
                "article_id":        f"{slug}_{content_type}",
                "thema":             canonical,
                "primaer_wikipedia": canonical,
                "title":             canonical,
                "content_type":      content_type,
                "prompt_age_level":  _PROMPT_AGE_LEVEL[content_type],
                "topic_interest":    "medium",
                "sensibel":          bool(entry.get("sensibel", False)),
                "pattern":           entry.get("themengebiet", ""),
                "category_top":      "",
                "category_sub":      "",
                "_catalog_rank":     entry.get("production_rank", 9999),
                "_catalog_age_floor": int(entry.get("age_floor") or 1),
            })
    return jobs


def _load_catalog_rank_jobs(top_n: int, typen: list[str]) -> list[dict]:
    """Lädt Top-N Themen nach production_rank aus catalog_full.json."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog_full.json nicht gefunden: {CATALOG_PATH}")
    catalog: list[dict] = json.load(CATALOG_PATH.open(encoding="utf-8"))
    eligible = [
        e for e in catalog
        if e.get("eignung") != "exclude" and e.get("production_rank") is not None
    ]
    eligible.sort(key=lambda e: int(e.get("production_rank") or 9999))
    top_themen = [e["thema"] for e in eligible[:top_n]]
    return _build_catalog_jobs(top_themen, typen)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Kompass-Grounding Artikel-Generator")
    parser.add_argument(
        "--articles", nargs="+",
        default=None,
        help="Artikel-IDs aus TEST_JOBS (default: alle Test-Jobs, wenn kein --catalog)",
    )
    parser.add_argument(
        "--catalog", nargs="+", metavar="THEMA",
        help="Themen aus catalog_full.json (z.B. --catalog Vulkan Biene)",
    )
    parser.add_argument(
        "--catalog-rank", type=int, default=None, metavar="N",
        help="Top-N Themen nach production_rank aus catalog_full.json",
    )
    parser.add_argument(
        "--typen", nargs="+", choices=list(CONTENT_TYPES), default=list(CONTENT_TYPES),
        help="Zu generierende Inhaltstypen (default: hoerspiel erzaehltext)",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run-ID fuer cost_tracker (default: Zeitstempel)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Zeigt Jobs + Eignungs-Gate, generiert nichts",
    )
    parser.add_argument(
        "--gen-model", default=None,
        help="Gemini-Modell (z.B. gemini-2.5-flash, gemini-3.5-flash)",
    )
    parser.add_argument(
        "--skip-images", action="store_true",
        help="Bildpipeline komplett ueberspringen",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Ausgabeverzeichnis (default: articles/test_grounded)",
    )
    parser.add_argument(
        "--hoerspiel-prompt", default=None, metavar="PFAD",
        help="Alternativer Hörspiel-System-Prompt (Bake-off A/B). Überschreibt "
             "PROMPT_PATHS['hoerspiel'] für diesen Lauf.",
    )
    parser.add_argument(
        "--skip-lektorat", action="store_true",
        help="Faktenlektorat (Schritt 8, Gemini Flash) ueberspringen",
    )
    args = parser.parse_args()

    # Bake-off: alternativen Hörspiel-Prompt für diesen Lauf einhängen (A/B).
    if args.hoerspiel_prompt:
        alt = Path(args.hoerspiel_prompt).resolve()
        if not alt.exists():
            log.error("Hörspiel-Prompt nicht gefunden: %s", alt)
            sys.exit(1)
        PROMPT_PATHS["hoerspiel"] = alt
        _PROMPT_CACHE.pop(str(alt), None)
        log.info("Bake-off: Hörspiel-Prompt = %s", alt.name)

    global _RUN_ID
    _RUN_ID = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    model         = args.gen_model or GEMINI_MODEL
    out_dir       = Path(args.output_dir).resolve() if args.output_dir else OUT_DIR
    model_slug    = model.replace("gemini-", "").replace(".", "-")
    skip_lektorat = args.skip_lektorat

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    # Faktenlektorat (Schritt 8) läuft über Gemini Flash — kein ANTHROPIC_API_KEY
    # mehr nötig. Der Key bleibt nur für den optionalen Claude-GENERATOR relevant.
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    log.info("System-Prompts: Erzähltext %d Z. | Hörspiel %d Z.",
             len(system_prompt_for("erzaehltext")), len(system_prompt_for("hoerspiel")))
    log.info("Modell: %s | skip_images: %s | out_dir: %s | run_id: %s",
             model, args.skip_images, out_dir, _RUN_ID)

    client = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_errors").mkdir(exist_ok=True)

    # Jobs sammeln
    resolved_jobs: list[dict] = []
    if args.catalog_rank:
        try:
            resolved_jobs = _load_catalog_rank_jobs(args.catalog_rank, args.typen)
            log.info("Catalog-Rank: Top-%d Themen, %d Jobs", args.catalog_rank, len(resolved_jobs))
        except Exception as e:
            log.error("Catalog-Rank Fehler: %s", e)
            sys.exit(1)
    elif args.catalog:
        try:
            resolved_jobs = _build_catalog_jobs(args.catalog, args.typen)
            log.info("Catalog: %d Themen, %d Jobs", len(args.catalog), len(resolved_jobs))
        except Exception as e:
            log.error("Catalog Fehler: %s", e)
            sys.exit(1)
    else:
        article_ids = args.articles if args.articles else list(TEST_JOBS.keys())
        for article_id in article_ids:
            job = TEST_JOBS.get(article_id)
            if not job:
                log.error("Unbekannte article_id: %s (verfuegbar: %s)",
                          article_id, list(TEST_JOBS.keys()))
                continue
            resolved_jobs.append({**job, "article_id": article_id})

    if args.dry_run:
        print(f"\n=== DRY-RUN: {len(resolved_jobs)} Jobs ===")
        n_drop = 0
        for job in resolved_jobs:
            ev = eignung_for(job.get("thema", job["title"]))
            floor = int(ev["age_floor"])
            ct = _job_ct(job)
            if ev["eignung"] == "exclude":
                verdikt = "EXCLUDE"
            elif ct == "hoerspiel" and floor >= 3:
                verdikt = "DROP (age_floor 3 → kein Hörspiel)"
                n_drop += 1
            else:
                verdikt = f"OK  image_stufe={image_stufe_for(ct, floor)}"
            sens = " sensibel" if job.get("sensibel") else ""
            print(f"  {job['article_id']:32s}  age_floor={floor}  {verdikt}{sens}")
        print(f"Kein einziger API-Call — dry-run beendet. ({n_drop} Hörspiel-Drop wg. age_floor 3)")
        return

    # Nach primaer_wikipedia gruppieren (Reihenfolge des ersten Auftretens bewahren)
    topic_groups: dict[str, list[dict]] = defaultdict(list)
    seen_topics: list[str] = []
    for job in resolved_jobs:
        primaer = job.get("primaer_wikipedia", job["title"])
        if primaer not in topic_groups:
            seen_topics.append(primaer)
        topic_groups[primaer].append(job)

    # ── Pro Thema: Phase 1 einmal, Phase 2 je Inhaltstyp ─────────────────────
    for primary_wikipedia in seen_topics:
        topic_jobs = topic_groups[primary_wikipedia]
        thema      = topic_jobs[0].get("thema", topic_jobs[0]["title"])

        # ── Eignungs-Gate: exclude / age_floor / framing ─────────────────────
        # age_floor steuert jetzt Anbietezeit + Bild-/Typ-Auswahl (Plan §3/§4),
        # NICHT mehr einen Stufen-Skip. Autoritative Quelle = eignung_for.
        ev = eignung_for(thema)
        if ev["eignung"] == "exclude":
            log.warning("  Eignungs-Gate: '%s' ausgeschlossen (%s) — übersprungen", thema, ev["source"])
            continue
        floor = int(ev["age_floor"])
        kept: list[dict] = []
        for job in topic_jobs:
            ct = _job_ct(job)
            # Hörspiel (4–9) entfällt nur bei age_floor 3 → ausschließlich Erzähltext.
            if ct == "hoerspiel" and floor >= 3:
                log.info("  age_floor=%d: '%s' bekommt kein Hörspiel (nur Erzähltext)", floor, thema)
                continue
            job["content_type"]     = ct
            job.setdefault("prompt_age_level", _PROMPT_AGE_LEVEL[ct])
            job["age_level"]         = job["prompt_age_level"]  # Back-compat: validate_article/Legacy lesen age_level
            job["age_floor"]         = floor
            job["image_stufe"]       = image_stufe_for(ct, floor)
            job["framing_note"]      = ev["framing_note"]
            kept.append(job)
        topic_jobs = kept
        if not topic_jobs:
            log.warning("  Eignungs-Gate: '%s' — kein Inhaltstyp übrig, nichts zu tun", thema)
            continue
        types = [_job_ct(j) for j in topic_jobs]

        # ── Lemma auflösen (Redirect / BKS / Listen / Doppelbedeutung) ───────
        try:
            lr = resolve_lemma(session, thema)
        except Exception as e:
            log.warning("  resolve_lemma('%s') Fehler: %s — nutze primaer_wikipedia direkt",
                        thema, e)
            lr = {"resolved_title": None, "flags": [], "doppelbedeutung_directive": None}
        resolved_title = lr.get("resolved_title")
        lemma_flags    = lr.get("flags", [])
        dd_directive   = lr.get("doppelbedeutung_directive")
        if resolved_title:
            if resolved_title != primary_wikipedia:
                log.info("  Lemma aufgelöst: '%s' → '%s'", primary_wikipedia, resolved_title)
            primary_wikipedia = resolved_title
        else:
            log.warning("  Lemma '%s' nicht auflösbar (%s) — nutze '%s' direkt",
                        thema, lemma_flags, primary_wikipedia)
        if lemma_flags:
            log.info("  Lemma-Flags: %s", lemma_flags)
        if dd_directive:
            log.info("  Doppelbedeutung (diagnostisch, nicht injiziert): %s",
                     dd_directive.get("directive", ""))
        for job in topic_jobs:
            job["primaer_wikipedia"]         = primary_wikipedia
            job["lemma_flags"]               = lemma_flags
            job["doppelbedeutung_directive"] = (dd_directive or {}).get("directive", "")

        # Appeal-Tier (Companion-/Bildmenge) aus Ergiebigkeit
        appeal, appeal_source = appeal_for(thema, topic_jobs[0].get("topic_interest"))
        for job in topic_jobs:
            job["resolved_appeal"] = appeal
            job["appeal_source"]   = appeal_source

        sensibel = bool(topic_jobs[0].get("sensibel", False))

        print(f"\n{'='*60}")
        print(f"THEMA: {thema} | Primaer: {primary_wikipedia} | Modell: {model}")
        print(f"Typen: {types} | Appeal: {appeal} (Herkunft: {appeal_source}) | sensibel: {sensibel}")
        print(f"Phase 1 laeuft EINMAL fuer alle Typen")
        print(f"{'='*60}")

        try:
            primary_text, valid_companions, companion_texts, images, phase1_report = (
                prepare_topic_sources(
                    session, client, primary_wikipedia, thema, appeal,
                    model, args.skip_images,
                    sensibel=sensibel, anthropic_api_key=anthropic_key,
                )
            )
        except Exception as e:
            log.error("  Topic-Setup fehlgeschlagen: %s", e)
            continue

        # Robustheit: Phase-1-Fehlschlag → LAUT abbrechen, KEIN Primär-only-Fallback
        if not valid_companions:
            log.error(
                "  ABBRUCH: Phase 1 lieferte keine validierten Companions fuer '%s' "
                "(503-Sturm oder kein Ergebnis). Kein Primaer-only-Fallback. "
                "Alle %d Stufe(n) uebersprungen.",
                thema, len(topic_jobs),
            )
            print(f"\n  *** FEHLER: Keine Companions fuer '{thema}' — Artikel NICHT generiert ***")
            for job in topic_jobs:
                err_report = {
                    "article_id": job["article_id"],
                    "thema": thema,
                    "status": "FAILED_NO_COMPANIONS",
                    "reason": "Phase 1 lieferte keine validierten Companions. Kein Primaer-only-Fallback.",
                    "phase1": phase1_report,
                    "errors": ["Phase 1: keine Companions nach allen Versuchen"],
                }
                report_path = out_dir / f"{job['article_id']}_report.json"
                report_path.write_text(
                    json.dumps(err_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                err_path = out_dir / "_errors" / f"{job['article_id']}_FAILED.json"
                err_path.write_text(
                    json.dumps(err_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log.error("  FAILED: %s", job["article_id"])
            continue

        # Kompass-Schreibplan (Phase 1) an alle Jobs des Topics haengen → wird in
        # der Generierung als verbindliche Fenster-Vorgabe injiziert (build_grounded_user_message).
        kompass_plan = get_last_kompass_plan()
        for job in topic_jobs:
            job["kompass_plan"] = kompass_plan

        # Befund Phase 1 ausgeben
        print(f"\n  [PHASE 1 — einmalig fuer '{thema}']")
        print(f"  Kompass-Vorschlag (roh): {phase1_report['raw_companions']}")
        for r in phase1_report["rejected"]:
            resolved_hint = f" (aufgeloest: '{r['resolved']}')" if r.get("resolved") else ""
            print(f"  Verworfen: '{r['title']}'{resolved_hint} — {r['reason']}")
        print(f"  Validiert + aufgeloest:  {valid_companions}")
        print(f"  [Quellblock wird fuer {len(topic_jobs)} Stufe(n) geteilt + gecacht]")

        # Quellblock einmal pro Thema bauen (geteilt über alle Stufen)
        sources_block = build_grounded_sources_block(
            primary_wikipedia, primary_text, valid_companions, companion_texts
        )
        log.info("  Quellblock: %d Zeichen (Primaer + %d Companions)",
                 len(sources_block), len(valid_companions))

        # Gemini Context Cache: stabilen Prefix (Quellblock) je Thema cachen.
        # Der Prefix (Quellen + Bildpool) ist typ-unabhängig; der System-Prompt NICHT
        # (Hörspiel ≠ Erzähltext) → ein Cache PRO Inhaltstyp aus demselben Prefix.
        stable_prefix: str | None = None
        if topic_jobs:
            stable_prefix, _ = _split_grounded_user_message(
                topic_jobs[0], primary_text, companion_texts, valid_companions, images
            )
        type_caches: dict[str, str | None] = {}

        # Phase 2: Typen SEQUENZIELL generieren (verhindert 503-Burst beim parallelen Feuern)
        topic_articles: list[tuple[dict, dict, dict]] = []  # (job, article, report)
        failed_levels: list[str] = []

        try:
            print(f"\n  Phase 2 startet {len(topic_jobs)} Typ(en) sequenziell ...")
            for job in sorted(topic_jobs, key=lambda j: CONTENT_TYPES.index(_job_ct(j))):
                article_id = job["article_id"]
                ct         = _job_ct(job)
                sp         = system_prompt_for(ct)
                print(f"\n  --- {ct}: {article_id} ---")

                # Gemini-Context-Cache nur für Gemini-Generatoren (bei Claude-Generator
                # sinnlos/fehlerhaft — Claude nutzt eigenes Prompt-Caching, hier ungenutzt).
                if (stable_prefix is not None and ct not in type_caches
                        and not model.lower().startswith("claude")):
                    type_caches[ct] = try_create_gemini_cache(client, model, sp, stable_prefix)

                article, report = generate_one_level(
                    client, sp, job,
                    primary_text, companion_texts, valid_companions, images,
                    phase1_report, model, args.skip_images, out_dir,
                    gemini_cache=type_caches.get(ct),
                    sources_block=sources_block,
                    skip_lektorat=skip_lektorat,
                )

                report_path = out_dir / f"{article_id}_report.json"
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"  Report: {report_path.relative_to(ROOT)}")
                if article:
                    topic_articles.append((job, article, report))
                else:
                    failed_levels.append(article_id)
                    print(f"  FEHLGESCHLAGEN: {report.get('errors')}")

            # Faktenlektorat läuft jetzt inline PRO Artikel als Schritt 8 in
            # generate_one_level (Gemini Flash, Fakten + Sprache). Kein nachgelagerter
            # Sonnet-Batch mehr — die Artikel tragen ihr lektorat-Feld/Pruefbericht
            # bereits, wenn wir hier ankommen.

            # Artikel schreiben (mit ggf. annotiertem lektorat-Feld)
            for job, article, report in topic_articles:
                article_id = job["article_id"]
                out_path = out_dir / f"{article_id}.json"
                out_path.write_text(
                    json.dumps(article, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                meta_title = article.get("meta", {}).get("title", "?")
                n_imgs  = len(article.get("images", []))
                n_sents = sum(
                    len(s.get("sentences", []))
                    for s in article.get("sections", [])
                )
                wc      = report["phase2"].get("word_count", "?")
                wtarget = report["phase2"].get("word_target", "?")
                retry   = " [RETRY]" if report["phase2"].get("retry_needed") else ""
                review  = " [REVIEW]" if article["meta"].get("review_flag") else ""
                pb      = article.get("pruefbericht", {})
                findings_list = pb.get("findings", [])
                n_f   = len(findings_list)
                n_s   = sum(1 for f in findings_list if f.get("verdikt") == "SILENT")
                n_k   = sum(1 for f in findings_list if f.get("verdikt") == "KORRIGIERT")
                n_p   = sum(1 for f in findings_list if f.get("verdikt") == "PRÜFEN")
                n_e   = sum(1 for f in findings_list if f.get("verdikt") == "EINBAU_FEHLGESCHLAGEN")
                lekt_note = (
                    f" [LEKTORAT {n_f}:{n_s}S/{n_k}K/{n_p}P/{n_e}E]"
                    if n_f else ""
                )
                gen_m   = article["meta"].get("generation_method", "?")
                print(f"  Gespeichert: {out_path.relative_to(ROOT)}")
                print(f"  meta.title='{meta_title}' | method='{gen_m}'")
                print(f"  Bilder: {n_imgs} | Saetze: {n_sents} | Woerter: {wc} (Ziel {wtarget}){retry}{review}{lekt_note}")

            if failed_levels:
                log.warning(
                    "  FEHLGESCHLAGEN (%d/%d Stufen): %s",
                    len(failed_levels), len(topic_jobs), ", ".join(failed_levels),
                )

        finally:
            for _ct, _cache in type_caches.items():
                if _cache:
                    try:
                        client.caches.delete(name=_cache)
                        log.info("  Gemini-Cache geloescht (%s): %s", _ct, _cache)
                    except Exception as e:
                        log.warning("  Gemini-Cache loeschen fehlgeschlagen (%s/%s): %s", _ct, _cache, e)

        print(f"\n  Appeal: {appeal} ({appeal_source}) | Companions ({len(valid_companions)}): {valid_companions}")


if __name__ == "__main__":
    main()
