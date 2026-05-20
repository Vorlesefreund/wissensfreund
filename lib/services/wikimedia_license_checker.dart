import 'dart:convert';
import 'package:http/http.dart' as http;
import 'license_cache_db.dart';

const _licenseJsonUrl =
    'https://github.com/Vorlesefreund/wissensfreund/releases/latest/download/image_licenses.json';

class WikimediaLicenseChecker {
  WikimediaLicenseChecker._();
  static final WikimediaLicenseChecker instance = WikimediaLicenseChecker._();

  static const _timeout = Duration(seconds: 20);

  /// Returns true if this image may be displayed.
  /// Only reads from the local SQLite cache — never makes API calls.
  /// Returns false if the image is not in the cache (JSON not yet synced).
  Future<bool> isAllowed(String imageFilename) async {
    final entry = await LicenseCacheDb.instance.get(imageFilename);
    return entry?.erlaubt ?? false;
  }

  /// Returns cached license entry for the ⓘ overlay, or null if not cached.
  Future<LicenseEntry?> getCached(String imageFilename) =>
      LicenseCacheDb.instance.get(imageFilename);

  /// True if the license JSON has been downloaded and cached at least once.
  Future<bool> isSynced() => LicenseCacheDb.instance.isSynced();

  /// Downloads the centrally-generated image_licenses.json from the GitHub
  /// release and populates the local SQLite cache.
  /// Call once on app start when isSynced() returns false.
  /// Returns true on success, false if offline or the download failed.
  Future<bool> syncLicenses() async {
    try {
      final response = await http
          .get(Uri.parse(_licenseJsonUrl))
          .timeout(_timeout);
      if (response.statusCode != 200) return false;

      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final images = data['images'] as Map<String, dynamic>? ?? {};
      final generated = data['generated'] as String? ?? '';
      final zimVersion = data['zim_version'] as String? ?? '';

      final entries = <LicenseEntry>[];
      for (final kv in images.entries) {
        final info = kv.value as Map<String, dynamic>;
        entries.add(LicenseEntry(
          imageFilename: kv.key,
          urheber: info['author'] as String?,
          lizenz: info['license'] as String?,
          lizenzUrl: info['license_url'] as String?,
          erlaubt: (info['allowed'] as bool?) ?? false,
          checkedAt: DateTime.now(),
        ));
      }

      await LicenseCacheDb.instance.putBatch(entries);
      await LicenseCacheDb.instance.saveLastSync(generated, zimVersion);
      return true;
    } catch (_) {
      return false;
    }
  }
}
