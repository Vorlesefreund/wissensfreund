import 'wf_article.dart';

enum ArticleSource { zim, json }

class RenderedImage {
  final int index;
  final String filename;   // ZIM: hash-key; JSON: commons filename
  final String? caption;
  final String? thumbUrl;  // JSON only
  final bool fromKlexikon;
  final String? author;
  final String? license;
  final String? sourceUrl;

  const RenderedImage({
    required this.index,
    required this.filename,
    this.caption,
    this.thumbUrl,
    required this.fromKlexikon,
    this.author,
    this.license,
    this.sourceUrl,
  });
}

class RenderedLink {
  final String text;
  final String target;
  final int startChar;
  final int endChar;

  const RenderedLink({
    required this.text,
    required this.target,
    required this.startChar,
    required this.endChar,
  });
}

class RenderedBox {
  final String type;       // "wow" | "fakt" | "stimmt_das" | "warnung"
  final String? headline;
  final String text;
  final bool revealMode;
  final bool? answer;
  final String? explanation;

  const RenderedBox({
    required this.type,
    this.headline,
    required this.text,
    this.revealMode = false,
    this.answer,
    this.explanation,
  });
}

class RenderedSentence {
  final String id;
  final String text;
  final int startChar;   // byte offset in RenderedArticle.plainText
  final int imageIndex;  // which image index to show alongside this sentence

  const RenderedSentence({
    required this.id,
    required this.text,
    required this.startChar,
    required this.imageIndex,
  });
}

class RenderedSection {
  final String id;
  final String heading;
  final List<RenderedSentence> sentences;
  final List<RenderedBox> boxes;

  const RenderedSection({
    required this.id,
    required this.heading,
    required this.sentences,
    required this.boxes,
  });
}

/// Unified article representation that both ZIM and JSON articles convert to.
///
/// The provider stores this and exposes its fields; the article screens render it.
/// ZIM articles leave subtitle/emoji/themeColor empty and quiz/ttsConfig null.
class RenderedArticle {
  final ArticleSource source;
  final String id;            // '' for ZIM; stable JSON article id (reward keying)
  final String title;
  final String subtitle;      // '' for ZIM
  final String emoji;         // '' for ZIM
  final String themeColor;    // '' for ZIM
  final String categoryTop;   // '' for ZIM; Themengebiet (reward "neues Gebiet")
  final String categorySub;   // '' for ZIM
  final String plainText;     // TTS-ready full text
  final List<RenderedSection> sections;
  final List<RenderedImage> images;
  final List<RenderedLink> links;
  final WfQuiz? quiz;         // JSON only
  final WfTtsConfig? ttsConfig; // JSON only
  final String sourceUrl;     // for Klexikon/Wikipedia attribution footer

  const RenderedArticle({
    required this.source,
    this.id = '',
    required this.title,
    this.subtitle = '',
    this.emoji = '',
    this.themeColor = '',
    this.categoryTop = '',
    this.categorySub = '',
    required this.plainText,
    required this.sections,
    required this.images,
    required this.links,
    this.quiz,
    this.ttsConfig,
    this.sourceUrl = '',
  });
}
