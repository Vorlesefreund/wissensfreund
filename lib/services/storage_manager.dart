import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Manages the two persistent storage directories used by the app.
///
/// image_library/ — offline image package (low/medium quality, user-installed)
/// image_cache/   — on-demand HiRes cache (max 500 MB, LRU, 30-day TTL)
///
/// Prefers external app storage (SD card / USB) when available and returns
/// to internal app storage as fallback. The chosen path is persisted in
/// SharedPreferences so it survives hot restarts.
class StorageManager {
  StorageManager._();
  static final StorageManager instance = StorageManager._();

  static const _prefKey       = 'storage_base_path';
  static const _maxCacheBytes = 500 * 1024 * 1024; // 500 MB
  static const _cacheMaxAge   = Duration(days: 30);

  String? _basePath;
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    _basePath = await _resolveBasePath();
    await _ensureDirs();
    debugPrint('StorageManager: base=$_basePath');
  }

  /// Directory for the offline image library (medium quality).
  /// Only deleted by explicit user action or quality-tier change.
  Directory get imageLibraryDir {
    assert(_initialized, 'StorageManager not initialized');
    return Directory('$_basePath/image_library');
  }

  /// Directory for on-demand HiRes image cache.
  /// Automatically evicted by [evictOldCache].
  Directory get imageCacheDir {
    assert(_initialized, 'StorageManager not initialized');
    return Directory('$_basePath/image_cache');
  }

  // ── Cache eviction ───────────────────────────────────────────────────────────

  /// Removes files older than 30 days, then LRU-evicts until cache is
  /// under 500 MB. Safe to call in the background at app start.
  Future<void> evictOldCache() async {
    final dir = imageCacheDir;
    if (!dir.existsSync()) return;

    final now = DateTime.now();

    // Pass 1: remove by age.
    for (final entity in dir.listSync(recursive: true).whereType<File>()) {
      try {
        if (now.difference(entity.statSync().modified) > _cacheMaxAge) {
          entity.deleteSync();
        }
      } catch (_) {}
    }

    // Pass 2: LRU until under size limit.
    final remaining = dir
        .listSync(recursive: true)
        .whereType<File>()
        .toList();

    var totalBytes = remaining.fold<int>(0, (s, f) {
      try { return s + f.lengthSync(); } catch (_) { return s; }
    });

    if (totalBytes <= _maxCacheBytes) return;

    remaining.sort((a, b) {
      try {
        return a.statSync().modified.compareTo(b.statSync().modified);
      } catch (_) { return 0; }
    });

    for (final file in remaining) {
      if (totalBytes <= _maxCacheBytes) break;
      try {
        totalBytes -= file.lengthSync();
        file.deleteSync();
      } catch (_) {}
    }

    debugPrint('StorageManager: cache eviction done');
  }

  // ── Internal ─────────────────────────────────────────────────────────────────

  Future<String> _resolveBasePath() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_prefKey);
    if (stored != null && Directory(stored).existsSync()) return stored;

    // Prefer external storage (more space, survives uninstall on some devices).
    String? chosen;
    try {
      final ext = await getExternalStorageDirectory();
      if (ext != null) chosen = ext.path;
    } catch (_) {}

    chosen ??= (await getApplicationDocumentsDirectory()).path;
    await prefs.setString(_prefKey, chosen);
    return chosen;
  }

  Future<void> _ensureDirs() async {
    await imageLibraryDir.create(recursive: true);
    await imageCacheDir.create(recursive: true);
  }
}
