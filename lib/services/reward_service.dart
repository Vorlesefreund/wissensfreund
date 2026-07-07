import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/collected_card.dart';
import 'license_cache_db.dart';
import 'profile_service.dart';

/// Why a grant happened — for later UI (confetti, "+3 ⭐ Neues Gebiet!").
enum RewardReason { question, quizAllCorrect, newArea, dailyMilestone1, dailyMilestone2 }

/// Result of a single reward action: which reasons fired and how many ⭐ each.
class RewardAward {
  final Map<RewardReason, int> grants;
  final bool cardEarned; // a new Sammelkarte was just collected

  const RewardAward(this.grants, {this.cardEarned = false});

  static const RewardAward empty = RewardAward({});

  int get totalStars => grants.values.fold(0, (a, b) => a + b);
  bool get isEmpty => totalStars == 0 && !cardEarned;
}

/// Central reward engine (Baustein 1: Quiz-Sterne-Ökonomie).
///
/// Balance is per active profile. All balancing lives in [RewardRules]; all
/// persistence + anti-abuse logic (dedup, daily cap, milestones) lives in
/// [LicenseCacheDb] transactions. This service is the thin, reactive front:
/// it caches the active profile's ⭐ balance and notifies the UI.
class RewardService extends ChangeNotifier {
  RewardService._();
  static final RewardService instance = RewardService._();

  int _stars = 0;
  int get stars => _stars;

  bool _wired = false;

  Future<void> initialize() async {
    if (!_wired) {
      ProfileService.instance.addListener(_onProfileChanged);
      _wired = true;
    }
    await _reload();
  }

  int? get _pid => ProfileService.instance.activeProfile?.id;

  void _onProfileChanged() => unawaited(_reload());

  Future<void> _reload() async {
    final pid = _pid;
    final next = pid == null ? 0 : await LicenseCacheDb.instance.getStars(pid);
    if (next != _stars) {
      _stars = next;
      notifyListeners();
    }
  }

  /// Call once per quiz question the child answers correctly. Grants ⭐ only the
  /// first time this profile ever gets this question right; also triggers the
  /// "neues Themengebiet" bonus. Safe to call on re-takes (no double reward).
  Future<RewardAward> onCorrectAnswer({
    required String articleId,
    required String topicArea,
    required String questionId,
  }) async {
    final pid = _pid;
    if (pid == null || articleId.isEmpty || questionId.isEmpty) {
      return RewardAward.empty;
    }
    final raw = await LicenseCacheDb.instance.awardForCorrectAnswer(
      profileId: pid,
      articleId: articleId,
      questionId: questionId,
      topicArea: topicArea,
    );
    return _apply(raw);
  }

  /// Call once when a quiz run finishes. [allCorrect] = every question right in
  /// this run. Grants the completion bonus + daily milestones (once each).
  Future<RewardAward> onQuizFinished({
    required String articleId,
    required String topicArea,
    required bool allCorrect,
    CollectedCard? card,
  }) async {
    final pid = _pid;
    if (pid == null || articleId.isEmpty) return RewardAward.empty;
    final res = await LicenseCacheDb.instance.awardForQuizFinish(
      profileId: pid,
      articleId: articleId,
      topicArea: topicArea,
      allCorrect: allCorrect,
      card: card,
    );
    return _apply(res.stars, cardEarned: res.cardEarned);
  }

  RewardAward _apply(Map<String, int> raw, {bool cardEarned = false}) {
    final grants = <RewardReason, int>{};
    raw.forEach((key, value) {
      final r = _reasonFromKey(key);
      if (r != null && value > 0) grants[r] = value;
    });
    final gained = grants.values.fold(0, (a, b) => a + b);
    if (gained > 0 || cardEarned) {
      _stars += gained;
      notifyListeners();
    }
    return RewardAward(grants, cardEarned: cardEarned);
  }

  static RewardReason? _reasonFromKey(String key) => switch (key) {
        'question' => RewardReason.question,
        'quiz_complete' => RewardReason.quizAllCorrect,
        'new_area' => RewardReason.newArea,
        'daily_5' => RewardReason.dailyMilestone1,
        'daily_10' => RewardReason.dailyMilestone2,
        _ => null,
      };

  @override
  void dispose() {
    if (_wired) ProfileService.instance.removeListener(_onProfileChanged);
    super.dispose();
  }
}
