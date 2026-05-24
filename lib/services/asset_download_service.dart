import 'dart:io';
import 'dart:math';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;

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
/// - WiFi-only: returns immediately with error='no_wifi' on mobile/no connection.
/// - Streaming: writes directly to disk, never loads full file into memory.
/// - Atomic: uses a .tmp file; only renames to destination after full download.
/// - Retry: up to 3 attempts with exponential backoff (2s, 4s).
/// - ETA: rolling 5-second window of download speed.
class AssetDownloadService {
  AssetDownloadService._();
  static final AssetDownloadService instance = AssetDownloadService._();

  static const _maxAttempts    = 3;
  static const _wifiCheckEvery = Duration(seconds: 3);
  static const _requestTimeout = Duration(minutes: 10);

  /// Downloads [url] and writes the result to [destinationPath].
  ///
  /// Returns immediately with success=false if not on WiFi.
  /// [onProgress] receives (bytesReceived, totalBytes, estimatedTimeLeft).
  /// totalBytes is -1 when the server does not send Content-Length.
  Future<DownloadResult> downloadAsset({
    required String url,
    required String destinationPath,
    void Function(int received, int total, Duration eta)? onProgress,
  }) async {
    if (!await _isOnWifi()) {
      return const DownloadResult(
          success: false, bytesTransferred: 0, error: 'no_wifi');
    }

    for (int attempt = 0; attempt < _maxAttempts; attempt++) {
      if (attempt > 0) {
        await Future.delayed(Duration(seconds: pow(2, attempt).toInt()));
      }
      try {
        return await _downloadOnce(url, destinationPath, onProgress);
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

  Future<bool> _isOnWifi() async {
    final result = await Connectivity().checkConnectivity();
    return result.contains(ConnectivityResult.wifi);
  }

  Future<DownloadResult> _downloadOnce(
    String url,
    String destinationPath,
    void Function(int, int, Duration)? onProgress,
  ) async {
    final client = http.Client();
    var lastWifiCheck = DateTime.now();

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
      // (cumulativeBytes, timestamp) for ETA rolling window
      final samples = <(int, DateTime)>[];

      try {
        await for (final chunk in response.stream) {
          sink.add(chunk);
          received += chunk.length;

          final now = DateTime.now();

          // Periodic WiFi check — every 3 seconds.
          if (now.difference(lastWifiCheck) >= _wifiCheckEvery) {
            lastWifiCheck = now;
            if (!await _isOnWifi()) throw const _WifiLostException();
          }

          if (onProgress != null) {
            samples.add((received, now));
            samples.removeWhere(
                (s) => now.difference(s.$2).inSeconds > 5);

            var eta = Duration.zero;
            if (samples.length >= 2 && total > 0) {
              final deltaBytes = samples.last.$1 - samples.first.$1;
              final deltaMs    = samples.last.$2
                  .difference(samples.first.$2)
                  .inMilliseconds;
              if (deltaMs > 0 && deltaBytes > 0) {
                final speed    = deltaBytes / deltaMs; // bytes/ms
                final remaining = (total - received).clamp(0, total);
                eta = Duration(
                    milliseconds: (remaining / speed).round());
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

      // Atomic rename — destination only appears after successful download.
      final dest = File(destinationPath);
      if (dest.existsSync()) dest.deleteSync();
      tmpFile.renameSync(destinationPath);

      return DownloadResult(success: true, bytesTransferred: received);
    } finally {
      client.close();
    }
  }
}
