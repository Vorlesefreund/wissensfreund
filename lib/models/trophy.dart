// Trophy/certificate model (Baustein 4). Everything here is DERIVED from the
// reward stats already recorded since Baustein 1 (area_stats), so no extra DB
// state is needed — a title/pokal is "earned" iff the counters clear a
// threshold. Retuning thresholds only changes future display, never history.

/// Per-topic-area progress (from the area_stats table).
class AreaStat {
  final String area; // = categoryTop, e.g. "Tiere"
  final int quizzesPassed;
  final int questionsCorrect;
  const AreaStat({
    required this.area,
    required this.quizzesPassed,
    required this.questionsCorrect,
  });
}

/// One of 5 ascending ranks within a topic area. Threshold = quizzes fully
/// passed (all questions correct) in that area.
class RankTier {
  final String name; // "Entdecker"
  final int threshold; // quizzes passed
  final String seal; // emoji seal on the certificate
  const RankTier(this.name, this.threshold, this.seal);
}

const List<RankTier> kRankTiers = [
  RankTier('Entdecker', 1, '🌱'),
  RankTier('Kenner', 5, '📖'),
  RankTier('Forscher', 10, '🔬'),
  RankTier('Experte', 20, '🎓'),
  RankTier('Legende', 40, '👑'),
];

/// The current standing in one area: which rank is reached and progress to next.
class AreaTitle {
  final String area;
  final int passed;
  final int tierIndex; // -1 = no rank yet
  final RankTier? current;
  final RankTier? next;

  const AreaTitle({
    required this.area,
    required this.passed,
    required this.tierIndex,
    required this.current,
    required this.next,
  });

  bool get hasRank => tierIndex >= 0;

  /// 0..1 toward the next rank (or 1.0 if maxed).
  double get progressToNext {
    if (next == null) return 1.0;
    final base = current?.threshold ?? 0;
    final span = next!.threshold - base;
    if (span <= 0) return 1.0;
    return ((passed - base) / span).clamp(0.0, 1.0);
  }

  static AreaTitle fromStat(AreaStat s) {
    var idx = -1;
    for (var i = 0; i < kRankTiers.length; i++) {
      if (s.quizzesPassed >= kRankTiers[i].threshold) idx = i;
    }
    return AreaTitle(
      area: s.area,
      passed: s.quizzesPassed,
      tierIndex: idx,
      current: idx >= 0 ? kRankTiers[idx] : null,
      next: idx + 1 < kRankTiers.length ? kRankTiers[idx + 1] : null,
    );
  }
}

/// Cross-area milestone pokal: earned when [requiredTier] is reached in at least
/// [requiredAreas] areas.
class Pokal {
  final String name;
  final String emoji;
  final int requiredTier; // 0 = Entdecker
  final int requiredAreas;
  const Pokal(this.name, this.emoji, this.requiredTier, this.requiredAreas);

  bool earnedBy(List<AreaTitle> titles) =>
      titles.where((t) => t.tierIndex >= requiredTier).length >= requiredAreas;

  /// How many areas already meet [requiredTier] (for progress display).
  int progressCount(List<AreaTitle> titles) =>
      titles.where((t) => t.tierIndex >= requiredTier).length;
}

const List<Pokal> kPokals = [
  Pokal('Allrounder Bronze', '🥉', 0, 3),
  Pokal('Allrounder Silber', '🥈', 0, 5),
  Pokal('Weltforscher', '🏆', 1, 3),
  Pokal('Universalgenie', '🌟', 2, 3),
];
