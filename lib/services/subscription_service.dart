import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum SubscriptionTier { free, plus, premium }

/// Central feature-gate service for the Wissensfreund freemium model.
///
/// Tier hierarchy:  free < plus < premium
/// Premium includes all Plus features.
///
/// Cached in SharedPreferences for offline availability;
/// verified against Google Play on each app start.
class SubscriptionService {
  SubscriptionService._();
  static final SubscriptionService instance = SubscriptionService._();

  static const _channel = MethodChannel('wissensfreund/billing');
  static const _tierKey = 'subscription_tier';

  SubscriptionTier _tier = SubscriptionTier.free;
  bool _initialized = false;

  // ── Feature gates ───────────────────────────────────────────────────────────

  bool get isFree    => _tier == SubscriptionTier.free;
  bool get isPlus    => _tier == SubscriptionTier.plus || isPremium;
  bool get isPremium => _tier == SubscriptionTier.premium;

  /// Premium: Rückfragen an Professor (Gemini API).
  bool get canAskQuestions => isPremium;

  /// Plus or Premium: offline 800px image library download.
  bool get canDownloadMediumQuality => isPlus;

  /// Plus or Premium: HiRes on-demand images (1600px, WiFi only).
  bool get canUseHighResOnDemand => isPlus;

  SubscriptionTier get tier => _tier;

  String get tierName {
    switch (_tier) {
      case SubscriptionTier.premium: return 'Wissensfreund Premium';
      case SubscriptionTier.plus:    return 'Wissensfreund Plus';
      case SubscriptionTier.free:    return 'Wissensfreund Free';
    }
  }

  // ── Initialize ───────────────────────────────────────────────────────────────

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    // Load cached tier immediately — works offline.
    final prefs = await SharedPreferences.getInstance();
    _tier = _parseTier(prefs.getString(_tierKey) ?? 'free');

    // Verify with Play Store in background.
    _verifyInBackground();
  }

  Future<void> _verifyInBackground() async {
    try {
      final result = await _channel.invokeMethod<String>('getStatus');
      if (result != null) await _applyTier(_parseTier(result));
    } catch (_) {
      // Billing unavailable or offline — keep cached tier.
    }
  }

  Future<void> _applyTier(SubscriptionTier tier) async {
    _tier = tier;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tierKey, _tierString(tier));
  }

  // ── Purchase ────────────────────────────────────────────────────────────────

  /// Launches the Google Play Plus purchase flow.
  /// Returns the new tier on success. Throws [PlatformException] on error.
  /// Returns [SubscriptionTier.free] if the user cancelled.
  Future<SubscriptionTier> purchasePlus() async {
    final raw = await _channel.invokeMethod<String>('purchasePlus');
    if (raw == null || raw == 'cancelled') return _tier;
    final tier = _parseTier(raw);
    await _applyTier(tier);
    return tier;
  }

  /// Launches the Google Play Premium subscription flow.
  Future<SubscriptionTier> subscribePremium() async {
    final raw = await _channel.invokeMethod<String>('subscribePremium');
    if (raw == null || raw == 'cancelled') return _tier;
    final tier = _parseTier(raw);
    await _applyTier(tier);
    return tier;
  }

  /// Restores existing purchases (for device changes / reinstalls).
  Future<SubscriptionTier> restorePurchases() async {
    final raw = await _channel.invokeMethod<String>('restorePurchases');
    final tier = _parseTier(raw ?? 'free');
    await _applyTier(tier);
    return tier;
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  static SubscriptionTier _parseTier(String s) {
    switch (s) {
      case 'premium': return SubscriptionTier.premium;
      case 'plus':    return SubscriptionTier.plus;
      default:        return SubscriptionTier.free;
    }
  }

  static String _tierString(SubscriptionTier t) {
    switch (t) {
      case SubscriptionTier.premium: return 'premium';
      case SubscriptionTier.plus:    return 'plus';
      case SubscriptionTier.free:    return 'free';
    }
  }
}
