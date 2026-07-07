/// Tunable economy for the reward system (Baustein 1: Quiz-Sterne).
///
/// ALL balancing lives here — change a number, rebuild, done. No schema change
/// needed to retune. The DB (reward_ledger) records what was actually granted,
/// so retuning only affects future awards, never rewrites history.
class RewardRules {
  RewardRules._();

  /// ⭐ per quiz question answered correctly — but only the FIRST time this
  /// profile ever answers this specific question correctly (re-takes give 0).
  static const int starsPerCorrectQuestion = 1;

  /// ⭐ bonus the first time a profile passes a whole quiz with EVERY question
  /// correct. Granted once per article, ever.
  static const int starsQuizAllCorrectBonus = 1;

  /// ⭐ the first time a profile earns anything in a new topic area
  /// (categoryTop). Granted once per area, ever. "Neues Thema" gives nothing —
  /// only a new *Themengebiet* counts.
  static const int starsNewArea = 3;

  /// Daily engagement milestones, counted as fully-passed quizzes (all-correct)
  /// completed *today*. Each milestone fires once per day.
  static const int dailyMilestone1Count = 5;
  static const int starsDailyMilestone1 = 3;
  static const int dailyMilestone2Count = 10;
  static const int starsDailyMilestone2 = 5;

  /// Anti-grinding: max ⭐ a profile can earn per calendar day. `null` = no cap.
  /// Question/quiz progress is still recorded past the cap (so cards/trophies
  /// unlock) — only the star grant is withheld.
  // Intentionally nullable so it can be set to `null` to disable the cap.
  // ignore: unnecessary_nullable_for_final_variable_declarations
  static const int? dailyCapStars = 80;
}
