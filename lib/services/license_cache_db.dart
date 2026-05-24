import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

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
      version: 4,
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
