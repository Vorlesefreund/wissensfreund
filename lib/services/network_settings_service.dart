import 'package:shared_preferences/shared_preferences.dart';

/// SharedPreferences-backed settings for WiFi and mobile data limits.
class NetworkSettingsService {
  NetworkSettingsService._();
  static final NetworkSettingsService instance = NetworkSettingsService._();

  SharedPreferences? _prefs;

  Future<SharedPreferences> get _p async {
    _prefs ??= await SharedPreferences.getInstance();
    return _prefs!;
  }

  // ── WiFi ──────────────────────────────────────────────────────────────────────

  Future<bool> get wifiUnlimited async =>
      (await _p).getBool('wifi_unlimited') ?? true;

  Future<int> get wifiDailyLimitMb async =>
      (await _p).getInt('wifi_daily_limit_mb') ?? 0;

  Future<int> get wifiMonthlyLimitMb async =>
      (await _p).getInt('wifi_monthly_limit_mb') ?? 0;

  Future<void> setWifiUnlimited(bool v) async =>
      (await _p).setBool('wifi_unlimited', v);

  Future<void> setWifiDailyLimitMb(int v) async =>
      (await _p).setInt('wifi_daily_limit_mb', v);

  Future<void> setWifiMonthlyLimitMb(int v) async =>
      (await _p).setInt('wifi_monthly_limit_mb', v);

  // ── Mobile ────────────────────────────────────────────────────────────────────

  Future<bool> get mobileAllowed async =>
      (await _p).getBool('mobile_allowed') ?? false;

  Future<int> get mobileDailyLimitMb async =>
      (await _p).getInt('mobile_daily_limit_mb') ?? 100;

  Future<int> get mobileMonthlyLimitMb async =>
      (await _p).getInt('mobile_monthly_limit_mb') ?? 500;

  Future<void> setMobileAllowed(bool v) async =>
      (await _p).setBool('mobile_allowed', v);

  Future<void> setMobileDailyLimitMb(int v) async =>
      (await _p).setInt('mobile_daily_limit_mb', v);

  Future<void> setMobileMonthlyLimitMb(int v) async =>
      (await _p).setInt('mobile_monthly_limit_mb', v);

  // ── Onboarding ────────────────────────────────────────────────────────────────

  Future<bool> get networkSettingsOffered async =>
      (await _p).getBool('network_settings_offered') ?? false;

  Future<void> setNetworkSettingsOffered(bool v) async =>
      (await _p).setBool('network_settings_offered', v);
}
