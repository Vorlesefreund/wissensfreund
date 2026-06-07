# Wissensfreund — Grundregel Quellenprüfung (verbindlich)

<!-- Für CLAUDE.md / Wissens-Doku. Gilt für jede Faktenprüfung, sowohl im
     Lektorats-Pass als auch in der Beratung durch Claude Chat. -->

## Die Regel

Vor JEDEM Faktencheck eines erzeugten Artikels:

1. **Vollständigen Quelltext beschaffen.** Den echten, vollständigen deutschen
   Wikipedia-Artikel abrufen (in der Pipeline: der injizierte WIKIPEDIA_TEXT;
   in der Beratung: per `fetch` des Artikels). Kein Auszug, keine Zusammenfassung.
2. **Nur an dieser Quelle prüfen.** Niemals aus Such-Snippets, Sekundärquellen
   (z. B. Olympics.com, Biografien, andere Lexika) oder aus Eigen-/Trainingswissen.
   Widerspricht das eigene Wissen dem Quelltext, gilt der Quelltext.
3. **Belegzitat-Pflicht.** Kein Urteil BELEGT/ÜBERTRIEBEN/NICHT_BELEGT ohne
   wörtliches Zitat aus dem Quelltext. Ein Urteil ohne Beleg ist ungültig und gilt
   selbst als Halluzination.
4. **„Nicht gefunden" ≠ „falsch".** Wird eine Aussage nicht gefunden, lautet das
   Urteil „im Quelltext nicht gefunden — unentscheidbar", nicht „falsch".
   Vor einem NICHT_BELEGT erst den GESAMTEN Text nach den Schlüsselwörtern absuchen.
5. **Kein Schein-Check.** Liegt kein Volltext vor, wird der Faktencheck NICHT
   ausgeführt und NICHT vorgetäuscht — sondern offen gesagt: „Faktencheck ohne
   Volltext nicht möglich."

## Warum diese Regel an erster Stelle steht

Diese Regel wurde im Projekt zugesichert und dennoch zweimal verletzt:
- Ein Basketball-Faktencheck lief auf Such-Snippets + Sekundärquellen und erklärte
  belegte Aussagen fälschlich zu Fehlern (False Positives: „Volleyball-ähnlicher
  Ball" und „1998-Vorteil-Nachteil-Prinzip" stehen tatsächlich in der Quelle).
- Ein Elefant-Faktencheck wurde zunächst offengelassen („verify"), statt den
  Volltext zu holen — derselbe Abwesenheits-Fehler in milder Form.

Ein unzuverlässiger Prüfer ist schlimmer als kein Prüfer: Er macht aus richtigen
Antworten falsche. Deshalb ist die Absicherung strukturell (Belegzitat-Pflicht),
nicht eine bloße Zusage. Sichtbarste Kontrolle: Ein Faktenurteil ohne Quelltext-
Zitat ist sofort als ungültig erkennbar — auch beim manuellen Gegenlesen.

## Zusatz: Lange Artikel werden bei einem einzelnen Abruf abgeschnitten

Sehr lange Wikipedia-Artikel (z. B. „Elefanten") passen nicht in einen einzigen
fetch — der Abruf bricht ab, und der **abgeschnittene Schwanz** (oft Ernährung,
Ökologie, Bedrohung) enthält genau die zu prüfenden Aussagen.

Konsequenz für die Regel:
- „Im abgerufenen Text nicht gefunden" kann schlicht „nicht abgerufen" bedeuten —
  das ist KEIN Befund gegen den Artikel und darf nicht als Mangel gewertet werden.
- Vor jeder Faktenbilanz den GANZEN Artikel sichern: mehrere/gezielte fetches,
  oder die fehlenden Abschnitte gezielt nachladen/einfügen.
- Niemals eine vergleichende Bewertung („Modell X hat mehr Fehler") aus einer
  unvollständigen Quelle ableiten.

Anlass: Beim Elefant-Vergleich wurden „150 kg/Tag" und „38.000 gewilderte
Elefanten/Jahr (Schätzung 2009)" fälschlich als „unbelegt" markiert — beide standen
in der abgeschnittenen Sektion und sind belegt. Das überzeichnete ein Modell
(3.5 Flash) im Vergleich. Derselbe Wurzelfehler wie der Snippet-Check: unvollständige
Quelle erzeugt False-Negative-Flags.

## Zusatz: Gegen den Generierungs-Snapshot prüfen — die Quelle ist veränderlich

Wikipedia-Artikel werden laufend editiert. Eine Aussage, die zur Generierungszeit
belegt war, kann später im Artikel geändert sein. Wird der Faktencheck gegen ein
*später* nachgeladenes Exemplar geführt, entstehen Scheinfehler, die in Wirklichkeit
nur zwischenzeitliche Edits sind.

Regel:
- Immer gegen den QUELLTEXT-SNAPSHOT DER GENERIERUNGSZEIT prüfen. In der Pipeline ist
  das der injizierte WIKIPEDIA_TEXT — derselbe Text, aus dem generiert wurde.
- Niemals für den Check ad hoc neu fetchen und das Ergebnis gegen den alten Artikel
  halten. Genau das erzeugt Versions-Mismatch.
- Die Pipeline-Architektur (Text injizieren, gegen den injizierten Text prüfen) ist
  deshalb korrekt; ad-hoc-Nachladen in der Beratung ist die Fehlerquelle.

Anlass: Im Elefant-Artikel wurde das Angola-Maß von „4 m / ~10 t" (erster Abruf,
= Generierungszeitpunkt der Modelle) auf „3,8 m / knapp 8 t" (späterer Volltext)
editiert. Sonnet und 3.1 Pro hatten „4 m / 10 t" geschrieben — zur Generierungszeit
belegt, kein Modellfehler, sondern eine Wikipedia-Änderung.
