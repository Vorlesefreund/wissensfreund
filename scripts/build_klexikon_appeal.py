#!/usr/bin/env python3
"""
build_klexikon_appeal.py
Erzeugt klexikon_appeal_quartil.json aus der Klexikon-Meistbesuchte-Liste 2022
und dem Top-10-Override 2025.

Quartile:
  Q1 / high   = Top-10 2025 + Bänder 1–3 (>5.000 Aufrufe 2022)
  Q2 / medium = Bänder 4–7 (1.000–5.000 Aufrufe 2022)
  null        = nicht in der 2022-Liste (Feld wird weggelassen; Generator schätzt selbst)

Verwendung:
    python scripts/build_klexikon_appeal.py
    python scripts/build_klexikon_appeal.py --out klexikon_appeal_quartil.json
    python scripts/build_klexikon_appeal.py --dry-run   # nur Report, kein Schreiben
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ─── Quelldaten ──────────────────────────────────────────────────────────────

# Klexikon-Startseite 2025 — Top-10 fix (Q1, quelle="klexikon_top10_2025")
TOP10_2025: list[str] = [
    "Organe", "Erde", "Römisches Reich", "Deutschland", "Wolfgang Amadeus Mozart",
    "Hunde", "Europa", "Äquator", "Suchmaschine", "Katzen",
]

# Hilfe:Meistbesuchte_Artikel_2022 — Bänder
# Quelle: https://klexikon.zum.de/wiki/Hilfe:Meistbesuchte_Artikel_2022
# Abruf: 2026-06-05, vollständige Liste

BAND_1_GT20K: list[str] = [
    "Zehn Gebote", "Erde", "Römisches Reich", "Mittelalter", "Eichhörnchen",
    "Äquator", "Deutschland", "Kommunismus", "Mensch", "Steinzeit",
]

BAND_2_GT10K: list[str] = [
    "Mose", "Wolfgang Amadeus Mozart", "Hunde", "Halloween", "Reh",
    "Zeitzone", "Wolf", "Martin Luther", "Frankreich", "Erster Weltkrieg",
    "Altes Ägypten", "Italien", "Wikipedia", "Französische Revolution",
    "Österreich", "Nikolaus", "Verwandtschaft", "Klexikon", "Igel", "Europa",
    "Islam", "Judentum", "Schweiz", "Bibel", "Rattenfänger von Hameln",
    "Jahreszeiten", "Sonne", "Suchmaschine", "Hinduismus", "Klavier",
    "Jugoslawien", "Christoph Kolumbus", "Zweiter Weltkrieg", "Katzen",
    "Wasser", "Hochkultur", "Abraham", "Weimarer Republik", "Löwe",
    "Hauskatze", "Relativitätstheorie", "Türkei", "Elektrizität", "Fische",
    "Weihnachten", "Pinguine", "Britisches Weltreich", "Orthodoxe Kirche",
    "Berlin", "Mond",
]

BAND_3_GT5K: list[str] = [
    "Schlangen", "Verdauung", "Aufklärung", "Popmusik", "Dinosaurier",
    "Pferde", "Indianer", "Spanien", "Reptilien", "Brüder Grimm", "Getreide",
    "Klimawandel", "Gitarre", "Altes Griechenland", "Polen", "Kontinent",
    "Himmelsrichtung", "Saturn", "Sonnensystem", "Planet", "Eulen", "Vulkan",
    "Paris", "Jesus", "Albert Einstein", "Demokratie", "Tiger", "Waldtiere",
    "Computer", "Mars", "Schildkröten", "Eiffelturm", "Osmanisches Reich",
    "Herz", "Griechenland", "Delfine", "Polarkreis", "Wald", "London",
    "Eisbär", "Wetter", "Säugetiere", "Epoche", "Russland", "Pilze", "Wale",
    "Buddhismus", "Blutkreislauf", "Hamburg", "Jupiter", "Ernährung",
    "Hip Hop", "Nationalsozialismus", "Wildschwein", "Geschichte",
    "Dreißigjähriger Krieg", "Hasen", "Industrielle Revolution", "Fledermäuse",
    "Bayern", "Stern", "Katar", "Kaninchen", "Ägypten", "Christentum",
    "Australien", "Koala", "Großbritannien", "Elefanten", "DNA",
    "Nahostkonflikt", "Niederlande", "Portugal", "Adam und Eva", "Ötzi",
    "Südamerika", "Urknall", "Alpen", "Ukraine", "Buckingham Palace",
    "Merkur", "Pharao", "Napoleon Bonaparte", "Skelett", "Kartoffel",
    "Schnecken", "Ethik", "Hamster", "Uranus", "Asien", "England", "Afrika",
    "Tiere", "Muscheln", "Antarktis", "Karl der Große", "Blindenschrift",
    "Wirtschaft", "Bundesland", "Tierarten", "Ritter", "Auge", "Leopard",
    "Amphibien", "Schweden", "Sozialismus", "Rockmusik", "Rom", "Belgien",
    "Nachhaltigkeit", "Biologie", "Spinnen", "Million", "Meer", "Fußball",
    "Rotfuchs", "Auto", "Neuzeit", "Neptun", "China", "Atomenergie", "Silbe",
    "Märchen", "Winter", "Altertum", "Mohammed", "Chemie", "Marder",
    "Energie", "Atome und Moleküle", "Buche", "Laubbaum", "Respekt",
    "Germanen", "Herbst", "Meerschweinchen", "Atmosphäre", "Advent",
    "Kolonie", "Kastanien", "Winterschlaf", "Weltall", "Nibelungensage",
    "Rothirsch", "Tsunami", "Nikolaus Kopernikus", "Arabien", "Erntedankfest",
    "Adler", "Vietnamkrieg", "Photosynthese", "Hiob", "Bienen", "Schlagzeug",
    "Nil", "Adolf Hitler", "Nordrhein-Westfalen", "Lexikon", "Internet",
    "Pyramiden von Gizeh", "Baum", "Lunge", "Kirche", "Polarlicht",
    "Adjektiv", "Politik", "Affen", "Zeus", "Ludwig van Beethoven",
    "Europäische Union", "Weizen", "Karneval", "Inka", "Dänemark",
    "Märzrevolution", "Tower Bridge", "Deutscher Bund", "Rassismus",
    "Julius Cäsar", "Palästina", "Venus", "Darm", "Bruttoinlandsprodukt",
    "Johannes Gutenberg", "Lenin", "Streichinstrument", "Erdkunde", "Religion",
    "Wasserkreislauf", "Carl Benz", "Vincent van Gogh", "Seele",
    "Brandenburger Tor", "Römische Götter", "Finnland", "Titanic", "Toilette",
    "Michael Jackson", "Hauptstadt", "Physik", "Freiheitsstatue", "New York",
    "Johann Sebastian Bach", "Körper", "Gemeinde", "Indien",
    "Elisabeth die Zweite", "Reformationstag", "Heilige Drei Könige",
    "Vereinigte Staaten von Amerika", "Frösche", "Wind", "Archäologie",
    "Absolutismus", "Reformation", "Klima",
]

BAND_4_GT4K: list[str] = [
    "Till Eulenspiegel", "Malala Yousafzai", "Babylonien", "Gepard", "Zelle",
    "Sonnenfinsternis", "Koran", "Jahrhundert", "Polarfuchs", "Hirsche",
    "Schnee", "Wissenschaft", "Viereck", "Wüste", "Brücke", "Illuminati",
    "Spanisches Kolonialreich", "Kloster", "Blasinstrument", "Leonardo da Vinci",
    "Island", "Feuer", "Meter", "Hieroglyphen", "Kreuzzug", "Poseidon",
    "Maßstab", "Glück", "Michelangelo", "Russische Revolution", "Kroatien",
    "Jerusalem", "Maya", "Staat", "Katholische Kirche", "Erdmännchen",
    "Kultur", "Antonio Vivaldi", "Blues", "Geige", "Friedensreich Hundertwasser",
    "Marie Curie", "Umweltverschmutzung", "Kleopatra", "Pablo Picasso",
    "Recycling", "Griechische Götter", "Fossil", "Nadelbaum", "Zugvögel",
    "Bakterien", "Biber", "Apfel", "Iran", "Wiener Kongress", "Vögel",
    "Blauwal", "Kompass", "Leber", "Wasserkraft", "Gletscher", "Milchstraße",
    "Stadt", "Big Ben", "Beatles", "Haie", "Bronzezeit", "Gezeiten", "Eichen",
    "Joseph Haydn", "Germanische Götter", "Bären", "Pubertät", "Landkarte",
    "Otto von Bismarck", "Savanne", "Staaten der Erde", "Wien", "Kunststoff",
    "Füchse", "Erdgas", "Dreifaltigkeit", "Erdöl", "Braunbär", "Sexualität",
    "Gehirn", "Labrador (Hund)", "Schwerkraft", "Marienkäfer", "Ameisen",
    "Angelsachsen", "Regenbogen", "Nordamerika", "Niedersachsen",
    "Tag und Nacht", "Russischer Überfall auf die Ukraine", "Sachsen", "Luft",
    "Migration", "Robin Hood", "Bananen", "Höhlenmalerei", "Limes",
    "Niederschlag", "Japan", "Norwegen", "Gewitter", "Tornado", "Damaskus",
]

BAND_5_GT3K: list[str] = [
    "Flugzeug", "Alkohol", "Evolution", "Platon", "Fluss", "Galileo Galilei",
    "Imperialismus", "Metall", "Roggen", "Schmetterlinge", "Prophet",
    "Josef Stalin", "Wüstenfuchs", "König", "Magnet", "Augustus", "Sowjetunion",
    "Geld", "Windkraft", "Renaissance", "Pflanzen", "Urgeschichte", "Querflöte",
    "Giraffen", "Brasilien", "Claude Monet", "Monat", "Cristiano Ronaldo",
    "Zeitrechnung", "Schwarzes Loch", "Irland", "Milz", "Mutter Teresa",
    "Einwohner", "Wilhelm Tell", "Fortpflanzung", "Astrid Lindgren", "Zunft",
    "Haut", "Tannen", "Gotik", "Radioaktivität", "Medien", "Nomen", "Odysseus",
    "Kohlenhydrate", "Baron Münchhausen", "Galaxie", "Raupe", "Trompete",
    "Silvester", "Musik", "Licht", "Mäuse", "Kraftwerk", "Gott", "Thermometer",
    "Pessach", "Jungsteinzeit", "Luxemburg", "Nordische Mythologie", "Erdbeben",
    "Luchse", "Fichten", "Chanukka", "Hafer", "Aristoteles", "Golfstrom",
    "Mumie", "Geburt", "Gewissen", "Feuerwehr", "Muskel", "Erich Kästner",
    "Sage", "Mönch", "Telefon", "Held", "Albrecht Dürer", "Papier",
    "Inflation", "Oper", "Harfe", "Eiszeit", "Nation", "Periodensystem",
    "Nagetiere", "Syrien", "Yeti", "London Eye", "Blut", "Mahatma Gandhi",
    "Arktis", "Allerheiligen", "Mais", "Magen", "Waschbär", "Kinderlexikon",
    "Wort", "Wappen", "Deutsche Ostgebiete", "München", "Aborigines",
    "Hermannsdenkmal", "Frau", "Liberalismus", "Niere", "Fränkisches Reich",
    "Kanada", "Wiederkäuer", "Jazz", "Eidechsen", "Tschechien", "Dampfmaschine",
    "Robben", "Sieben Weltwunder", "Jahr", "Artikelübersicht Deutschland",
    "Kolosseum", "Husky", "Hühner", "Klarinette", "Balkan",
    "Johann Wolfgang von Goethe", "Zeugen Jehovas", "Natur", "Wirbelsäule",
    "Marco Polo", "Wildkatze", "Blindschleiche", "Nahrungskette", "Wikinger",
    "Software", "Sonnenenergie", "Ku-Klux-Klan", "Liebe", "Meteorit",
    "Holocaust", "Moschee", "Berliner Mauer", "Baden-Württemberg", "Gebirge",
    "Ungarn", "Tropen", "Olympische Spiele", "Weihnachtsmann",
    "Deutsche Sprache", "Pluto", "Stonehenge", "Philosophie", "Mark Forster",
    "Name", "Rhein", "Thomas Alva Edison", "Deutsches Kaiserreich", "Knochen",
    "Martin Luther King", "Schäferhund", "Schottland",
    "Amerikanischer Unabhängigkeitskrieg", "Pirat", "Landwirtschaft",
    "Tower of London", "Gedicht", "Hanse", "Ahorne", "Gerste", "Kapitalismus",
    "Dialekt", "Insekten", "Korallen", "Borkenkäfer", "Neandertaler",
    "Kinderrechte", "Taiga", "Varusschlacht", "Orchester", "Kunst",
    "Geschlechtsorgan", "Rosa Parks", "Kaiser", "Dachse", "Motor",
    "Wirbeltiere", "Ungeheuer von Loch Ness", "Charles Darwin",
    "Sherlock Holmes", "Birken", "Musikinstrument", "Todesstrafe", "Faschismus",
    "Wasserstoff", "Jaguar", "Grundrechenarten", "Abstrakte Kunst", "Fahrrad",
    "Roboter", "Musical", "Nelson Mandela", "Azteken", "Lionel Messi",
]

BAND_6_GT2K: list[str] = [
    "Fotografie", "Perserkriege", "Elisabeth die Erste", "Nationalhymne",
    "Amsel", "Buchdruck", "Rheinland-Pfalz", "Ärmelkanal", "Präposition",
    "Latein", "Basketball", "Byzantinisches Reich", "Quelle", "Kind",
    "Salamander", "Albanien", "Theater", "Leben", "Argentinien", "Urheberrecht",
    "Sprache", "Heiliges Römisches Reich", "Schaltjahr", "Recht", "Afghanistan",
    "Sturm", "Vereinte Nationen", "Mount Everest", "Heiliger", "Isaac Newton",
    "Farbe", "Erneuerbare Energie", "Ostern", "Schall", "Integration",
    "Französisches Kolonialreich", "Barock", "Burg", "Nordpol", "Donau",
    "Republik", "Mammut", "Regenwald", "Pyramide", "Piktogramm",
    "Elsaß-Lothringen", "Mesopotamien", "Rakete", "Krieg", "Ferdinand Magellan",
    "Chamäleon", "Blockflöte", "Revolution", "Sudetenland", "Enten", "Nomade",
    "Rumänien", "Peter Tschaikowski", "Freundschaft", "Bischof", "Quader",
    "Archimedes", "Rätoromanische Sprachen", "Werbung", "Hernán Cortés",
    "Oktoberfest", "Holz", "Terroranschläge vom 11. September", "Verb",
    "Komet", "Tintenfische", "Arnold Schwarzenegger", "Quallen", "Adel",
    "Ökosystem", "Oskar Schindler", "Euphrat und Tigris", "Karl Marx", "Wolke",
    "Südpol", "Orgel", "Ohr", "Hessen", "Kohle", "Mexiko", "Kosovo", "Blüte",
    "Schweine", "Skorpion", "Puma", "Technik", "Johannes der Täufer",
    "Bundeskanzler", "Informatik", "Kalter Krieg", "Flagge", "Menschenrechte",
    "Schleswig-Holstein", "Polizist", "Vitamin", "Sternbild", "Mauritius",
    "Orient", "Harry Potter", "Posaune", "Abfall", "Mona Lisa", "Schach",
    "Buch", "Symbol", "Bonnie und Clyde", "Zuckerfest", "Klassik", "Bundestag",
    "Ozeanien", "Kohlenstoff", "Albert Schweitzer", "Skateboard", "Beat",
    "Fridays for Future", "Nonne", "Wales", "Flöte", "Erdaltertum", "Mann",
    "Pest", "Ludwig der Vierzehnte", "Satellit", "Nordsee", "Kelten", "Sand",
    "Akropolis", "Zucker", "Messias", "Georg Friedrich Händel", "Ganges",
    "Gold", "Venedig", "Tutanchamun", "Pädagogik", "Gustav Klimt", "Zeit",
    "Ader", "Totes Meer", "Kreuzotter", "Lokomotive", "Kontrabass",
    "Datenschutz", "Holocaust-Mahnmal", "Guinea", "Celsius", "Eidgenossenschaft",
    "Fabel", "Haustiere", "Pandas", "Schokolade", "Eskimo",
    "Alexander der Große", "Sumerer", "Bier", "Eiweiß", "Kölner Dom", "App",
    "Deutsche Kolonien", "Apollo 11", "Kot", "Schwertwal", "Tourismus",
    "Schlesien", "Kläranlage", "Fortnite", "Evangelische Kirchen", "Saarland",
    "Tradition", "Noah", "Benito Mussolini", "Turnen", "Papageien",
    "Gemäßigte Zone", "Griechische Sprache", "Temperatur", "Bulgarien", "Oder",
    "Bussarde", "Strom", "Kokosnuss", "Kamele", "Uluru", "Bauernhof",
    "Cornelia Funke", "Gestein", "Dudelsack", "Michail Gorbatschow", "Taufe",
    "Beruf", "Joseph Goebbels", "Breitenkreis", "Hildegard von Bingen",
    "Louvre", "Alchemie", "Oase", "Erdachse", "Krebse", "Thüringen", "Sklave",
    "Papst", "Reichstag", "Landschaft", "Trojanisches Pferd", "Pronomen",
    "Fremdwort", "Schlacht von Stalingrad", "Backbord und Steuerbord",
    "Sozialdemokratie", "Radio", "Faultiere", "Bremen", "Martin von Tours",
    "Impressionismus", "Arabischer Frühling", "Arzt", "Fußball-Weltmeisterschaft",
    "Tausendundeine Nacht", "Volleyball", "Salvador Dalí", "Serbien",
    "Berliner Fernsehturm", "Südafrika", "Moor", "Atmung", "Saxophon",
    "Immanuel Kant", "Astronaut", "Engel", "Amerika", "Richard Löwenherz",
    "Eisen", "Gorillas", "Spechte", "Schule", "Fett", "Glaube", "Tuba",
    "Geist", "Palmen", "Eisenbahn", "Regen", "Pflanzenarten", "Xylophon",
    "Subtropen", "Staatsoberhaupt", "Kristall", "Habsburger", "Tierarzt",
    "Heavy Metal", "Paulus", "Menstruation", "Schneeleopard", "Primzahl",
    "Brandenburg", "Bangladesch", "Anne Frank", "Fliegenpilz", "Pazifischer Ozean",
    "ABBA", "Sokrates", "Hitlerjugend", "Kängurus", "Nase", "Haselnuss",
    "Eisenzeit", "Gefühl", "Brüder Wright", "Country-Musik", "Altsteinzeit",
    "Queen (Band)", "Rohstoff", "Utopie", "Maximilien de Robespierre", "Milch",
    "Seepferdchen", "Deutsche Währung", "Obst", "Minecraft", "Atheismus",
    "Francisco Franco", "Preußen", "Atlantischer Ozean", "Kinderarbeit",
    "Pfau", "Dinkel", "Marokko", "Meerestiere",
]

BAND_7_GT1K: list[str] = [
    "Telegrafie", "Bundesstaat", "Dodo-Vogel", "Hans Christian Andersen",
    "Musikrichtung", "Dalai Lama", "Nebel", "Meeresspiegel", "Zebras",
    "Velociraptor", "Schloss Versailles", "Westliche Welt",
    "Mecklenburg-Vorpommern", "Parlament", "Opferfest", "Raubtiere",
    "Abraham Lincoln", "Alaska", "Oboe", "Aktie", "Drache", "Literatur",
    "Israel", "Schmied", "Außerirdische", "Ei", "Windrad", "Schwangerschaft",
    "Armut", "Globus", "Mobbing", "Baumwolle", "Reis", "Architektur",
    "Sachsen-Anhalt", "Ramadan", "Büffel", "Schiff",
    "Links und Rechts (Politik)", "Kupfer", "Astronomie", "Sphinx", "Steppe",
    "Frieden", "Pippi Langstrumpf", "Ruhrgebiet", "Chinesische Mauer",
    "Bermuda-Dreieck", "Kakao", "Pfingsten", "Bosnien und Herzegowina", "Salz",
    "Köln", "Frida Kahlo", "Farne", "Kleidung", "Puls", "Geysir", "Nachname",
    "Maulwürfe", "Mondfinsternis", "Denkmal", "Teufel", "Aschenputtel", "Gen",
    "Siegessäule", "Handy", "Insel", "Abendmahl", "Krokodile", "Erdboden",
    "Gesetz", "Golden Gate Bridge", "Staudamm", "Soziale Medien",
    "Frankfurt am Main", "Nobelpreis", "Seesterne", "Elbe", "Schrift",
    "Umwelt", "Vasco da Gama", "Erfinder", "Gliederfüßer", "James Cook",
    "Schiefer Turm", "Hollywood", "Geldwäsche", "Gesellschaft", "Schnitzel",
    "Virus", "Gewässer", "Sucht", "Gesundheit", "Klaus Störtebeker", "YouTube",
    "Samen", "Himmel", "Zunge", "Adverb", "Klimaschutz", "Meteorologie",
    "Zahn", "Synagoge", "Völkerwanderung", "Rübezahl", "Regierung", "Hawaii",
    "Umweltschutz", "Zeitung", "Dracula", "Rotkehlchen", "Ballett", "Schlager",
    "Tundra", "Bagger", "Punk", "Längenkreis", "Dresden", "Athen",
]

# ─── Slug-Normalisierung ──────────────────────────────────────────────────────

def normalize_slug(title: str) -> str:
    """
    Klexikon-Titel → Basis-Slug (ohne _lN-Suffix).
    Umlaute, Sonderzeichen, Leerzeichen normalisieren.
    Kein Singular/Plural-Mapping — das übernimmt die Pipeline beim Abgleich.
    """
    s = title.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    # Klammern-Suffix entfernen (z.B. "Labrador (Hund)" → "labrador")
    s = re.sub(r"\s*\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


# Bekannte Plural→Singular-Mappings (nur Fälle wo Slug-Mismatch erwartet wird)
PLURAL_SINGULAR: dict[str, str] = {
    "elefanten":            "elefant",
    "katzen":               "katze",
    "hunde":                "hund",
    "pinguine":             "pinguin",
    "hasen":                "hase",
    "schmetterling":        "schmetterling",
    "schmetterlinge":       "schmetterling",
    "fledermaeuse":         "fledermaus",
    "schnecken":            "schnecke",
    "schildkroeten":        "schildkroete",
    "bienen":               "biene",
    "spinnen":              "spinne",
    "wale":                 "wal",
    "eulen":                "eule",
    "schlangen":            "schlange",
    "pferde":               "pferd",
    "affen":                "affe",
    "pilze":                "pilz",
    "fische":               "fisch",
    "frosche":              "frosch",
    "froesche":             "frosch",
    "delfine":              "delfin",
    "haie":                 "hai",
    "kaninchen":            "kaninchen",  # schon singular
    "tintenfische":         "tintenfisch",
    "insekten":             "insekt",
    "amphibien":            "amphibie",
    "reptilien":            "reptil",
    "saeugetiere":          "saeugetier",
    "voegel":               "vogel",
    "bären":                "baer",
    "baeren":               "baer",
    "fuechse":              "fuchs",
    "fuechse":              "fuchs",
    "luchse":               "luchs",
    "giraffen":             "giraffe",
    "maeuse":               "maus",
    "nagetiere":            "nagetier",
    "raubtiere":            "raubtier",
    "zebras":               "zebra",
    "kängurus":             "kaenguru",
    "kaenguruhs":           "kaenguru",
    "kamele":               "kamel",
    "dachse":               "dachs",
    "robben":               "robbe",
    "gorillas":             "gorilla",
    "ameisen":              "ameise",
    "muscheln":             "muschel",
    "seesterne":            "seestern",
    "bussarde":             "bussard",
    "spechte":              "specht",
    "quallen":              "qualle",
    "krebse":               "krebs",
    "zugvoegel":            "zugvogel",
    "zugvögel":             "zugvogel",
    "hühner":               "huhn",
    "huehner":              "huhn",
    "enten":                "ente",
    "papageien":            "papagei",
    "krokodile":            "krokodil",
    "wirbeltiere":          "wirbeltier",
    "wiederkäuer":          "wiederkaeuer",
    "faultiere":            "faultier",
    "kängurus":             "kaenguru",
    "pandas":               "panda",
    "korallenriff":         "korallenriff",
    "korallen":             "koralle",
    "suchmaschinen":        "suchmaschine",
    "katzen":               "katze",
    "organe":               "organ",
    "brüder grimm":         "brüder grimm",
}


def to_slug(title: str) -> str:
    """Normalisiert + bekannte Plural-Singular-Korrekturen."""
    slug = normalize_slug(title)
    return PLURAL_SINGULAR.get(slug, slug)


# Kurzform-Slug → kanonischer Klexikon-Titel.
# Zweck: WF-Artikel die mit Kurzform-Slug (z.B. "einstein") generiert werden,
# sollen trotzdem ein Quartil-Signal bekommen, auch wenn der Klexikon-Eintrag
# den vollen Namen trägt ("Albert Einstein").
SLUG_ALIASES: dict[str, str] = {
    # Personen
    "einstein":          "Albert Einstein",           # Band 3, Q1
    "beethoven":         "Ludwig van Beethoven",       # Band 3, Q1
    "mozart":            "Wolfgang Amadeus Mozart",    # Band 2, Q1
    "kolumbus":          "Christoph Kolumbus",         # Band 2, Q1
    "gutenberg":         "Johannes Gutenberg",         # Band 3, Q1
    "da_vinci":          "Leonardo da Vinci",          # Band 4, Q2
    "newton":            "Isaac Newton",               # Band 6, Q2
    "gandhi":            "Mahatma Gandhi",             # Band 5, Q2
    "mlk":               "Martin Luther King",         # Band 5, Q2
    "malala":            "Malala Yousafzai",           # Band 4, Q2
    "magellan":          "Ferdinand Magellan",         # Band 6, Q2
    "humboldt":          "Alexander von Humboldt",     # ggf. nicht in 2022-Liste
    # Orte / Themen mit abweichender WF-Benennung
    "pyramiden":         "Pyramiden von Gizeh",        # Band 3, Q1
    "pharaonen":         "Pharao",                     # Band 3, Q1
    "nordlicht":         "Polarlicht",                 # Band 3, Q1
    "mondlandung":       "Apollo 11",                  # Band 6, Q2
    "solarenergie":      "Sonnenenergie",              # Band 5, Q2
    "windkraftanlage":   "Windkraft",                  # Band 4, Q2
    "dodo":              "Dodo-Vogel",                 # Band 7, Q2
}


# ─── Mapping aufbauen ─────────────────────────────────────────────────────────

def build_entries() -> list[dict]:
    """Alle Bänder + Top-10-Override → normierte Einträge."""
    entries: dict[str, dict] = {}   # slug → entry

    # Top-10 2025 zuerst (Override-Priorität)
    for titel in TOP10_2025:
        slug = to_slug(titel)
        entries[slug] = {
            "slug":            slug,
            "klexikon_titel":  titel,
            "aufrufe_oder_rang": "top10_2025",
            "quartil":         1,
            "quelle":          "klexikon_top10_2025",
            "jahr":            "2025",
        }

    # Bänder einlesen
    band_specs = [
        (BAND_1_GT20K, ">20000", 1, "klexikon_liste_2022"),
        (BAND_2_GT10K, ">10000", 1, "klexikon_liste_2022"),
        (BAND_3_GT5K,  ">5000",  1, "klexikon_liste_2022"),
        (BAND_4_GT4K,  ">4000",  2, "klexikon_liste_2022"),
        (BAND_5_GT3K,  ">3000",  2, "klexikon_liste_2022"),
        (BAND_6_GT2K,  ">2000",  2, "klexikon_liste_2022"),
        (BAND_7_GT1K,  ">1000",  2, "klexikon_liste_2022"),
    ]

    for band_list, schwelle, quartil, quelle in band_specs:
        for titel in band_list:
            slug = to_slug(titel)
            if slug in entries:
                # Top-10-Override oder früheres Band — nur quelle ergänzen
                existing = entries[slug]
                if existing["quelle"] == "klexikon_top10_2025":
                    existing["quelle"] = f"klexikon_top10_2025+liste_2022"
                    existing["aufrufe_oder_rang"] = f"top10_2025+{schwelle}"
                    existing["jahr"] = "2022/2025"
                # Früheres Band hat höhere Priorität → nicht überschreiben
                continue
            entries[slug] = {
                "slug":            slug,
                "klexikon_titel":  titel,
                "aufrufe_oder_rang": schwelle,
                "quartil":         quartil,
                "quelle":          quelle,
                "jahr":            "2022",
            }

    # Alias-Einträge: Kurzform-Slug → Quartil des kanonischen Eintrags
    for alias_slug, klexikon_titel in SLUG_ALIASES.items():
        canonical_slug = to_slug(klexikon_titel)
        if alias_slug in entries:
            continue  # bereits direkt vorhanden
        canonical = entries.get(canonical_slug)
        if canonical is None:
            continue  # kanonischer Titel nicht in der 2022-Liste
        entries[alias_slug] = {
            "slug":            alias_slug,
            "klexikon_titel":  canonical["klexikon_titel"],
            "aufrufe_oder_rang": canonical["aufrufe_oder_rang"],
            "quartil":         canonical["quartil"],
            "quelle":          canonical["quelle"],
            "jahr":            canonical["jahr"],
        }

    return sorted(entries.values(), key=lambda e: (e["quartil"], e["klexikon_titel"]))


# ─── Wissensfreund-Abgleich ───────────────────────────────────────────────────

def load_wissensfreund_slugs(repo_root: Path) -> set[str]:
    """
    Lädt alle bekannten Wissensfreund-Basis-Slugs (ohne _lN-Suffix).
    Quellen (absteigend vollständig):
      1. articles/*.json  → meta.id
      2. wissensfreund_topic_tree.json → featured_articles
    """
    slugs: set[str] = set()

    # Aus articles/
    articles_dir = repo_root / "articles"
    if articles_dir.is_dir():
        for f in articles_dir.glob("*.json"):
            base = re.sub(r"_l[123]$", "", f.stem)
            slugs.add(base)

    # Aus topic_tree featured_articles
    tree_path = repo_root / "wissensfreund_topic_tree.json"
    if tree_path.exists():
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        for topic in tree.get("topics", []):
            for sub in topic.get("subtopics", []):
                for slug_full in sub.get("featured_articles", []):
                    base = re.sub(r"_l[123]$", "", slug_full)
                    slugs.add(base)

    return slugs


# ─── Report ───────────────────────────────────────────────────────────────────

def print_report(entries: list[dict], wf_slugs: set[str]) -> None:
    q1 = [e for e in entries if e["quartil"] == 1]
    q2 = [e for e in entries if e["quartil"] == 2]

    print("=" * 65)
    print("KLEXIKON APPEAL QUARTIL — REPORT")
    print("=" * 65)
    print(f"  Q1 / high   (>5.000 Views 2022 + Top-10 2025): {len(q1):>4}")
    print(f"  Q2 / medium (1.000–5.000 Views 2022):           {len(q2):>4}")
    print(f"  null / kein Signal (nicht in 2022-Liste):        ~2.600+")
    print(f"  GESAMT mit Signal:                              {len(entries):>4}")
    print()

    # Quellen-Mix
    from collections import Counter
    quellen = Counter(e["quelle"] for e in entries)
    print("Quellen:")
    for q, n in sorted(quellen.items()):
        print(f"  {q:<45} {n:>4}")
    print()

    # Top-20 (Aliasse überspringen — nur kanonischen Slug zeigen)
    alias_slugs = set(SLUG_ALIASES.keys())
    q1_canon = [e for e in q1 if e["slug"] not in alias_slugs]
    print("TOP-20 (Q1, Top-10-2025 zuerst, dann alphabetisch; ohne Alias-Duplikate):")
    top10_entries = [e for e in q1_canon if "top10" in e["quelle"]]
    rest_q1       = [e for e in q1_canon if "top10" not in e["quelle"]]
    shown = top10_entries[:10] + rest_q1[:10]
    for i, e in enumerate(shown, 1):
        flag = "[TOP10]" if "top10" in e["quelle"] else "       "
        print(f"  {i:>2}. {flag} {e['klexikon_titel']:<35} {e['aufrufe_oder_rang']}")
    print()

    # Abgleich-Lücken
    if wf_slugs:
        print(f"Wissensfreund-Slugs bekannt: {len(wf_slugs)}")
        kl_slugs  = {e["slug"] for e in entries}
        in_kl_not_wf = kl_slugs - wf_slugs
        in_wf_not_kl = wf_slugs - kl_slugs
        print(f"  Klexikon-Signal, kein WF-Pendant:  {len(in_kl_not_wf):>3}")
        print(f"  WF-Slug, kein Klexikon-Signal:     {len(in_wf_not_kl):>3}")
        if in_kl_not_wf:
            sample = sorted(in_kl_not_wf)[:10]
            print(f"  Beispiele (Klexikon->kein WF): {sample}")
        if in_wf_not_kl:
            print(f"  ALLE WF->kein Klexikon-Signal ({len(in_wf_not_kl)}):")
            for s in sorted(in_wf_not_kl):
                print(f"    - {s}")
    else:
        print("Hinweis: Kein vollständiger Wissensfreund-Artikelindex vorhanden.")
        print("         Abgleich erst nach Pipeline-Lauf möglich.")
    print()

    # Plausibilitätsprüfung Top-10 2025 — slugs via to_slug() normiert
    kl_slugs = {e["slug"] for e in entries}
    expected_2025_titles = [
        "Erde", "Römisches Reich", "Deutschland", "Wolfgang Amadeus Mozart",
        "Hunde", "Europa", "Äquator", "Suchmaschine", "Katzen", "Organe",
    ]
    expected_slugs = {to_slug(t) for t in expected_2025_titles}
    gefunden = expected_slugs & kl_slugs
    fehlt    = expected_slugs - kl_slugs
    print(f"Plausibilitaets-Check Top-10 2025: {len(gefunden)}/10 Slugs im Mapping")
    if fehlt:
        print(f"  FEHLT im Mapping: {fehlt}")
    print("=" * 65)


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Klexikon Appeal Quartil — Mapping-Builder")
    p.add_argument("--out",      default="klexikon_appeal_quartil.json", type=Path)
    p.add_argument("--dry-run",  action="store_true", help="Nur Report, kein Schreiben")
    args = p.parse_args()

    repo_root = Path(__file__).parent.parent

    entries    = build_entries()
    wf_slugs   = load_wissensfreund_slugs(repo_root)

    print_report(entries, wf_slugs)

    if args.dry_run:
        print("DRY-RUN: Datei wird nicht geschrieben.")
        return

    out_path = repo_root / args.out
    out_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Geschrieben: {out_path}  ({len(entries)} Eintraege)")


if __name__ == "__main__":
    main()
