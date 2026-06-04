import 'package:connectivity_plus/connectivity_plus.dart';

import 'data_usage_service.dart';
import 'network_settings_service.dart';

export 'data_usage_service.dart' show LimitWarningLevel;

enum ConnectionType { none, wifi, mobile }

class NetworkCheckResult {
  final bool allowed;
  final String? reason; // 'no_network' | 'mobile_not_allowed' | 'limit_reached'
  final LimitWarningLevel? pendingWarning;

  const NetworkCheckResult({
    required this.allowed,
    this.reason,
    this.pendingWarning,
  });
}

/// Central gate for all network access.
///
/// Call [canUseNetwork] before starting any download.
/// Call [recordUsage] after a successful download with `trackUsage: true`.
/// [consumePendingWarning] drains the queued 80/90% warning for the UI to show.
class NetworkService {
  NetworkService._();
  static final NetworkService instance = NetworkService._();

  LimitWarningLevel? _pendingWarning;

  /// Drains and returns any queued limit warning (80 % / 90 %), or null.
  LimitWarningLevel? consumePendingWarning() {
    final w = _pendingWarning;
    _pendingWarning = null;
    return w;
  }

  /// Returns the current physical connection type.
  Future<ConnectionType> getCurrentConnectionType() async {
    final result = await Connectivity().checkConnectivity();
    if (result.contains(ConnectivityResult.wifi))   return ConnectionType.wifi;
    if (result.contains(ConnectivityResult.mobile)) return ConnectionType.mobile;
    return ConnectionType.none;
  }

  /// Gate check before any download.
  ///
  /// For small, content-critical fetches (e.g. article thumbnails):
  /// only checks connectivity + mobile-data permission, never blocks on data limit.
  Future<bool> isContentFetchAllowed() async {
    final conn = await getCurrentConnectionType();
    if (conn == ConnectionType.none) return false;
    if (conn == ConnectionType.mobile) {
      return await NetworkSettingsService.instance.mobileAllowed;
    }
    return true;
  }

  /// When [trackUsage] is false (ZIM downloads), only connectivity is checked —
  /// no data-limit enforcement.
  Future<NetworkCheckResult> canUseNetwork({
    int estimatedBytes = 0,
    bool trackUsage = true,
  }) async {
    final conn = await getCurrentConnectionType();

    if (conn == ConnectionType.none) {
      return const NetworkCheckResult(allowed: false, reason: 'no_network');
    }

    if (!trackUsage) {
      return const NetworkCheckResult(allowed: true);
    }

    final settings = NetworkSettingsService.instance;
    final usage    = DataUsageService.instance;
    final connStr  = conn == ConnectionType.wifi ? 'wifi' : 'mobile';

    if (conn == ConnectionType.mobile) {
      if (!await settings.mobileAllowed) {
        return const NetworkCheckResult(
            allowed: false, reason: 'mobile_not_allowed');
      }
    }

    final level = await usage.checkThreshold(connStr);

    if (level == LimitWarningLevel.limitReached) {
      return NetworkCheckResult(
          allowed: false,
          reason: 'limit_reached',
          pendingWarning: level);
    }

    if (level != null) {
      final alreadyShown = await usage.isDailyWarningShown(level, connStr);
      if (!alreadyShown) {
        await usage.markDailyWarningShown(level, connStr);
        _pendingWarning = level;
      }
    }

    return NetworkCheckResult(allowed: true, pendingWarning: _pendingWarning);
  }

  /// Record [bytes] transferred after a successful tracked download.
  Future<void> recordUsage(int bytes) async {
    final conn = await getCurrentConnectionType();
    if (conn == ConnectionType.none) return;
    final connStr = conn == ConnectionType.wifi ? 'wifi' : 'mobile';
    await DataUsageService.instance.recordUsage(bytes, connStr);
  }
}
