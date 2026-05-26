/// Central configuration for all Cloudflare R2 asset URLs.
///
/// SETUP: After creating the Cloudflare R2 bucket, replace the placeholder
/// below with the actual public URL. Format:
///   https://pub-[hash].r2.dev          (R2 built-in public domain)
///   https://assets.yourdomain.com      (custom domain)
///
/// The URL must NOT end with a slash.
class AssetConfig {
  AssetConfig._();

  static const String r2BaseUrl =
      'https://pub-07f0107be14b48fd8652e5318441c7c2.r2.dev';

  static String get mediaLicensesUrl  => '$r2BaseUrl/media_licenses.json';
  static String get audioIndexUrl     => '$r2BaseUrl/audio_index.json';
  static String get audioZipUrl       => '$r2BaseUrl/wissensfreund_audio.zip';
  static String get zimVersionUrl     => '$r2BaseUrl/zim_version.json';

  // ── Image tiers ─────────────────────────────────────────────────────────────
  // thumb (300px)    — Free tier, sourced from ZIM
  // standard (600px) — Plus/Premium offline download
  // pro (1200px)     — Plus/Premium on-demand at WiFi (downloaded individually)

  /// Offline image library for Plus/Premium users (600px, ~600 MB).
  static String get imageLibraryUrl      => '$r2BaseUrl/images_standard.zip';
  static String get imageManifestUrl     => '$r2BaseUrl/images_standard_manifest.json';

  /// Approximate size of images_standard.zip for ETA estimation (bytes).
  static const int imageLibrarySizeBytes = 600 * 1024 * 1024; // ~600 MB
}
