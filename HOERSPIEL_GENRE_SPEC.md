# Hörspiel-Genre — Generator-Spec (Paket B)

<!-- erstellt: 2026-07-19 · Status: PO-Forks entschieden 2026-07-19; Prompt gebaut (wissensfreund_hoerspiel_prompt_v1.md) -->

Spec für den **Hörspiel-Inhaltstyp** (4–9 J.) im Generator. Abgeleitet
**rückwärts aus der abgenommenen Leonardo-Prosa** (`assets/test/leo_mit_tags_l2.json`,
PO-abgenommen 2026-07-18) + Serien-Cast (`tts_samples.py`) + TTS-Feasibility
(`tts_story.py`). Der Erzähltext (10–12) bleibt die bestehende Sachprosa (v5.2).

## 1. Was fix ist (aus der abgenommenen Prosa, nicht verhandelbar)

Die Leonardo-Fassung ist die Referenz. Ablesbare, zu bewahrende Konventionen:

- **Dialogisierte Szene statt Sachprosa** (Hörspiel-Format). Fakten stecken IM
  Gespräch, nicht in Erzählabsätzen. Ton = **spannend + unterhaltsam + warm**, aus
  echter Neugier — NICHT theatralisch/reißerisch (PO 2026-07-19). EISERNE REGEL
  bleibt: jeder Fakt aus dem Wikipedia-Quelltext.
- **Rollenverteilung der Fakten:** Die **erwachsene** Figur spricht die belegten
  Fakten; das **Kind** fragt/staunt und trägt KEINE Fakten (nur Wunder + die
  natürliche nächste Frage). Naive Kinder-Framings („Mann mit vier Armen") richten
  eine faktische Korrektur ein.
- **Körper-/Szenen-Aktionen als Erzähler-Zeilen** verankern Bilder und takten das
  Stück („Theo blättert weiter…", „…streicht über eine Zeichnung", „Oma lacht.").
- **Redebegleitsätze bleiben verbatim** („sagt Oma Rina", „fragt Theo") — der
  Erzähler spricht sie mit (Text = Audio für die Mitlese-Lupe). Kern des „mit Tags".
- **Konkreter Einstieg + warmer, thematischer Schluss** (Bilderbuch aufschlagen →
  „ich will auch alles wissen"). Kein Fakten-Cliffhanger.
- **Bild-Anker:** `img_index` schreitet über die Bilder, an dem, „was sie gerade
  ansehen" (Leonardo: 0→1→2 über 3 Bilder).

## 2. Schema bleibt gleich (JSON v1.0)

Das Hörspiel nutzt **dasselbe Ausgabeschema** wie der Erzähltext — nur der Prosa-
Stil in `sections[].sentences[].text` wird zu Dialog/Erzähler-Zeilen. Damit laufen
Bildpipeline, `source_passages` (Grounding-Audit!), Quiz und der TTS-„mit-Tags"-
Segmentierer unverändert weiter.

- `source_passages`: **bleibt Pflicht** — jede faktische (Erwachsenen-)Aussage mit
  wörtlichem Quellzitat. Das ist der prüfbare EISERNE-REGEL-Anker; unbedingt behalten.
- `sections`: 1–3 Abschnitte, `section_role: "story"`, `heading` leer.
- `sentences[].id` global fortlaufend; `img_index` wie gehabt.

## 3. Cast (auf das TTS-Modell abgestimmt — 3 Rollen)

`tts_story.py` segmentiert heute in genau **drei Rollen** mit festen Stimmen:
Erzähler=Iapetus · Kind (Puck ♂ / Leda ♀) · Erwachsener (Gacrux ♂ / Vindemiatrix ♀).
Der volle 11-Figuren-Cast ist noch NICHT verdrahtet → Zielmodell = diese drei:

- **Erzähler** (Professor/Iapetus): rahmt Anfang + Ende, spricht Aktionen +
  Redebegleitsätze.
- **Kind**: der wiederkehrende rote Faden — **Mia** (♀) oder **Mio** (♂). Fragt/staunt.
- **Erwachsene Bezugsperson**: EINE pro Folge, Name/Persona nach Themen-**Kategorie**
  (`category_top`) — Geschichte→Oma/Opa, Museum/Kunst→Forscher/in, Technik→Erfinder/in,
  Natur→Naturführer/in, Meer→Meeresbiologe/in, Himmel→Sternwarten-Opa/-Oma. Generelle
  Regel (kategorie-gekoppelt), KEIN Thema-Hardcoding. Gerendert über die gegenderte
  „erwachsener"-Stimme.

## 4. Umsetzung (Empfehlung, kein PO-Fork)

- **Eigene Prompt-Datei** `wissensfreund_hoerspiel_prompt_v1.md`, per `content_type`
  ausgewählt (statt v5.2 mit einem Riesen-Conditional aufzublähen). v5.2 bleibt der
  Erzähltext-Prompt unangetastet.
- Phase 1 (Kompass) läuft weiter EINMAL je Thema; das Hörspiel dramatisiert dieselben
  geplanten Fakten (kein zweiter Quell-Plan).
- Wortband (225,975) wie verdrahtet; Turn-Zahl floatet; Trim bei 12 min (TTS).

## 5. PO-Entscheidungen (2026-07-19)

1. **Kind:** wiederkehrend **Mia/Mio** (Serien-Wiedererkennung); Generator wählt passend. ✓
2. **Erwachsene Bezugsperson:** **situativ von Flash gewählt** — passend zum Thema,
   glaubwürdig; Kategorie-Beispiele sind Anregung, **keine feste Zuordnung** (PO 2026-07-19). ✓
3. **Boxen im Hörspiel:** **keine** (`boxes: []`); Quiz bleibt (genau 3 Fragen). ✓
4. **Cast:** **immer Erzähler + Kind + eine erwachsene Bezugsperson** (3 feste Rollen);
   **optionale vierte Figur**, wenn die Story davon lebt — Flash entscheidet situativ
   (PO 2026-07-19). Voller Multi-Voice-Cast = späteres Upgrade (§6). ✓
5. **Ton:** spannend/unterhaltsam/warm, nicht dramatisch-theatralisch. ✓

Umgesetzt in `wissensfreund_hoerspiel_prompt_v1.md`, verdrahtet über `content_type`
in `generate_grounded.py` (`system_prompt_for`, Cache je Typ).

**Offen vor der ersten Finalproduktion (zeitnah, eigener Task):**
- **Finale Namen** aller Figuren (Kind, Bezugspersonen, ggf. 4. Figur).
- **Voice-Cast:** Rollen→Stimmen final; für die **optionale 4. Figur / einen zweiten
  Erwachsenen** braucht `tts_story.py` eine Erweiterung (heute nur EIN „erwachsener"-
  Slot, gegendert) — sonst teilt sich die 4. Figur die Stimme der Bezugsperson.

## 6. Downstream-Abhängigkeit (Flag, nicht Paket B)

Voller Multi-Voice-Cast später = Arbeit in `tts_story.py` (Rollen→Stimme über
benannten Cast statt nur Geschlecht) + PO-Abnahme der 11 Hörproben. Nicht Teil dieses
Pakets.
