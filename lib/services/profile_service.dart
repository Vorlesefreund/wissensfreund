import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'license_cache_db.dart';

class UserProfile {
  final int id;
  final String name;
  final int birthYear;
  final String avatarId;
  final String languageLevel; // 'easy' | 'medium' | 'advanced'
  final DateTime? createdAt;
  final DateTime? lastUsedAt;

  const UserProfile({
    required this.id,
    required this.name,
    required this.birthYear,
    required this.avatarId,
    required this.languageLevel,
    this.createdAt,
    this.lastUsedAt,
  });

  int get age {
    final now = DateTime.now();
    int age = now.year - birthYear;
    return age.clamp(0, 99);
  }

  UserProfile copyWith({
    String? name,
    int? birthYear,
    String? avatarId,
    String? languageLevel,
    DateTime? lastUsedAt,
  }) => UserProfile(
    id:            id,
    name:          name          ?? this.name,
    birthYear:     birthYear     ?? this.birthYear,
    avatarId:      avatarId      ?? this.avatarId,
    languageLevel: languageLevel ?? this.languageLevel,
    createdAt:     createdAt,
    lastUsedAt:    lastUsedAt    ?? this.lastUsedAt,
  );

  Map<String, dynamic> toMap() => {
    'name':           name,
    'birth_year':     birthYear,
    'avatar_id':      avatarId,
    'language_level': languageLevel,
    'created_at':     createdAt?.toIso8601String(),
    'last_used_at':   lastUsedAt?.toIso8601String(),
  };

  static UserProfile fromMap(Map<String, dynamic> m) => UserProfile(
    id:            m['id'] as int,
    name:          m['name'] as String,
    birthYear:     m['birth_year'] as int,
    avatarId:      m['avatar_id'] as String,
    languageLevel: m['language_level'] as String,
    createdAt:     m['created_at'] != null
        ? DateTime.tryParse(m['created_at'] as String)
        : null,
    lastUsedAt:    m['last_used_at'] != null
        ? DateTime.tryParse(m['last_used_at'] as String)
        : null,
  );
}

/// Manages user profiles and the active profile selection.
///
/// Profile-scoped data (history, favorites, usage stats) is stored in
/// LicenseCacheDb with profile_id. Global settings (parental lock,
/// data limits, kiosk mode) are NOT profile-scoped.
class ProfileService extends ChangeNotifier {
  ProfileService._();
  static final ProfileService instance = ProfileService._();

  static const _prefKey = 'active_profile_id';

  List<UserProfile> _profiles = [];
  UserProfile? _activeProfile;

  List<UserProfile> get profiles => List.unmodifiable(_profiles);
  UserProfile? get activeProfile => _activeProfile;
  bool get hasProfiles => _profiles.isNotEmpty;

  // ── Initialization ────────────────────────────────────────────────────────────

  Future<void> initialize() async {
    await _loadProfiles();
    await _restoreActiveProfile();
  }

  Future<void> _loadProfiles() async {
    _profiles = await LicenseCacheDb.instance.getAllProfiles();
  }

  Future<void> _restoreActiveProfile() async {
    final prefs = await SharedPreferences.getInstance();
    final savedId = prefs.getInt(_prefKey);
    if (savedId != null) {
      try {
        _activeProfile = _profiles.firstWhere((p) => p.id == savedId);
      } catch (_) {
        _activeProfile = _profiles.isNotEmpty ? _profiles.first : null;
      }
    } else if (_profiles.isNotEmpty) {
      _activeProfile = _profiles.first;
    }
  }

  // ── Active profile ────────────────────────────────────────────────────────────

  Future<void> setActiveProfile(UserProfile profile) async {
    _activeProfile = profile.copyWith(lastUsedAt: DateTime.now());
    await LicenseCacheDb.instance.updateProfile(_activeProfile!);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_prefKey, profile.id);
    // Refresh list so lastUsedAt is current
    await _loadProfiles();
    notifyListeners();
  }

  // ── CRUD ──────────────────────────────────────────────────────────────────────

  Future<UserProfile> createProfile({
    required String name,
    required int birthYear,
    required String avatarId,
    required String languageLevel,
  }) async {
    final profile = await LicenseCacheDb.instance.insertProfile(
      name:          name,
      birthYear:     birthYear,
      avatarId:      avatarId,
      languageLevel: languageLevel,
    );
    _profiles.add(profile);
    notifyListeners();
    return profile;
  }

  Future<void> updateProfile(UserProfile profile) async {
    await LicenseCacheDb.instance.updateProfile(profile);
    final idx = _profiles.indexWhere((p) => p.id == profile.id);
    if (idx >= 0) _profiles[idx] = profile;
    if (_activeProfile?.id == profile.id) _activeProfile = profile;
    notifyListeners();
  }

  Future<void> deleteProfile(int profileId) async {
    await LicenseCacheDb.instance.deleteProfile(profileId);
    _profiles.removeWhere((p) => p.id == profileId);
    if (_activeProfile?.id == profileId) {
      _activeProfile = _profiles.isNotEmpty ? _profiles.first : null;
      final prefs = await SharedPreferences.getInstance();
      if (_activeProfile != null) {
        await prefs.setInt(_prefKey, _activeProfile!.id);
      } else {
        await prefs.remove(_prefKey);
      }
    }
    notifyListeners();
  }

  // ── Article history ───────────────────────────────────────────────────────────

  Future<void> recordArticleOpened(String articleTitle) async {
    final pid = _activeProfile?.id;
    if (pid == null) return;
    await LicenseCacheDb.instance.recordArticleHistory(
      profileId:    pid,
      articleTitle: articleTitle,
    );
  }

  Future<List<String>> getRecentArticles({int limit = 20}) async {
    final pid = _activeProfile?.id;
    if (pid == null) return [];
    return LicenseCacheDb.instance.getArticleHistory(profileId: pid, limit: limit);
  }

  // ── Favorites ─────────────────────────────────────────────────────────────────

  Future<void> toggleFavorite(String articleTitle) async {
    final pid = _activeProfile?.id;
    if (pid == null) return;
    final isFav = await LicenseCacheDb.instance.isFavorite(
      profileId: pid, articleTitle: articleTitle,
    );
    if (isFav) {
      await LicenseCacheDb.instance.removeFavorite(
        profileId: pid, articleTitle: articleTitle,
      );
    } else {
      await LicenseCacheDb.instance.addFavorite(
        profileId: pid, articleTitle: articleTitle,
      );
    }
    notifyListeners();
  }

  Future<bool> isFavorite(String articleTitle) async {
    final pid = _activeProfile?.id;
    if (pid == null) return false;
    return LicenseCacheDb.instance.isFavorite(
      profileId: pid, articleTitle: articleTitle,
    );
  }

  Future<List<String>> getFavorites() async {
    final pid = _activeProfile?.id;
    if (pid == null) return [];
    return LicenseCacheDb.instance.getFavorites(profileId: pid);
  }
}
