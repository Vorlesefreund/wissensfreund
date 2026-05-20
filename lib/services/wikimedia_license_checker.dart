import 'dart:convert';
import 'package:http/http.dart' as http;
import 'license_cache_db.dart';

const _mediaJsonUrl =
    'https://github.com/Vorlesefreund/wissensfreund/releases/latest/download/media_licenses.json';

class WikimediaLicenseChecker {
  WikimediaLicenseChecker._();
  static final WikimediaLicenseChecker instance = WikimediaLicenseChecker._();

  static const _timeout = Duration(seconds: 20);

  // ── Images ──────────────────────────────────────────────────────────────────

  /// Returns true if this image may be displayed.
  /// Only reads from the local SQLite cache — never makes API calls.
  Future<bool> isAllowed(String imageFilename) async {
    final entry = await LicenseCacheDb.instance.get(imageFilename);
    return entry?.erlaubt ?? false;
  }

  /// Returns cached license entry for the ⓘ overlay, or null if not cached.
  Future<LicenseEntry?> getCached(String imageFilename) =>
      LicenseCacheDb.instance.get(imageFilename);

  // ── Audio ───────────────────────────────────────────────────────────────────

  /// Returns true if this audio file may be played.
  Future<bool> isAudioAllowed(String audioFilename) async {
    final entry = await LicenseCacheDb.instance.getAudio(audioFilename);
    return entry?.erlaubt ?? false;
  }

  /// Returns cached audio license entry (includes caption), or null.
  Future<AudioLicenseEntry?> getCachedAudio(String audioFilename) =>
      LicenseCacheDb.instance.getAudio(audioFilename);

  // ── Sync ────────────────────────────────────────────────────────────────────

  /// True if the media license JSON has been downloaded and cached at least once.
  Future<bool> isSynced() => LicenseCacheDb.instance.isSynced();

  /// Downloads media_licenses.json from the GitHub release and populates the
  /// local SQLite cache (images + audio).
  /// Call once on app start when isSynced() returns false.
  /// Returns true on success, false if offline or the download failed.
  Future<bool> syncLicenses() async {
    try {
      final response = await http
          .get(Uri.parse(_mediaJsonUrl))
          .timeout(_timeout);
      if (response.statusCode != 200) return false;

      final data       = jsonDecode(response.body) as Map<String, dynamic>;
      final images     = data['images'] as Map<String, dynamic>? ?? {};
      final audio      = data['audio']  as Map<String, dynamic>? ?? {};
      final generated  = data['generated']   as String? ?? '';
      final zimVersion = data['zim_version']  as String? ?? '';

      final imageEntries = <LicenseEntry>[];
      for (final kv in images.entries) {
        final info = kv.value as Map<String, dynamic>;
        imageEntries.add(LicenseEntry(
          imageFilename: kv.key,
          urheber: info['author']      as String?,
          lizenz:  info['license']     as String?,
          lizenzUrl: info['license_url'] as String?,
          erlaubt: (info['allowed'] as bool?) ?? false,
          checkedAt: DateTime.now(),
        ));
      }

      final audioEntries = <AudioLicenseEntry>[];
      for (final kv in audio.entries) {
        final info = kv.value as Map<String, dynamic>;
        audioEntries.add(AudioLicenseEntry(
          audioFilename: kv.key,
          urheber:   info['author']      as String?,
          lizenz:    info['license']     as String?,
          lizenzUrl: info['license_url'] as String?,
          caption:   info['caption']     as String?,
          erlaubt:   (info['allowed'] as bool?) ?? false,
          checkedAt: DateTime.now(),
        ));
      }

      await LicenseCacheDb.instance.putBatch(imageEntries);
      await LicenseCacheDb.instance.putBatchAudio(audioEntries);
      await LicenseCacheDb.instance.saveLastSync(generated, zimVersion);
      return true;
    } catch (_) {
      return false;
    }
  }
}
