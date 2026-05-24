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

  static String get mediaLicensesUrl => '$r2BaseUrl/media_licenses.json';
  static String get audioIndexUrl    => '$r2BaseUrl/audio_index.json';
  static String get audioZipUrl      => '$r2BaseUrl/wissensfreund_audio.zip';
}
