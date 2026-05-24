import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config/asset_config.dart';
import 'asset_download_service.dart';
import 'license_cache_db.dart';
import 'storage_manager.dart';

class ZimVersionInfo {
  final String version;
  final String zimUrl;
  final int sizeBytes;
  final String updated;

  const ZimVersionInfo({
    required this.version,
    required this.zimUrl,
    required this.sizeBytes,
    required this.updated,
  });

  factory ZimVersionInfo.fromJson(Map<String, dynamic> j) => ZimVersionInfo(
        version:   j['version'] as String? ?? '',
        zimUrl:    j['zim_url'] as String? ?? '',
        sizeBytes: j['size_bytes'] as int? ?? 0,
        updated:   j['updated'] as String? ?? '',
      );

  String get sizeMb => '${(sizeBytes / (1024 * 1024)).round()} MB';
}

/// Checks for ZIM updates from R2 and manages the download + swap flow.
///
/// Platform-channel swap (`wissensfreund/zim` → `swapZim`) requires the
/// Android side to accept a new path and hot-swap the ZIM reader without
/// restarting the app. That channel call is attempted here; if the Kotlin
/// side is not yet implemented it throws and the user is asked to restart.
class ZimUpdateService {
  ZimUpdateService._();
  static final ZimUpdateService instance = ZimUpdateService._();

  static const _skipKey    = 'zim_update_skip_until';
  static const _zimChannel = MethodChannel('wissensfreund/zim');

  // ── Public API ───────────────────────────────────────────────────────────────

  /// Fetches `zim_version.json` from R2 and returns update info if a newer
  /// version is available and the user has not chosen to skip for 30 days.
  Future<ZimVersionInfo?> checkForUpdate() async {
    try {
      // Skip window active?
      final prefs = await SharedPreferences.getInstance();
      final skipUntil = prefs.getString(_skipKey);
      if (skipUntil != null) {
        final until = DateTime.tryParse(skipUntil);
        if (until != null && DateTime.now().isBefore(until)) return null;
      }

      final resp = await http
          .get(Uri.parse(AssetConfig.zimVersionUrl),
              headers: {'User-Agent': 'Wissensfreund/1.0'})
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return null;

      final info = ZimVersionInfo.fromJson(
          jsonDecode(resp.body) as Map<String, dynamic>);
      if (info.version.isEmpty) return null;

      final stored = await LicenseCacheDb.instance.getStoredZimVersion();
      if (stored == null || stored == info.version) return null;

      return info;
    } catch (_) {
      return null;
    }
  }

  /// Mark "skip for 30 days".
  Future<void> skipFor30Days() async {
    final prefs = await SharedPreferences.getInstance();
    final until = DateTime.now().add(const Duration(days: 30));
    await prefs.setString(_skipKey, until.toIso8601String());
  }

  /// Download [info.zimUrl] to a staging file and then call the Android
  /// platform channel to swap the ZIM reader.
  ///
  /// Returns true on full success (download + swap), false on any error.
  /// [onProgress] receives (bytesReceived, totalBytes, eta).
  Future<bool> downloadAndSwap(
    ZimVersionInfo info, {
    void Function(int, int, Duration)? onProgress,
  }) async {
    await StorageManager.instance.initialize();
    final zimDir  = StorageManager.instance.zimUpdateDir;
    await zimDir.create(recursive: true);
    final destPath = '${zimDir.path}/klexikon_update.zim';

    final result = await AssetDownloadService.instance.downloadAsset(
      url:             info.zimUrl,
      destinationPath: destPath,
      onProgress:      onProgress,
      trackUsage:      false, // ZIM downloads are exempt from data limits
    );

    if (!result.success) return false;

    // Ask the Kotlin side to hot-swap the ZIM reader.
    try {
      await _zimChannel.invokeMethod<void>('swapZim', {'path': destPath});
    } on MissingPluginException {
      // Android channel not yet implemented — cold-restart required.
      // The download succeeded; caller shows a restart prompt.
      return true;
    } catch (_) {
      return false;
    }

    return true;
  }
}
