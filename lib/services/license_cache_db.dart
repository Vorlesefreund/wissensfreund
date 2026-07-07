import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

import '../models/collected_card.dart';
import '../models/trophy.dart';
import 'profile_service.dart';
import 'reward_rules.dart';

class LicenseEntry {
  final String imageFilename;
  final String? urheber;
  final String? lizenz;
  final String? lizenzUrl;
  final bool erlaubt;
  final DateTime checkedAt;

  const LicenseEntry({
    required this.imageFilename,
    this.urheber,
    this.lizenz,
    this.lizenzUrl,
    required this.erlaubt,
    required this.checkedAt,
  });
}

class AudioLicenseEntry {
  final String audioFilename;
  final String? urheber;
  final String? lizenz;
  final String? lizenzUrl;
  final String? caption;
  final bool erlaubt;
  final DateTime checkedAt;

  const AudioLicenseEntry({
    required this.audioFilename,
    this.urheber,
    this.lizenz,
    this.lizenzUrl,
    this.caption,
    required this.erlaubt,
    required this.checkedAt,
  });
}

class LicenseCacheDb {
  LicenseCacheDb._();
  static final LicenseCacheDb instance = LicenseCacheDb._();

  Database? _db;

  Future<Database> get _database async {
    _db ??= await _open();
    return _db!;
  }

  Future<Database> _open() async {
    final dbPath = join(await getDatabasesPath(), 'license_cache.db');
    return openDatabase(
      dbPath,
      version: 10,
      onCreate: (db, _) async {
        await db.execute('''
          CREATE TABLE license_cache (
            image_filename TEXT PRIMARY KEY,
            urheber        TEXT,
            lizenz         TEXT,
            lizenz_url     TEXT,
            erlaubt        INTEGER NOT NULL,
            checked_at     INTEGER NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE audio_cache (
            audio_filename TEXT PRIMARY KEY,
            urheber        TEXT,
            lizenz         TEXT,
            lizenz_url     TEXT,
            caption        TEXT,
            erlaubt        INTEGER NOT NULL,
            checked_at     INTEGER NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE sync_info (
            id          INTEGER PRIMARY KEY,
            sync_date   TEXT NOT NULL,
            zim_version TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE image_cache_index (
            filename      TEXT PRIMARY KEY,
            local_path    TEXT NOT NULL,
            last_accessed INTEGER NOT NULL,
            file_size     INTEGER NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE data_usage (
            date             TEXT NOT NULL,
            connection_type  TEXT NOT NULL,
            bytes_used       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, connection_type)
          )
        ''');
        await db.execute('''
          CREATE TABLE question_usage (
            month TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
          )
        ''');
        await db.execute('''
          CREATE TABLE usage_stats (
            date              TEXT PRIMARY KEY,
            articles_listened INTEGER NOT NULL DEFAULT 0,
            questions_asked   INTEGER NOT NULL DEFAULT 0,
            session_minutes   INTEGER NOT NULL DEFAULT 0
          )
        ''');
        await _createProfileTables(db);
        await _createRewardTables(db);
        await _createCardTables(db);
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          await db.execute('''
            CREATE TABLE IF NOT EXISTS sync_info (
              id          INTEGER PRIMARY KEY,
              sync_date   TEXT NOT NULL,
              zim_version TEXT NOT NULL
            )
          ''');
        }
        if (oldVersion < 3) {
          await db.execute('''
            CREATE TABLE IF NOT EXISTS audio_cache (
              audio_filename TEXT PRIMARY KEY,
              urheber        TEXT,
              lizenz         TEXT,
              lizenz_url     TEXT,
              caption        TEXT,
              erlaubt        INTEGER NOT NULL,
              checked_at     INTEGER NOT NULL
            )
          ''');
        }
        if (oldVersion < 4) {
          await db.execute('''
            CREATE TABLE IF NOT EXISTS image_cache_index (
              filename      TEXT PRIMARY KEY,
              local_path    TEXT NOT NULL,
              last_accessed INTEGER NOT NULL,
              file_size     INTEGER NOT NULL
            )
          ''');
        }
        if (oldVersion < 5) {
          await db.execute('''
            CREATE TABLE IF NOT EXISTS data_usage (
              date             TEXT NOT NULL,
              connection_type  TEXT NOT NULL,
              bytes_used       INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (date, connection_type)
            )
          ''');
        }
        if (oldVersion < 6) {
          await db.execute('''
            CREATE TABLE IF NOT EXISTS question_usage (
              month TEXT PRIMARY KEY,
              count INTEGER NOT NULL DEFAULT 0
            )
          ''');
          await db.execute('''
            CREATE TABLE IF NOT EXISTS usage_stats (
              date              TEXT PRIMARY KEY,
              articles_listened INTEGER NOT NULL DEFAULT 0,
              questions_asked   INTEGER NOT NULL DEFAULT 0,
              session_minutes   INTEGER NOT NULL DEFAULT 0
            )
          ''');
        }
        if (oldVersion < 7) {
          await _createProfileTables(db);
        }
        if (oldVersion < 8) {
          try {
            await db.execute(
              'ALTER TABLE profiles ADD COLUMN age_level INTEGER NOT NULL DEFAULT 2',
            );
          } on DatabaseException catch (_) {
            // Column already present — created by _createProfileTables in v7 migration
          }
        }
        if (oldVersion < 9) {
          await _createRewardTables(db);
        }
        if (oldVersion < 10) {
          await _createCardTables(db);
        }
      },
    );
  }

  // ── Images ─────────────────────────────────────────────────────────────────

  Future<LicenseEntry?> get(String imageFilename) async {
    final rows = await (await _database).query(
      'license_cache',
      where: 'image_filename = ?',
      whereArgs: [imageFilename],
    );
    if (rows.isEmpty) return null;
    final r = rows.first;
    return LicenseEntry(
      imageFilename: r['image_filename'] as String,
      urheber: r['urheber'] as String?,
      lizenz: r['lizenz'] as String?,
      lizenzUrl: r['lizenz_url'] as String?,
      erlaubt: (r['erlaubt'] as int) == 1,
      checkedAt: DateTime.fromMillisecondsSinceEpoch(r['checked_at'] as int),
    );
  }

  Future<void> put(LicenseEntry entry) async {
    await (await _database).insert('license_cache', _imageToMap(entry),
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> putBatch(List<LicenseEntry> entries) async {
    final db = await _database;
    final batch = db.batch();
    for (final e in entries) {
      batch.insert('license_cache', _imageToMap(e),
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  // ── Audio ───────────────────────────────────────────────────────────────────

  Future<AudioLicenseEntry?> getAudio(String audioFilename) async {
    final rows = await (await _database).query(
      'audio_cache',
      where: 'audio_filename = ?',
      whereArgs: [audioFilename],
    );
    if (rows.isEmpty) return null;
    final r = rows.first;
    return AudioLicenseEntry(
      audioFilename: r['audio_filename'] as String,
      urheber: r['urheber'] as String?,
      lizenz: r['lizenz'] as String?,
      lizenzUrl: r['lizenz_url'] as String?,
      caption: r['caption'] as String?,
      erlaubt: (r['erlaubt'] as int) == 1,
      checkedAt: DateTime.fromMillisecondsSinceEpoch(r['checked_at'] as int),
    );
  }

  Future<void> putBatchAudio(List<AudioLicenseEntry> entries) async {
    final db = await _database;
    final batch = db.batch();
    for (final e in entries) {
      batch.insert('audio_cache', _audioToMap(e),
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  // ── Sync info ───────────────────────────────────────────────────────────────

  Future<bool> isSynced() async {
    final rows = await (await _database).query('sync_info', limit: 1);
    return rows.isNotEmpty;
  }

  Future<void> saveLastSync(String syncDate, String zimVersion) async {
    final db = await _database;
    await db.delete('sync_info');
    await db.insert('sync_info', {
      'id': 1,
      'sync_date': syncDate,
      'zim_version': zimVersion,
    });
  }

  // ── Image cache index ────────────────────────────────────────────────────────

  Future<void> upsertImageCache({
    required String filename,
    required String localPath,
    required int fileSize,
  }) async {
    await (await _database).insert(
      'image_cache_index',
      {
        'filename':      filename,
        'local_path':    localPath,
        'last_accessed': DateTime.now().millisecondsSinceEpoch,
        'file_size':     fileSize,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> touchImageCache(String filename) async {
    await (await _database).update(
      'image_cache_index',
      {'last_accessed': DateTime.now().millisecondsSinceEpoch},
      where: 'filename = ?',
      whereArgs: [filename],
    );
  }

  Future<int> imageCacheTotalBytes() async {
    final result = await (await _database)
        .rawQuery('SELECT SUM(file_size) as total FROM image_cache_index');
    return (result.first['total'] as int?) ?? 0;
  }

  Future<void> clearImageCacheIndex() async {
    await (await _database).delete('image_cache_index');
  }

  // ── ZIM version ─────────────────────────────────────────────────────────────

  Future<String?> getStoredZimVersion() async {
    final rows = await (await _database).query('sync_info', limit: 1);
    if (rows.isEmpty) return null;
    return rows.first['zim_version'] as String?;
  }

  // ── Data usage ───────────────────────────────────────────────────────────────

  Future<void> recordDataUsage({
    required String date,
    required String connectionType,
    required int bytes,
  }) async {
    final db = await _database;
    await db.rawInsert('''
      INSERT INTO data_usage (date, connection_type, bytes_used) VALUES (?, ?, ?)
      ON CONFLICT(date, connection_type) DO UPDATE SET bytes_used = bytes_used + excluded.bytes_used
    ''', [date, connectionType, bytes]);
  }

  Future<int> getDailyUsage(String date, String connectionType) async {
    final rows = await (await _database).query(
      'data_usage',
      columns: ['bytes_used'],
      where: 'date = ? AND connection_type = ?',
      whereArgs: [date, connectionType],
    );
    if (rows.isEmpty) return 0;
    return (rows.first['bytes_used'] as int?) ?? 0;
  }

  Future<int> getMonthlyUsage(String monthPrefix, String connectionType) async {
    final result = await (await _database).rawQuery(
      'SELECT SUM(bytes_used) as total FROM data_usage '
      "WHERE date LIKE ? AND connection_type = ?",
      ['$monthPrefix%', connectionType],
    );
    return (result.first['total'] as int?) ?? 0;
  }

  // ── Question usage (Premium monthly limit) ───────────────────────────────────

  Future<int> getQuestionCount(String month) async {
    final rows = await (await _database).query(
      'question_usage',
      columns: ['count'],
      where: 'month = ?',
      whereArgs: [month],
    );
    if (rows.isEmpty) return 0;
    return (rows.first['count'] as int?) ?? 0;
  }

  Future<void> incrementQuestionCount(String month) async {
    await (await _database).rawInsert('''
      INSERT INTO question_usage (month, count) VALUES (?, 1)
      ON CONFLICT(month) DO UPDATE SET count = count + 1
    ''', [month]);
  }

  // ── Usage statistics (Premium dashboard) ─────────────────────────────────────

  Future<void> recordArticleListened(String date) async {
    await (await _database).rawInsert('''
      INSERT INTO usage_stats (date, articles_listened) VALUES (?, 1)
      ON CONFLICT(date) DO UPDATE SET articles_listened = articles_listened + 1
    ''', [date]);
  }

  Future<void> recordQuestionAsked(String date) async {
    await (await _database).rawInsert('''
      INSERT INTO usage_stats (date, questions_asked) VALUES (?, 1)
      ON CONFLICT(date) DO UPDATE SET questions_asked = questions_asked + 1
    ''', [date]);
  }

  Future<void> addSessionMinutes(String date, int minutes) async {
    if (minutes <= 0) return;
    await (await _database).rawInsert('''
      INSERT INTO usage_stats (date, session_minutes) VALUES (?, ?)
      ON CONFLICT(date) DO UPDATE SET session_minutes = session_minutes + ?
    ''', [date, minutes, minutes]);
  }

  /// Returns stats for the past [days] days, most recent first.
  Future<List<Map<String, dynamic>>> getRecentStats(int days) async {
    final cutoff = DateTime.now().subtract(Duration(days: days));
    final cutoffStr = cutoff.toIso8601String().substring(0, 10);
    return (await _database).query(
      'usage_stats',
      where: 'date >= ?',
      whereArgs: [cutoffStr],
      orderBy: 'date DESC',
    );
  }

  // ── Profile tables (v7) ──────────────────────────────────────────────────────

  static Future<void> _createProfileTables(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS profiles (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        name           TEXT NOT NULL,
        birth_year     INTEGER NOT NULL,
        avatar_id      TEXT NOT NULL,
        language_level TEXT NOT NULL,
        age_level      INTEGER NOT NULL DEFAULT 2,
        created_at     TEXT,
        last_used_at   TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS article_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id    INTEGER NOT NULL,
        article_title TEXT NOT NULL,
        opened_at     TEXT NOT NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute(
      'CREATE INDEX IF NOT EXISTS idx_history_profile ON article_history(profile_id, opened_at DESC)',
    );
    await db.execute('''
      CREATE TABLE IF NOT EXISTS favorites (
        profile_id    INTEGER NOT NULL,
        article_title TEXT NOT NULL,
        added_at      TEXT NOT NULL,
        PRIMARY KEY (profile_id, article_title),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
  }

  // ── Reward tables (v9) ────────────────────────────────────────────────────────
  //
  // All profile-scoped. Spendable ⭐ live in reward_wallet.stars; total_earned is
  // lifetime (never decremented — for prestige/stats). reward_ledger is the
  // append-only audit that drives the daily cap and milestone counting.

  static Future<void> _createRewardTables(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS reward_wallet (
        profile_id   INTEGER PRIMARY KEY,
        stars        INTEGER NOT NULL DEFAULT 0,
        total_earned INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT NOT NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS reward_ledger (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        day        TEXT NOT NULL,
        amount     INTEGER NOT NULL,
        reason     TEXT NOT NULL,
        ref        TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute(
      'CREATE INDEX IF NOT EXISTS idx_ledger_profile_day ON reward_ledger(profile_id, day)',
    );
    await db.execute('''
      CREATE TABLE IF NOT EXISTS quiz_answer_progress (
        profile_id       INTEGER NOT NULL,
        article_id       TEXT NOT NULL,
        question_id      TEXT NOT NULL,
        first_correct_at TEXT NOT NULL,
        PRIMARY KEY (profile_id, article_id, question_id),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS quiz_completions (
        profile_id   INTEGER NOT NULL,
        article_id   TEXT NOT NULL,
        topic_area   TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        all_correct  INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (profile_id, article_id),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS discovered_areas (
        profile_id    INTEGER NOT NULL,
        topic_area    TEXT NOT NULL,
        discovered_at TEXT NOT NULL,
        PRIMARY KEY (profile_id, topic_area),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS area_stats (
        profile_id        INTEGER NOT NULL,
        topic_area        TEXT NOT NULL,
        quizzes_passed    INTEGER NOT NULL DEFAULT 0,
        questions_correct INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (profile_id, topic_area),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS daily_activity (
        profile_id         INTEGER NOT NULL,
        day                TEXT NOT NULL,
        quizzes_passed     INTEGER NOT NULL DEFAULT 0,
        milestone1_awarded INTEGER NOT NULL DEFAULT 0,
        milestone2_awarded INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (profile_id, day),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
  }

  // ── Card tables (v10) ─────────────────────────────────────────────────────────
  //
  // One row per (profile, topic). card_id is the topic base id ("biene"), so the
  // same card is never earned twice across levels. Content is snapshotted at earn
  // time so the album works offline.

  static Future<void> _createCardTables(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS collected_cards (
        profile_id  INTEGER NOT NULL,
        card_id     TEXT NOT NULL,
        article_id  TEXT NOT NULL,
        title       TEXT NOT NULL,
        emoji       TEXT NOT NULL DEFAULT '',
        theme_color TEXT NOT NULL DEFAULT '#4caf50',
        thumb_url   TEXT NOT NULL DEFAULT '',
        fact        TEXT NOT NULL DEFAULT '',
        earned_at   TEXT NOT NULL,
        PRIMARY KEY (profile_id, card_id),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
      )
    ''');
  }

  // ── Card reads ────────────────────────────────────────────────────────────────

  Future<List<CollectedCard>> getCollectedCards(int profileId) async {
    final rows = await (await _database).query(
      'collected_cards',
      where: 'profile_id = ?',
      whereArgs: [profileId],
      orderBy: 'earned_at DESC',
    );
    return rows.map(CollectedCard.fromMap).toList();
  }

  Future<Set<String>> getCollectedCardIds(int profileId) async {
    final rows = await (await _database).query(
      'collected_cards',
      columns: ['card_id'],
      where: 'profile_id = ?',
      whereArgs: [profileId],
    );
    return rows.map((r) => r['card_id'] as String).toSet();
  }

  // ── Trophy reads (derived from area_stats) ────────────────────────────────────

  Future<List<AreaStat>> getAreaStats(int profileId) async {
    final rows = await (await _database).query(
      'area_stats',
      where: 'profile_id = ?',
      whereArgs: [profileId],
      orderBy: 'quizzes_passed DESC, questions_correct DESC',
    );
    return rows
        .map((r) => AreaStat(
              area: r['topic_area'] as String? ?? '',
              quizzesPassed: r['quizzes_passed'] as int? ?? 0,
              questionsCorrect: r['questions_correct'] as int? ?? 0,
            ))
        .toList();
  }

  // ── Reward reads ──────────────────────────────────────────────────────────────

  Future<int> getStars(int profileId) async {
    final rows = await (await _database).query(
      'reward_wallet',
      columns: ['stars'],
      where: 'profile_id = ?',
      whereArgs: [profileId],
      limit: 1,
    );
    if (rows.isEmpty) return 0;
    return (rows.first['stars'] as int?) ?? 0;
  }

  // ── Reward writes (transactional) ─────────────────────────────────────────────

  /// Grants ⭐ for a first-time-correct question + the "neues Themengebiet" bonus.
  /// Returns a reason→stars map of what was actually granted (empty on re-take).
  Future<Map<String, int>> awardForCorrectAnswer({
    required int profileId,
    required String articleId,
    required String questionId,
    required String topicArea,
  }) async {
    final db = await _database;
    final nowIso = DateTime.now().toIso8601String();
    final day = nowIso.substring(0, 10);
    final result = <String, int>{};

    await db.transaction((txn) async {
      final existed = await txn.query(
        'quiz_answer_progress',
        where: 'profile_id = ? AND article_id = ? AND question_id = ?',
        whereArgs: [profileId, articleId, questionId],
        limit: 1,
      );
      if (existed.isNotEmpty) return; // already rewarded this question, ever

      await txn.insert('quiz_answer_progress', {
        'profile_id': profileId,
        'article_id': articleId,
        'question_id': questionId,
        'first_correct_at': nowIso,
      });

      if (topicArea.isNotEmpty) {
        await txn.rawInsert('''
          INSERT INTO area_stats (profile_id, topic_area, questions_correct, quizzes_passed)
          VALUES (?, ?, 1, 0)
          ON CONFLICT(profile_id, topic_area) DO UPDATE SET questions_correct = questions_correct + 1
        ''', [profileId, topicArea]);
      }

      var earned = await _earnedToday(txn, profileId, day);

      final gQ = _grant(RewardRules.starsPerCorrectQuestion, earned);
      if (gQ > 0) {
        await _ledger(txn, profileId, day, gQ, 'question', articleId, nowIso);
        earned += gQ;
        result['question'] = gQ;
      }

      if (topicArea.isNotEmpty) {
        final known = await txn.query(
          'discovered_areas',
          where: 'profile_id = ? AND topic_area = ?',
          whereArgs: [profileId, topicArea],
          limit: 1,
        );
        if (known.isEmpty) {
          await txn.insert('discovered_areas', {
            'profile_id': profileId,
            'topic_area': topicArea,
            'discovered_at': nowIso,
          });
          final gA = _grant(RewardRules.starsNewArea, earned);
          if (gA > 0) {
            await _ledger(txn, profileId, day, gA, 'new_area', topicArea, nowIso);
            earned += gA;
            result['new_area'] = gA;
          }
        }
      }

      await _applyWallet(txn, profileId, result, nowIso);
    });

    return result;
  }

  /// Grants the all-correct completion bonus (once per article) + daily
  /// milestones. [allCorrect] = every question right in this run.
  Future<({Map<String, int> stars, bool cardEarned})> awardForQuizFinish({
    required int profileId,
    required String articleId,
    required String topicArea,
    required bool allCorrect,
    CollectedCard? card,
  }) async {
    final db = await _database;
    final nowIso = DateTime.now().toIso8601String();
    final day = nowIso.substring(0, 10);
    final result = <String, int>{};
    var cardEarned = false;

    await db.transaction((txn) async {
      final rows = await txn.query(
        'quiz_completions',
        where: 'profile_id = ? AND article_id = ?',
        whereArgs: [profileId, articleId],
        limit: 1,
      );
      final firstCompletion = rows.isEmpty;
      final prevAllCorrect =
          rows.isNotEmpty && (rows.first['all_correct'] as int? ?? 0) == 1;

      if (firstCompletion) {
        await txn.insert('quiz_completions', {
          'profile_id': profileId,
          'article_id': articleId,
          'topic_area': topicArea,
          'completed_at': nowIso,
          'all_correct': allCorrect ? 1 : 0,
        });
      } else if (allCorrect && !prevAllCorrect) {
        await txn.update(
          'quiz_completions',
          {'all_correct': 1, 'completed_at': nowIso},
          where: 'profile_id = ? AND article_id = ?',
          whereArgs: [profileId, articleId],
        );
      }

      // A "new all-correct pass" = first time this article is fully solved.
      final newAllCorrectPass = allCorrect && (firstCompletion || !prevAllCorrect);
      if (!newAllCorrectPass) return;

      // Sammelkarte: one per topic (card_id = base id), snapshotted at earn time.
      if (card != null && card.cardId.isNotEmpty) {
        final existing = await txn.query(
          'collected_cards',
          where: 'profile_id = ? AND card_id = ?',
          whereArgs: [profileId, card.cardId],
          limit: 1,
        );
        if (existing.isEmpty) {
          await txn.insert('collected_cards', card.toMap(profileId, nowIso));
          cardEarned = true;
        }
      }

      if (topicArea.isNotEmpty) {
        await txn.rawInsert('''
          INSERT INTO area_stats (profile_id, topic_area, questions_correct, quizzes_passed)
          VALUES (?, ?, 0, 1)
          ON CONFLICT(profile_id, topic_area) DO UPDATE SET quizzes_passed = quizzes_passed + 1
        ''', [profileId, topicArea]);
      }

      var earned = await _earnedToday(txn, profileId, day);

      final gB = _grant(RewardRules.starsQuizAllCorrectBonus, earned);
      if (gB > 0) {
        await _ledger(txn, profileId, day, gB, 'quiz_complete', articleId, nowIso);
        earned += gB;
        result['quiz_complete'] = gB;
      }

      // Daily milestones: count all-correct passes today.
      await txn.rawInsert('''
        INSERT INTO daily_activity (profile_id, day, quizzes_passed, milestone1_awarded, milestone2_awarded)
        VALUES (?, ?, 1, 0, 0)
        ON CONFLICT(profile_id, day) DO UPDATE SET quizzes_passed = quizzes_passed + 1
      ''', [profileId, day]);

      final act = (await txn.query(
        'daily_activity',
        where: 'profile_id = ? AND day = ?',
        whereArgs: [profileId, day],
        limit: 1,
      )).first;
      final passed = act['quizzes_passed'] as int? ?? 0;
      final m1done = (act['milestone1_awarded'] as int? ?? 0) == 1;
      final m2done = (act['milestone2_awarded'] as int? ?? 0) == 1;

      if (!m1done && passed >= RewardRules.dailyMilestone1Count) {
        await txn.update('daily_activity', {'milestone1_awarded': 1},
            where: 'profile_id = ? AND day = ?', whereArgs: [profileId, day]);
        final g = _grant(RewardRules.starsDailyMilestone1, earned);
        if (g > 0) {
          await _ledger(txn, profileId, day, g, 'daily_5', null, nowIso);
          earned += g;
          result['daily_5'] = g;
        }
      }
      if (!m2done && passed >= RewardRules.dailyMilestone2Count) {
        await txn.update('daily_activity', {'milestone2_awarded': 1},
            where: 'profile_id = ? AND day = ?', whereArgs: [profileId, day]);
        final g = _grant(RewardRules.starsDailyMilestone2, earned);
        if (g > 0) {
          await _ledger(txn, profileId, day, g, 'daily_10', null, nowIso);
          earned += g;
          result['daily_10'] = g;
        }
      }

      await _applyWallet(txn, profileId, result, nowIso);
    });

    return (stars: result, cardEarned: cardEarned);
  }

  // ── Reward helpers ────────────────────────────────────────────────────────────

  /// Caps a grant against the remaining daily allowance ([RewardRules.dailyCapStars]).
  static int _grant(int want, int earnedSoFar) {
    final cap = RewardRules.dailyCapStars;
    if (cap == null) return want;
    final remaining = cap - earnedSoFar;
    if (remaining <= 0) return 0;
    return want < remaining ? want : remaining;
  }

  Future<int> _earnedToday(DatabaseExecutor txn, int profileId, String day) async {
    final r = await txn.rawQuery(
      'SELECT COALESCE(SUM(amount), 0) AS s FROM reward_ledger WHERE profile_id = ? AND day = ?',
      [profileId, day],
    );
    return (r.first['s'] as int?) ?? 0;
  }

  Future<void> _ledger(DatabaseExecutor txn, int profileId, String day,
      int amount, String reason, String? ref, String nowIso) async {
    await txn.insert('reward_ledger', {
      'profile_id': profileId,
      'day': day,
      'amount': amount,
      'reason': reason,
      'ref': ref,
      'created_at': nowIso,
    });
  }

  Future<void> _applyWallet(DatabaseExecutor txn, int profileId,
      Map<String, int> result, String nowIso) async {
    final total = result.values.fold(0, (a, b) => a + b);
    if (total <= 0) return;
    await txn.rawInsert('''
      INSERT INTO reward_wallet (profile_id, stars, total_earned, updated_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(profile_id) DO UPDATE SET
        stars        = stars + excluded.stars,
        total_earned = total_earned + excluded.total_earned,
        updated_at   = excluded.updated_at
    ''', [profileId, total, total, nowIso]);
  }

  // ── Profile CRUD ──────────────────────────────────────────────────────────────

  Future<List<UserProfile>> getAllProfiles() async {
    final rows = await (await _database).query(
      'profiles',
      orderBy: 'last_used_at DESC, id ASC',
    );
    return rows.map(UserProfile.fromMap).toList();
  }

  Future<UserProfile> insertProfile({
    required String name,
    required int birthYear,
    required String avatarId,
    required String languageLevel,
    int ageLevel = 2,
  }) async {
    final now = DateTime.now().toIso8601String();
    final id = await (await _database).insert('profiles', {
      'name':           name,
      'birth_year':     birthYear,
      'avatar_id':      avatarId,
      'language_level': languageLevel,
      'age_level':      ageLevel,
      'created_at':     now,
      'last_used_at':   now,
    });
    return UserProfile(
      id:            id,
      name:          name,
      birthYear:     birthYear,
      avatarId:      avatarId,
      languageLevel: languageLevel,
      ageLevel:      ageLevel,
      createdAt:     DateTime.parse(now),
      lastUsedAt:    DateTime.parse(now),
    );
  }

  Future<void> updateProfile(UserProfile profile) async {
    await (await _database).update(
      'profiles',
      profile.toMap(),
      where: 'id = ?',
      whereArgs: [profile.id],
    );
  }

  Future<void> deleteProfile(int profileId) async {
    final db = await _database;
    // FK enforcement is not enabled on this DB, so remove profile-scoped rows
    // explicitly (both the older tables and the v9 reward tables).
    await db.transaction((txn) async {
      for (final table in const [
        'article_history',
        'favorites',
        'reward_wallet',
        'reward_ledger',
        'quiz_answer_progress',
        'quiz_completions',
        'discovered_areas',
        'area_stats',
        'daily_activity',
        'collected_cards',
      ]) {
        await txn.delete(table, where: 'profile_id = ?', whereArgs: [profileId]);
      }
      await txn.delete('profiles', where: 'id = ?', whereArgs: [profileId]);
    });
  }

  // ── Article history ───────────────────────────────────────────────────────────

  Future<void> recordArticleHistory({
    required int profileId,
    required String articleTitle,
  }) async {
    final db = await _database;
    await db.insert('article_history', {
      'profile_id':    profileId,
      'article_title': articleTitle,
      'opened_at':     DateTime.now().toIso8601String(),
    });
    // Keep only the 200 most recent entries per profile.
    await db.rawDelete('''
      DELETE FROM article_history
      WHERE profile_id = ?
        AND id NOT IN (
          SELECT id FROM article_history
          WHERE profile_id = ?
          ORDER BY opened_at DESC
          LIMIT 200
        )
    ''', [profileId, profileId]);
  }

  Future<List<String>> getArticleHistory({
    required int profileId,
    int limit = 20,
  }) async {
    final rows = await (await _database).rawQuery('''
      SELECT DISTINCT article_title
      FROM article_history
      WHERE profile_id = ?
      ORDER BY opened_at DESC
      LIMIT ?
    ''', [profileId, limit]);
    return rows.map((r) => r['article_title'] as String).toList();
  }

  // ── Favorites ─────────────────────────────────────────────────────────────────

  Future<bool> isFavorite({
    required int profileId,
    required String articleTitle,
  }) async {
    final rows = await (await _database).query(
      'favorites',
      where: 'profile_id = ? AND article_title = ?',
      whereArgs: [profileId, articleTitle],
      limit: 1,
    );
    return rows.isNotEmpty;
  }

  Future<void> addFavorite({
    required int profileId,
    required String articleTitle,
  }) async {
    await (await _database).insert(
      'favorites',
      {
        'profile_id':    profileId,
        'article_title': articleTitle,
        'added_at':      DateTime.now().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  Future<void> removeFavorite({
    required int profileId,
    required String articleTitle,
  }) async {
    await (await _database).delete(
      'favorites',
      where: 'profile_id = ? AND article_title = ?',
      whereArgs: [profileId, articleTitle],
    );
  }

  Future<List<String>> getFavorites({required int profileId}) async {
    final rows = await (await _database).query(
      'favorites',
      columns: ['article_title'],
      where: 'profile_id = ?',
      whereArgs: [profileId],
      orderBy: 'added_at DESC',
    );
    return rows.map((r) => r['article_title'] as String).toList();
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  Map<String, dynamic> _imageToMap(LicenseEntry e) => {
        'image_filename': e.imageFilename,
        'urheber': e.urheber,
        'lizenz': e.lizenz,
        'lizenz_url': e.lizenzUrl,
        'erlaubt': e.erlaubt ? 1 : 0,
        'checked_at': e.checkedAt.millisecondsSinceEpoch,
      };

  Map<String, dynamic> _audioToMap(AudioLicenseEntry e) => {
        'audio_filename': e.audioFilename,
        'urheber': e.urheber,
        'lizenz': e.lizenz,
        'lizenz_url': e.lizenzUrl,
        'caption': e.caption,
        'erlaubt': e.erlaubt ? 1 : 0,
        'checked_at': e.checkedAt.millisecondsSinceEpoch,
      };
}
