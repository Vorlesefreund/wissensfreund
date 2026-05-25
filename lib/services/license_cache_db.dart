import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

import 'profile_service.dart';

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
      version: 7,
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
  }) async {
    final now = DateTime.now().toIso8601String();
    final id = await (await _database).insert('profiles', {
      'name':           name,
      'birth_year':     birthYear,
      'avatar_id':      avatarId,
      'language_level': languageLevel,
      'created_at':     now,
      'last_used_at':   now,
    });
    return UserProfile(
      id:            id,
      name:          name,
      birthYear:     birthYear,
      avatarId:      avatarId,
      languageLevel: languageLevel,
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
    await (await _database).delete(
      'profiles',
      where: 'id = ?',
      whereArgs: [profileId],
    );
    // Cascade handles article_history and favorites.
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
