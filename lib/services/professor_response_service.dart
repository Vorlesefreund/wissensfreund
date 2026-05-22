import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class ProfessorResponseService {
  static final instance = ProfessorResponseService._();
  ProfessorResponseService._();

  Database? _db;
  Completer<void>? _initCompleter;

  Future<void> initialize() async {
    if (_db != null) return;
    if (_initCompleter != null) return _initCompleter!.future;
    _initCompleter = Completer<void>();
    try {
      final dir = await getApplicationDocumentsDirectory();
      final path = p.join(dir.path, 'professor_responses.db');
      _db = await openDatabase(path, version: 1, onCreate: _onCreate);
      _initCompleter!.complete();
    } catch (e) {
      debugPrint('ProfessorResponseService init error: $e');
      _initCompleter!.completeError(e);
      _initCompleter = null;
    }
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute('''
      CREATE TABLE professor_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        katalog_id TEXT NOT NULL,
        text TEXT NOT NULL,
        zuletzt_verwendet INTEGER NOT NULL DEFAULT 0
      )
    ''');
    final batch = db.batch();
    for (final e in _kEntries) {
      batch.insert('professor_responses', {
        'katalog_id': e.$1,
        'text': e.$2,
        'zuletzt_verwendet': 0,
      });
    }
    await batch.commit(noResult: true);
    debugPrint('ProfessorResponseService: seeded ${_kEntries.length} entries');
  }

  /// Random response from the catalog, avoiding the immediately last-used entry.
  Future<String> getResponse(String katalogId) async {
    try {
      await initialize();
    } catch (_) {
      return '';
    }
    final db = _db;
    if (db == null) return '';

    final lastUsed = await db.query(
      'professor_responses',
      columns: ['id'],
      where: 'katalog_id = ?',
      whereArgs: [katalogId],
      orderBy: 'zuletzt_verwendet DESC',
      limit: 1,
    );
    final lastId = lastUsed.isNotEmpty ? lastUsed.first['id'] as int : -1;

    var rows = await db.rawQuery(
      'SELECT id, text FROM professor_responses '
      'WHERE katalog_id = ? AND id != ? ORDER BY RANDOM() LIMIT 1',
      [katalogId, lastId],
    );
    if (rows.isEmpty) {
      rows = await db.rawQuery(
        'SELECT id, text FROM professor_responses '
        'WHERE katalog_id = ? ORDER BY RANDOM() LIMIT 1',
        [katalogId],
      );
    }
    if (rows.isEmpty) return '';

    final id   = rows.first['id']   as int;
    final text = rows.first['text'] as String;
    await db.update(
      'professor_responses',
      {'zuletzt_verwendet': DateTime.now().millisecondsSinceEpoch},
      where: 'id = ?',
      whereArgs: [id],
    );
    return text;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// All catalog entries — (katalog_id, text)
// ─────────────────────────────────────────────────────────────────────────────
const _kEntries = <(String, String)>[
  // ── K1 — Nicht verstanden (40) ────────────────────────────────────────────
  ('k1', 'Hmm, da war ich kurz abgelenkt — nochmal bitte!'),
  ('k1', 'Ich glaube der Wind hat deine Stimme weggeweht!'),
  ('k1', 'Ups! Kannst du das nochmal sagen?'),
  ('k1', 'Meine Ohren waren kurz woanders — nochmal!'),
  ('k1', 'Das habe ich leider nicht ganz gehört!'),
  ('k1', 'Oh! Ich war kurz in Gedanken — was hast du gesagt?'),
  ('k1', 'Kannst du etwas lauter sprechen? Ich höre schlecht heute!'),
  ('k1', 'Hm, ich glaube ich brauche neue Ohren!'),
  ('k1', 'Das war mir etwas zu leise — nochmal bitte!'),
  ('k1', 'Ich bin noch beim Lernen — kannst du es wiederholen?'),
  ('k1', 'Oh je, da habe ich was verpasst! Nochmal bitte!'),
  ('k1', 'Sprich nochmal — ich höre ganz genau hin!'),
  ('k1', 'Ich glaube meine Ohren schlafen noch — nochmal!'),
  ('k1', 'Das klang interessant! Kannst du es nochmal sagen?'),
  ('k1', 'Warte kurz — und jetzt nochmal bitte!'),
  ('k1', 'Ich war kurz beim Nachdenken — was meintest du?'),
  ('k1', 'Magst du das nochmal versuchen? Ich passe besser auf!'),
  ('k1', 'Hoppla! Das habe ich nicht ganz verstanden!'),
  ('k1', 'Sprich ruhig nochmal — ich bin ganz Ohr!'),
  ('k1', 'Hmm, da hat etwas nicht geklappt — nochmal!'),
  ('k1', 'Ich höre dir zu — kannst du es wiederholen?'),
  ('k1', 'Das war knapp! Noch ein Versuch bitte!'),
  ('k1', 'Kannst du mir das nochmal sagen? Ich bin gespannt!'),
  ('k1', 'Oh, da bin ich wohl kurz weg gewesen — nochmal!'),
  ('k1', 'Ich glaube ich muss besser aufpassen — nochmal bitte!'),
  ('k1', 'Deine Stimme war kurz weg — alles nochmal!'),
  ('k1', 'Mmh, das habe ich nicht ganz geschnappt!'),
  ('k1', 'Nochmal bitte — diesmal ganz deutlich!'),
  ('k1', 'Ich bin noch nicht so gut im Zuhören — nochmal!'),
  ('k1', 'Kannst du mir helfen? Ich habe das nicht verstanden!'),
  ('k1', 'Oh! Fast — aber nicht ganz! Nochmal bitte!'),
  ('k1', 'Sprich ruhig und deutlich — ich höre zu!'),
  ('k1', 'Das war schwierig für meine Ohren — nochmal!'),
  ('k1', 'Moment mal — und jetzt nochmal langsam bitte!'),
  ('k1', 'Ich glaube da hat etwas gefehlt — nochmal!'),
  ('k1', 'Hmm, kannst du das in anderen Worten sagen?'),
  ('k1', 'Das klang spannend — ich habe es aber nicht gehört!'),
  ('k1', 'Nochmal — ich verspreche diesmal besser aufzupassen!'),
  ('k1', 'Kannst du lauter sprechen? Ich bin etwas schwerhörig heute!'),
  ('k1', 'Oh je — da war ich kurz weg! Was hast du gesagt?'),

  // ── K2 — Kein Artikel gefunden (40) ──────────────────────────────────────
  ('k2', 'Hmm, dazu habe ich noch nichts gelernt — frag mal deine Eltern!'),
  ('k2', 'Oh, das ist neu für mich! Vielleicht wissen deine Eltern mehr?'),
  ('k2', 'Das kenne ich noch nicht — aber ich lerne jeden Tag dazu!'),
  ('k2', 'Interessant! Dazu fehlt mir noch Wissen — magst du etwas anderes hören?'),
  ('k2', 'Oh! Das steht noch nicht in meinen Büchern!'),
  ('k2', 'Hmm, da bin ich überfragt — deine Eltern wissen das bestimmt!'),
  ('k2', 'Das Thema kenne ich noch nicht — sollen wir etwas Ähnliches suchen?'),
  ('k2', 'Oh je, da muss ich noch lernen! Hast du eine andere Frage?'),
  ('k2', 'Das ist ein tolles Thema — ich kenne es leider noch nicht!'),
  ('k2', 'Hmm, dazu weiß ich nichts — aber schau mal bei deinen Eltern!'),
  ('k2', 'Das liegt außerhalb meines Wissens — magst du etwas anderes probieren?'),
  ('k2', 'Oh! Das ist mir neu — vielleicht kennen das deine Eltern?'),
  ('k2', 'Dazu habe ich leider keine Antwort — sollen wir etwas anderes entdecken?'),
  ('k2', 'Das weiß ich nicht — aber ich finde bestimmt etwas Ähnliches!'),
  ('k2', 'Hmm, da bin ich blank — frag mal deine Eltern!'),
  ('k2', 'Das Thema kenne ich noch nicht — magst du mich etwas anderes fragen?'),
  ('k2', 'Oh, das ist schwierig! Dazu weiß ich leider nichts.'),
  ('k2', 'Interessante Frage! Leider fehlt mir da das Wissen.'),
  ('k2', 'Das steht nicht in meinen Büchern — aber deine Eltern wissen das vielleicht!'),
  ('k2', 'Hmm, das ist außerhalb meiner Welt — magst du etwas anderes hören?'),
  ('k2', 'Oh! Dazu kann ich dir leider nichts sagen.'),
  ('k2', 'Das kenne ich nicht — sollen wir zusammen etwas anderes entdecken?'),
  ('k2', 'Da bin ich leider kein Experte — frag mal deine Eltern!'),
  ('k2', 'Hmm, das ist mir unbekannt — hast du noch eine andere Frage?'),
  ('k2', 'Oh je, dazu weiß ich nichts — aber vielleicht wissen deine Eltern mehr?'),
  ('k2', 'Das Thema liegt außerhalb meines Wissens — magst du etwas anderes probieren?'),
  ('k2', 'Interessant! Leider habe ich dazu keine Antwort.'),
  ('k2', 'Da muss ich passen — aber deine Eltern helfen dir bestimmt!'),
  ('k2', 'Oh, das kenne ich noch nicht! Magst du mich etwas anderes fragen?'),
  ('k2', 'Hmm, dazu bin ich noch nicht schlau genug — deine Eltern wissen das!'),
  ('k2', 'Das Thema kenne ich leider nicht — sollen wir etwas Ähnliches suchen?'),
  ('k2', 'Oh! Da bin ich überfragt — frag mal deine Eltern!'),
  ('k2', 'Dazu fehlt mir das Wissen — aber ich lerne noch!'),
  ('k2', 'Das kenne ich noch nicht — magst du mich etwas anderes fragen?'),
  ('k2', 'Hmm, da bin ich blank — vielleicht wissen deine Eltern mehr?'),
  ('k2', 'Oh je, das liegt außerhalb meiner Bücher!'),
  ('k2', 'Das ist eine tolle Frage — leider kenne ich die Antwort nicht!'),
  ('k2', 'Dazu weiß ich leider nichts — sollen wir etwas anderes entdecken?'),
  ('k2', 'Oh, das Thema kenne ich noch nicht! Deine Eltern helfen dir bestimmt!'),
  ('k2', 'Hmm, da muss ich noch lernen — magst du etwas anderes hören?'),

  // ── K3 S1 — 2. Fehlversuch (6) ───────────────────────────────────────────
  ('k3_s1', 'Das war knapp — ich versuche es nochmal besser!'),
  ('k3_s1', 'Hmm, da bin ich wohl nicht gut genug — nochmal bitte!'),
  ('k3_s1', 'Oh, das lag an mir — kannst du es nochmal versuchen?'),
  ('k3_s1', 'Ich lerne noch — nochmal bitte, ich schaffe das!'),
  ('k3_s1', 'Ups, das war mein Fehler — nochmal!'),
  ('k3_s1', 'Hmm, ich muss besser aufpassen — nochmal bitte!'),

  // ── K3 S2 — 3.–4. Fehlversuch (6) ────────────────────────────────────────
  ('k3_s2', 'Hmm, das ist schwierig für mich — magst du langsamer sprechen?'),
  ('k3_s2', 'Oh, ich höre dich — aber ich verstehe noch nicht ganz! Versuch es langsam!'),
  ('k3_s2', 'Das lag bestimmt an mir — sprich ruhig und deutlich nochmal!'),
  ('k3_s2', 'Hmm, ich versuche besser zu hören — nochmal bitte, langsam!'),
  ('k3_s2', 'Oh je, da bin ich noch nicht gut genug — sprich nochmal deutlich!'),
  ('k3_s2', 'Das war schwierig — magst du es nochmal langsam versuchen?'),

  // ── K3 S3 — 5. Fehlversuch (8) ───────────────────────────────────────────
  ('k3_s3', 'Oh je, das schaffe ich leider nicht — ich kenne dieses Wort noch nicht!'),
  ('k3_s3', 'Hmm, das liegt außerhalb meines Wissens — magst du etwas anderes probieren?'),
  ('k3_s3', 'Oh! Das kenne ich leider nicht — sollen wir etwas anderes entdecken?'),
  ('k3_s3', 'Das ist zu schwierig für mich — magst du deine Eltern fragen?'),
  ('k3_s3', 'Hmm, da muss ich passen — deine Eltern wissen das bestimmt!'),
  ('k3_s3', 'Oh je, das kenne ich wirklich nicht — magst du mich etwas anderes fragen?'),
  ('k3_s3', 'Das liegt außerhalb meiner Bücher — sollen wir etwas anderes versuchen?'),
  ('k3_s3', 'Hmm, da bin ich überfragt — deine Eltern helfen dir bestimmt!'),

  // ── K4 — Dasselbe Thema nochmal (25) ─────────────────────────────────────
  ('k4', 'Hmm, das kenne ich immer noch nicht — sollen wir etwas Ähnliches suchen?'),
  ('k4', 'Oh, dazu weiß ich leider immer noch nichts — frag mal deine Eltern!'),
  ('k4', 'Das Thema kenne ich wirklich nicht — magst du etwas anderes probieren?'),
  ('k4', 'Ich höre dich — aber dazu habe ich leider keine Antwort!'),
  ('k4', 'Hmm, da bin ich immer noch blank — deine Eltern wissen das bestimmt!'),
  ('k4', 'Das kenne ich wirklich nicht — sollen wir zusammen etwas anderes entdecken?'),
  ('k4', 'Oh je, dazu kann ich dir wirklich nicht helfen — frag deine Eltern!'),
  ('k4', 'Das liegt außerhalb meines Wissens — magst du mich etwas anderes fragen?'),
  ('k4', 'Ich verstehe dich — aber dazu fehlt mir das Wissen!'),
  ('k4', 'Hmm, das ist wirklich schwierig für mich — deine Eltern helfen dir!'),
  ('k4', 'Oh, dazu weiß ich immer noch nichts — sollen wir etwas anderes versuchen?'),
  ('k4', 'Das Thema kenne ich leider nicht — magst du etwas anderes hören?'),
  ('k4', 'Ich höre dich gut — aber dazu kann ich nichts sagen!'),
  ('k4', 'Hmm, da bin ich wirklich überfragt — frag mal deine Eltern!'),
  ('k4', 'Das kenne ich nicht — aber ich kenne viele andere tolle Themen!'),
  ('k4', 'Oh, das ist schwierig für mich — magst du mich eine andere Frage stellen?'),
  ('k4', 'Dazu fehlt mir das Wissen — sollen wir etwas Ähnliches suchen?'),
  ('k4', 'Ich verstehe dass du das wissen möchtest — frag mal deine Eltern!'),
  ('k4', 'Hmm, das liegt wirklich außerhalb meiner Bücher!'),
  ('k4', 'Oh je, da kann ich dir nicht helfen — deine Eltern bestimmt schon!'),
  ('k4', 'Das Thema kenne ich nicht — aber viele andere tolle Dinge!'),
  ('k4', 'Ich höre dich — aber da muss ich wirklich passen!'),
  ('k4', 'Hmm, dazu weiß ich nichts — magst du etwas anderes probieren?'),
  ('k4', 'Oh, das ist mir wirklich unbekannt — frag mal deine Eltern!'),
  ('k4', 'Dazu kann ich nichts sagen — aber ich bin für andere Fragen da!'),

  // ── K5 S1 — 1. technisches Problem (7) ───────────────────────────────────
  ('k5_s1', 'Ups, das hat nicht geklappt — magst du es nochmal versuchen?'),
  ('k5_s1', 'Oh! Da ist etwas schiefgelaufen — nochmal bitte!'),
  ('k5_s1', 'Hmm, das war seltsam — kannst du es nochmal probieren?'),
  ('k5_s1', 'Ups! Da hat etwas nicht funktioniert — nochmal versuchen?'),
  ('k5_s1', 'Oh je, das war nicht so geplant — nochmal bitte!'),
  ('k5_s1', 'Hmm, da ist etwas durcheinandergeraten — nochmal!'),
  ('k5_s1', 'Ups, das klappt gerade nicht so gut — nochmal versuchen?'),

  // ── K5 S2 — 2. technisches Problem (7) ───────────────────────────────────
  ('k5_s2', 'Hmm, das klappt immer noch nicht — magst du das Mikrofon antippen?'),
  ('k5_s2', 'Oh, da stimmt etwas nicht — versuch mal das Mikrofon nochmal anzutippen!'),
  ('k5_s2', 'Ups, das funktioniert immer noch nicht — tippe nochmal auf das Mikrofon!'),
  ('k5_s2', 'Hmm, da ist etwas nicht richtig — magst du nochmal von vorne anfangen?'),
  ('k5_s2', 'Oh je, das klappt nicht — tippe auf das Mikrofon und versuch es nochmal!'),
  ('k5_s2', 'Ups! Immer noch nicht — magst du kurz warten und es nochmal versuchen?'),
  ('k5_s2', 'Hmm, das ist seltsam — tippe nochmal auf das Mikrofon bitte!'),

  // ── K5 S3 — 3. technisches Problem (6) ───────────────────────────────────
  ('k5_s3', 'Oh je, das klappt wirklich nicht — hol bitte deine Eltern!'),
  ('k5_s3', 'Hmm, da brauchen wir Hilfe — deine Eltern wissen was zu tun ist!'),
  ('k5_s3', 'Ups, das schaffen wir alleine nicht — hol bitte deine Eltern!'),
  ('k5_s3', 'Oh! Da stimmt etwas nicht — deine Eltern helfen uns bestimmt!'),
  ('k5_s3', 'Hmm, das ist zu schwierig für mich alleine — hol deine Eltern bitte!'),
  ('k5_s3', 'Oh je, da brauchen wir deine Eltern — die wissen was zu tun ist!'),

  // ── K6 S1 — 30 Sekunden Stille (5) ───────────────────────────────────────
  ('k6_s1', 'Ich bin noch da — nimmst du dir Zeit zum Nachdenken?'),
  ('k6_s1', 'Kein Stress — ich warte gerne!'),
  ('k6_s1', 'Oh, schaust du dir das Bild an? Das ist schön, oder?'),
  ('k6_s1', 'Ich bin noch hier — magst du weitermachen?'),
  ('k6_s1', 'Keine Eile — ich bin da wenn du bereit bist!'),

  // ── K6 S2 — weitere 60 Sekunden (7) ──────────────────────────────────────
  ('k6_s2', 'Hmm, hast du eine Frage für mich?'),
  ('k6_s2', 'Ich bin noch hier — magst du mich etwas fragen?'),
  ('k6_s2', 'Denkst du gerade nach? Das ist prima — ich warte!'),
  ('k6_s2', 'Magst du etwas anderes hören? Ich habe noch viele Geschichten!'),
  ('k6_s2', 'Ich bin geduldig — aber ich freue mich auf deine nächste Frage!'),
  ('k6_s2', 'Oh, soll ich dir etwas vorschlagen? Ich kenne viele tolle Themen!'),
  ('k6_s2', 'Hmm, magst du etwas über Tiere hören? Oder lieber Weltall?'),

  // ── K6 S3 — weitere 90 Sekunden (5) ──────────────────────────────────────
  ('k6_s3', 'Ich glaube du brauchst gerade eine Pause — das ist völlig okay!'),
  ('k6_s3', 'Hmm, ich mache gleich ein kleines Nickerchen — tippe mich an wenn du weitermachen möchtest!'),
  ('k6_s3', 'Oh, ich glaube du bist gerade woanders — tippe einfach auf mich wenn du zurück bist!'),
  ('k6_s3', 'Ich warte auf dich — tippe mich einfach an wenn du weitermachen möchtest!'),
  ('k6_s3', 'Hmm, ich ruhe mich kurz aus — du weißt wo du mich findest!'),

  // ── K6 Wake — Aufwachen aus Ruhemodus (5) ────────────────────────────────
  ('k6_wake', 'Oh, da bist du ja wieder — schön!'),
  ('k6_wake', 'Hmm, guten Morgen! Was möchtest du wissen?'),
  ('k6_wake', 'Oh! Ich war kurz weg — was habe ich verpasst?'),
  ('k6_wake', 'Da bist du ja! Ich freue mich — was entdecken wir jetzt?'),
  ('k6_wake', 'Oh, du bist zurück! Ich habe auf dich gewartet!'),

  // ── K7 — Danke / Lob (20) ────────────────────────────────────────────────
  ('k7', 'Das freut mich sehr — magst du noch mehr erfahren?'),
  ('k7', 'Oh, wie schön! Was möchtest du als nächstes wissen?'),
  ('k7', 'Danke! Du stellst tolle Fragen!'),
  ('k7', 'Das macht mich glücklich — was entdecken wir als nächstes?'),
  ('k7', 'Oh wie toll! Du lernst so schnell!'),
  ('k7', 'Danke — das höre ich gerne! Was kommt als nächstes?'),
  ('k7', 'Das freut mich! Ich erkläre dir gerne noch mehr!'),
  ('k7', 'Oh, das ist nett! Hast du noch eine Frage?'),
  ('k7', 'Danke! Wollen wir noch mehr entdecken?'),
  ('k7', 'Das macht mich froh — was interessiert dich noch?'),
  ('k7', 'Oh wie schön! Du bist ein toller Entdecker!'),
  ('k7', 'Danke! Ich erkläre gerne — hast du noch eine Frage?'),
  ('k7', 'Das freut mich sehr! Was möchtest du noch wissen?'),
  ('k7', 'Oh! Das höre ich gerne — wollen wir weitermachen?'),
  ('k7', 'Danke! Du machst das wirklich toll!'),
  ('k7', 'Das ist nett — was entdecken wir als nächstes?'),
  ('k7', 'Oh wie schön! Ich bin gerne dein Wissensfreund!'),
  ('k7', 'Danke! Hast du noch eine tolle Frage für mich?'),
  ('k7', 'Das freut mich — wollen wir noch mehr lernen?'),
  ('k7', 'Oh! Das macht mich glücklich — was kommt als nächstes?'),

  // ── K8 — Tschüss (15) ────────────────────────────────────────────────────
  ('k8', 'Tschüss! Bis zum nächsten Mal — ich freue mich schon!'),
  ('k8', 'Auf Wiedersehen! Du hast heute viel gelernt!'),
  ('k8', 'Tschüss! Komm bald wieder — ich warte auf dich!'),
  ('k8', 'Auf Wiedersehen! Das war toll heute!'),
  ('k8', 'Tschüss! Denk mal an alles was wir heute entdeckt haben!'),
  ('k8', 'Bis bald! Ich habe noch viele Geschichten für dich!'),
  ('k8', 'Auf Wiedersehen! Du warst ein toller Entdecker heute!'),
  ('k8', 'Tschüss! Komm morgen wieder — ich bin immer da!'),
  ('k8', 'Bis zum nächsten Mal! Das hat Spaß gemacht!'),
  ('k8', 'Auf Wiedersehen! Ich freue mich auf deine nächste Frage!'),
  ('k8', 'Tschüss! Schlaf gut und komm bald wieder!'),
  ('k8', 'Bis bald! Du hast heute so viel gelernt!'),
  ('k8', 'Auf Wiedersehen! Ich warte schon auf dich!'),
  ('k8', 'Tschüss! Das war ein toller Tag heute!'),
  ('k8', 'Bis zum nächsten Mal — ich bin immer für dich da!'),
];
