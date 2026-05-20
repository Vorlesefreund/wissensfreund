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
      version: 2,
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
          CREATE TABLE sync_info (
            id          INTEGER PRIMARY KEY,
            sync_date   TEXT NOT NULL,
            zim_version TEXT NOT NULL
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
      },
    );
  }

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
    await _putSingle(await _database, entry);
  }

  Future<void> putBatch(List<LicenseEntry> entries) async {
    final db = await _database;
    final batch = db.batch();
    for (final e in entries) {
      batch.insert('license_cache', _entryToMap(e),
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

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

  Future<void> _putSingle(Database db, LicenseEntry entry) async {
    await db.insert('license_cache', _entryToMap(entry),
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Map<String, dynamic> _entryToMap(LicenseEntry e) => {
        'image_filename': e.imageFilename,
        'urheber': e.urheber,
        'lizenz': e.lizenz,
        'lizenz_url': e.lizenzUrl,
        'erlaubt': e.erlaubt ? 1 : 0,
        'checked_at': e.checkedAt.millisecondsSinceEpoch,
      };
}
