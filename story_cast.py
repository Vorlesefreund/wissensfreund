#!/usr/bin/env python3
"""story_cast.py — EINE Wahrheitsquelle für den Hörspiel-/Story-Serien-Cast.

Fester, wiederkehrender Cast (Wiedererkennungswert über Folgen). Jede Figur hat
eine feste Gemini-Prebuilt-Stimme + einen Stil-Vorspann (Tempo/Tonfall sind bei
Gemini-TTS mindestens so wichtig wie die Stimme selbst — s. Hörproben-Runden
2026-07-19). Diese Tabelle ist die FINALE PO-Abnahme; sie weicht bewusst von der
älteren `tts_samples.py` ab (dort z. B. Rudi=Fenrir, Nele=Kore — hier FINAL).

Nutzung (in tts_story.py):
    import story_cast
    fig = story_cast.lookup("Ronja")      # -> Figur | None
    fig.voice, fig.style, fig.is_child
    voice = story_cast.guest_voice("ein Fischer")   # deterministische Gast-Stimme

Matching ist tolerant: „Dr. Samir"/„Samir", „Oma Rosa"/„Oma"/„Rosa", „Professor"/
„Erzähler" treffen dieselbe Figur. Unbekannte Namen (von Flash erfundene Gäste)
bekommen KEINE Cast-Stimme, sondern deterministisch eine Stimme aus dem Gast-Pool
+ ein hörbares Merkmal (Guest-Regel: Gäste klingen nie wie der feste Cast).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib


@dataclass(frozen=True)
class Figur:
    key: str                 # kanonischer Schlüssel (kleingeschrieben)
    display: str             # Anzeigename
    voice: str               # Gemini-Prebuilt-Stimme (FINAL)
    style: str               # Stil-Vorspann für die TTS (Tonfall/Tempo/Eigenart)
    gender: str              # "m" | "w"
    is_child: bool = False
    is_narrator: bool = False
    aliases: tuple[str, ...] = field(default=())


# ── FINALE Stimmen — PO-Abnahme 2026-07-19 („alle Stimmen passen jetzt") ────────
# Stil-Vorspänne aus der Eigenart je Figur + den FINAL-Notizen (z. B. Ronja
# „zügiger, lebendig, nicht mystisch"; Oma Rosa Erwachsenen-Vorlese-Stil, NICHT
# säuselnd; Opa Karl tief/gutmütig-alt; Tom cool/lässig).
_CAST: list[Figur] = [
    Figur("professor", "Professor (Erzähler)", "Iapetus",
          "Lies ruhig und warm vor, wie ein guter Vorlese-Erzähler. Natürlich und "
          "unaufgeregt, ein leises Lächeln in der Stimme.",
          "m", is_narrator=True, aliases=("erzähler", "erzaehler", "narrator")),

    Figur("mia", "Mia", "Leda",
          "Sprich als neugieriges Mädchen (etwa 7): lebendig und interessiert, "
          "staunst leicht, aber nicht überdreht.",
          "w", is_child=True),
    Figur("theo", "Theo", "Puck",
          "Sprich als neugieriger Junge (etwa 7): lebendig und interessiert, "
          "willst alles wissen, aber nicht überdreht.",
          "m", is_child=True),

    Figur("oma rosa", "Oma Rosa", "Vindemiatrix",
          "Sprich warm und erzählend wie eine gute Vorlese-Großmutter, erwachsen "
          "und natürlich — NICHT gesäuselt oder kindlich. Erzählst gern von früher.",
          "w", aliases=("oma", "rosa", "großmutter", "grossmutter")),
    Figur("opa karl", "Opa Karl", "Enceladus",
          "Sprich tief, gutmütig und geduldig wie ein alter Großvater. Ruhig, "
          "freundlich, nimmst dir Zeit.",
          "m", aliases=("opa", "karl", "großvater", "grossvater")),

    Figur("nadia", "Tierpflegerin Nadia", "Autonoe",
          "Sprich freundlich und zugewandt wie eine Tierpflegerin, die jedes Tier "
          "beim Namen kennt; bei scheuen Tieren leiser.",
          "w", aliases=("tierpflegerin", "pflegerin")),
    Figur("nele", "Museums-Forscherin Nele", "Pulcherrima",
          "Sprich klar und präzise wie eine begeisterte Forscherin, die gern "
          "Dinge erklärt.",
          "w", aliases=("forscherin", "museums-forscherin")),
    Figur("rudi", "Werkstatt-Erfinder Rudi", "Algieba",
          "Sprich lebendig und tüftelnd wie ein Erfinder in seiner Werkstatt, der "
          "gern etwas ausprobiert — neugierig und anpackend.",
          "m", aliases=("erfinder",)),
    Figur("hanna", "Naturführerin Hanna", "Aoede",
          "Sprich leise und aufmerksam wie eine Naturführerin, die auf Geräusche "
          "in der Natur lauscht.",
          "w", aliases=("naturführerin", "naturfuehrerin")),
    Figur("ronja", "Meeresbiologin Ronja", "Despina",
          "Sprich lebendig und etwas zügig wie eine begeisterte Meeresbiologin — "
          "warm und wach, NICHT langsam oder mystisch.",
          "w", aliases=("meeresbiologin",)),
    Figur("aris", "Astronom Aris", "Charon",
          "Sprich staunend und weit wie ein Astronom, der in die Ferne des Alls "
          "blickt — ruhig, voller Ehrfurcht vor der Größe.",
          "m", aliases=("astronom",)),

    Figur("samir", "Dr. Samir", "Sadaltager",
          "Sprich behutsam und beruhigend wie ein freundlicher Arzt, der dem Kind "
          "den Körper erklärt.",
          "m", aliases=("dr. samir", "dr samir", "doktor samir", "arzt")),
    Figur("clara", "Lehrerin Clara", "Erinome",
          "Sprich klar und ermutigend wie eine gute Lehrerin, die Abstraktes "
          "greifbar macht.",
          "w", aliases=("lehrerin",)),
    Figur("wilhelm", "Chronist Wilhelm", "Algenib",
          "Sprich in mittlerem Tempo, erzählend wie ein Chronist, der von "
          "berühmten Menschen und alten Zeiten berichtet.",
          "m", aliases=("chronist",)),
    Figur("tom", "Weltenbummler Tom", "Zubenelgenubi",
          "Sprich cool und lässig wie ein weitgereister Weltenbummler — locker "
          "und freundlich, NICHT aufgedreht.",
          "m", aliases=("weltenbummler",)),
    Figur("toni", "Nachbar Toni", "Achird",
          "Sprich freundlich und alltagsnah wie ein kluger Nachbar, der gern "
          "weiterhilft.",
          "m", aliases=("nachbar",)),
]

NARRATOR_KEY = "professor"

# Index: kanonischer Schlüssel + alle Aliasse → Figur (alles kleingeschrieben).
_INDEX: dict[str, Figur] = {}
for _f in _CAST:
    _INDEX[_f.key] = _f
    for _a in _f.aliases:
        _INDEX.setdefault(_a.lower(), _f)

# Stimmen, die der feste Cast belegt — Gäste dürfen KEINE davon bekommen.
_CAST_VOICES = {f.voice for f in _CAST}

# ── Gast-Stimmen-Pool (nicht vom Cast belegt) + hörbares Merkmal je Stimme ──────
# Guest-Regel: von Flash erfundene Zusatzfiguren klingen hörbar anders als der
# Cast und tragen ein Merkmal (tiefe Stimme, bedächtig, hell …).
_GUEST_POOL: list[tuple[str, str]] = [
    ("Orus",       "Sprich mit tiefer, ruhiger Stimme, ein wenig bedächtig."),
    ("Umbriel",    "Sprich gemächlich und etwas brummig, gutmütig."),
    ("Rasalgethi", "Sprich lebhaft und rau, mit Schwung."),
    ("Callirrhoe", "Sprich sanft und hell, freundlich zurückhaltend."),
    ("Laomedeia",  "Sprich flott und aufgeweckt, mit heller Stimme."),
    ("Sulafat",    "Sprich warm und getragen, mit ruhigem Ernst."),
]
assert not (_CAST_VOICES & {v for v, _ in _GUEST_POOL}), "Gast-Pool kollidiert mit Cast-Stimmen"


def _norm(name: str) -> str:
    """Namen für den Abgleich normalisieren: klein, Titel/Rollen-Vorsätze weg."""
    n = (name or "").strip().lower()
    # führende Titel/Rollen entfernen, damit „Dr. Samir" → „samir",
    # „Meeresbiologin Ronja" → „ronja", „Oma Rosa" bleibt (Alias fängt es).
    for t in ("dr.", "dr", "doktor", "professor", "prof.",
              "meeresbiologin", "museums-forscherin", "forscherin",
              "tierpflegerin", "pflegerin", "naturführerin", "naturfuehrerin",
              "werkstatt-erfinder", "erfinder", "astronom", "lehrerin",
              "chronist", "weltenbummler", "nachbar", "arzt"):
        if n.startswith(t + " "):
            n = n[len(t) + 1:].strip()
            break
    return n


def lookup(name: str) -> Figur | None:
    """Feste Cast-Figur zu einem (Sprecher-)Namen finden — tolerant. None, wenn
    der Name zu keiner festen Figur gehört (dann Gast, s. guest_voice/guest_style)."""
    if not name:
        return None
    raw = name.strip().lower()
    if raw in _INDEX:
        return _INDEX[raw]
    n = _norm(name)
    if n in _INDEX:
        return _INDEX[n]
    # Einzelner Vorname als Teil eines Mehrwort-Namens (z. B. „Oma Rosa" → „rosa")
    for tok in n.split():
        if tok in _INDEX:
            return _INDEX[tok]
    return None


def narrator() -> Figur:
    return _INDEX[NARRATOR_KEY]


def _guest_slot(name: str) -> tuple[str, str]:
    """Deterministische Gast-Stimme+Merkmal aus dem Namen (stabil über Läufe:
    md5 statt hash(), das ist pro Prozess gesalzen)."""
    h = int(hashlib.md5((name or "gast").strip().lower().encode("utf-8")).hexdigest(), 16)
    return _GUEST_POOL[h % len(_GUEST_POOL)]


def guest_voice(name: str) -> str:
    return _guest_slot(name)[0]


def guest_style(name: str) -> str:
    return _guest_slot(name)[1]


def all_figures() -> list[Figur]:
    return list(_CAST)
