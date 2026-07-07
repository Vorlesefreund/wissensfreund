/// A collectible card (Sammelkarte), earned by passing an article's quiz with
/// every question correct. Keyed per topic ([cardId] = base id, e.g. "biene"),
/// not per level — so "biene_l2" and "biene_l3" map to the same card.
class CollectedCard {
  final String cardId;     // topic base id, e.g. "biene"
  final String articleId;  // the level article that earned it, e.g. "biene_l2"
  final String title;
  final String emoji;
  final String themeColor; // hex, e.g. "#4caf50" — offline card face
  final String thumbUrl;   // main image CDN url ('' if none)
  final String fact;       // "Fakt/Wow"-box text — card back ('' if none)
  final DateTime? earnedAt;

  const CollectedCard({
    required this.cardId,
    required this.articleId,
    required this.title,
    required this.emoji,
    required this.themeColor,
    required this.thumbUrl,
    required this.fact,
    this.earnedAt,
  });

  Map<String, dynamic> toMap(int profileId, String nowIso) => {
        'profile_id': profileId,
        'card_id': cardId,
        'article_id': articleId,
        'title': title,
        'emoji': emoji,
        'theme_color': themeColor,
        'thumb_url': thumbUrl,
        'fact': fact,
        'earned_at': nowIso,
      };

  static CollectedCard fromMap(Map<String, dynamic> m) => CollectedCard(
        cardId: m['card_id'] as String? ?? '',
        articleId: m['article_id'] as String? ?? '',
        title: m['title'] as String? ?? '',
        emoji: m['emoji'] as String? ?? '',
        themeColor: m['theme_color'] as String? ?? '#4caf50',
        thumbUrl: m['thumb_url'] as String? ?? '',
        fact: m['fact'] as String? ?? '',
        earnedAt: m['earned_at'] != null
            ? DateTime.tryParse(m['earned_at'] as String)
            : null,
      );
}
