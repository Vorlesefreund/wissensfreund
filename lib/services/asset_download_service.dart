import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'network_service.dart';

class DownloadResult {
  final bool success;
  final int bytesTransferred;
  final String? error;

  const DownloadResult({
    required this.success,
    required this.bytesTransferred,
    this.error,
  });
}

class _WifiLostException implements Exception {
  const _WifiLostException();
}

/// Central download service for all Cloudflare R2 assets.
///
/// - Network gate: delegates to [NetworkService.canUseNetwork].
/// - Streaming: writes directly to disk, never loads full file into memory.
/// - Atomic: uses a .tmp file; only renames to destination after full download.
/// - Retry: up to 3 attempts with exponential backoff (2s, 4s).
/// - ETA: rolling 5-second window of download speed.
/// - [trackUsage]: when false (ZIM downloads), data limits are not enforced
///   and usage is not recorded.
class AssetDownloadService {
  AssetDownloadService._();
  static final AssetDownloadService instance = AssetDownloadService._();

  /// Estimates download time given [totalBytes] and an assumed WiFi speed.
  static Duration estimateEta(
    int totalBytes, {
    double assumedSpeedBytesPerSec = 10 * 1024 * 1024, // 10 MB/s default
  }) {
    return Duration(seconds: (totalBytes / assumedSpeedBytesPerSec).ceil());
  }

  static const _maxAttempts    = 3;
  static const _wifiCheckEvery = Duration(seconds: 3);
  static const _requestTimeout = Duration(minutes: 10);

  /// Downloads [url] and writes the result to [destinationPath].
  ///
  /// Returns immediately with error='no_wifi' / 'mobile_not_allowed' /
  /// 'limit_reached' / 'no_network' if [NetworkService.canUseNetwork] rejects.
  ///
  /// Set [trackUsage] to false for ZIM downloads to skip data-limit checks.
  Future<DownloadResult> downloadAsset({
    required String url,
    required String destinationPath,
    void Function(int received, int total, Duration eta)? onProgress,
    bool trackUsage = true,
  }) async {
    final check = await NetworkService.instance.canUseNetwork(
      trackUsage: trackUsage,
    );
    if (!check.allowed) {
      return DownloadResult(
          success: false, bytesTransferred: 0, error: check.reason);
    }

    for (int attempt = 0; attempt < _maxAttempts; attempt++) {
      if (attempt > 0) {
        await Future.delayed(Duration(seconds: pow(2, attempt).toInt()));
      }
      try {
        final result =
            await _downloadOnce(url, destinationPath, onProgress);
        if (result.success && trackUsage && result.bytesTransferred > 0) {
          await NetworkService.instance.recordUsage(result.bytesTransferred);
        }
        return result;
      } on _WifiLostException {
        return const DownloadResult(
            success: false, bytesTransferred: 0, error: 'wifi_lost');
      } catch (_) {
        if (attempt == _maxAttempts - 1) rethrow;
      }
    }

    return const DownloadResult(
        success: false, bytesTransferred: 0, error: 'max_retries');
  }

  // ── Internal ─────────────────────────────────────────────────────────────────

  Future<DownloadResult> _downloadOnce(
    String url,
    String destinationPath,
    void Function(int, int, Duration)? onProgress,
  ) async {
    final client     = http.Client();
    var lastConnCheck = DateTime.now();

    try {
      final response = await client
          .send(http.Request('GET', Uri.parse(url)))
          .timeout(_requestTimeout);

      if (response.statusCode != 200) {
        return DownloadResult(
            success: false,
            bytesTransferred: 0,
            error: 'http_${response.statusCode}');
      }

      final total   = response.contentLength ?? -1;
      final tmpPath = '$destinationPath.tmp';
      final tmpFile = File(tmpPath);
      await tmpFile.parent.create(recursive: true);
      final sink = tmpFile.openWrite();

      var received = 0;
      final samples = <(int, DateTime)>[];

      try {
        await for (final chunk in response.stream) {
          sink.add(chunk);
          received += chunk.length;

          final now = DateTime.now();

          if (now.difference(lastConnCheck) >= _wifiCheckEvery) {
            lastConnCheck = now;
            final conn = await NetworkService.instance.getCurrentConnectionType();
            if (conn == ConnectionType.none) throw const _WifiLostException();
          }

          if (onProgress != null) {
            samples.add((received, now));
            samples.removeWhere((s) => now.difference(s.$2).inSeconds > 5);

            var eta = Duration.zero;
            if (samples.length >= 2 && total > 0) {
              final deltaBytes = samples.last.$1 - samples.first.$1;
              final deltaMs    = samples.last.$2
                  .difference(samples.first.$2)
                  .inMilliseconds;
              if (deltaMs > 0 && deltaBytes > 0) {
                final speed     = deltaBytes / deltaMs;
                final remaining = (total - received).clamp(0, total);
                eta = Duration(milliseconds: (remaining / speed).round());
              }
            }
            onProgress(received, total, eta);
          }
        }
      } catch (e) {
        await sink.close();
        if (tmpFile.existsSync()) tmpFile.deleteSync();
        rethrow;
      }

      await sink.close();

      final dest = File(destinationPath);
      if (dest.existsSync()) dest.deleteSync();
      tmpFile.renameSync(destinationPath);

      return DownloadResult(success: true, bytesTransferred: received);
    } finally {
      client.close();
    }
  }
}
