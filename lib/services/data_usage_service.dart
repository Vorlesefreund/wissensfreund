import 'package:shared_preferences/shared_preferences.dart';

import 'license_cache_db.dart';
import 'network_settings_service.dart';

enum LimitWarningLevel { warning80, warning90, limitReached }

/// Tracks daily/monthly data usage and checks limit thresholds.
class DataUsageService {
  DataUsageService._();
  static final DataUsageService instance = DataUsageService._();

  /// Record [bytes] transferred on [connectionType] ('wifi' | 'mobile').
  Future<void> recordUsage(int bytes, String connectionType) async {
    await LicenseCacheDb.instance.recordDataUsage(
      date: _today(),
      connectionType: connectionType,
      bytes: bytes,
    );
  }

  /// Returns the current limit warning level, or null if within limits.
  Future<LimitWarningLevel?> checkThreshold(String connectionType) async {
    final settings = NetworkSettingsService.instance;
    final db       = LicenseCacheDb.instance;

    final int dailyLimitMb;
    final int monthlyLimitMb;

    if (connectionType == 'wifi') {
      if (await settings.wifiUnlimited) return null;
      dailyLimitMb   = await settings.wifiDailyLimitMb;
      monthlyLimitMb = await settings.wifiMonthlyLimitMb;
    } else {
      dailyLimitMb   = await settings.mobileDailyLimitMb;
      monthlyLimitMb = await settings.mobileMonthlyLimitMb;
    }

    final daily   = await db.getDailyUsage(_today(), connectionType);
    final monthly = await db.getMonthlyUsage(_monthPrefix(), connectionType);

    return _checkLimits(
      daily:         daily,
      monthly:       monthly,
      dailyLimit:    dailyLimitMb * 1024 * 1024,
      monthlyLimit:  monthlyLimitMb * 1024 * 1024,
    );
  }

  /// True if the [level] warning for [connectionType] was already shown today.
  Future<bool> isDailyWarningShown(
      LimitWarningLevel level, String connectionType) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_warningKey(level, connectionType)) ?? false;
  }

  /// Mark the [level] warning for [connectionType] as shown today.
  Future<void> markDailyWarningShown(
      LimitWarningLevel level, String connectionType) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_warningKey(level, connectionType), true);
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  String _today()       => DateTime.now().toIso8601String().substring(0, 10);
  String _monthPrefix() => DateTime.now().toIso8601String().substring(0, 7);

  String _warningKey(LimitWarningLevel level, String conn) =>
      'warn_shown_${level.name}_${conn}_${_today()}';

  LimitWarningLevel? _checkLimits({
    required int daily,
    required int monthly,
    required int dailyLimit,
    required int monthlyLimit,
  }) {
    // Monthly takes precedence over daily.
    if (monthlyLimit > 0) {
      final pct = monthly / monthlyLimit;
      if (pct >= 1.0) return LimitWarningLevel.limitReached;
      if (pct >= 0.9) return LimitWarningLevel.warning90;
      if (pct >= 0.8) return LimitWarningLevel.warning80;
    }
    if (dailyLimit > 0) {
      final pct = daily / dailyLimit;
      if (pct >= 1.0) return LimitWarningLevel.limitReached;
      if (pct >= 0.9) return LimitWarningLevel.warning90;
      if (pct >= 0.8) return LimitWarningLevel.warning80;
    }
    return null;
  }
}
