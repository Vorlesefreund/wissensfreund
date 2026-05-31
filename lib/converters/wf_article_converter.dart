import '../models/rendered_article.dart';
import '../models/wf_article.dart';

/// Converts a [WfArticle] (from JSON pipeline) to [RenderedArticle].
///
/// Builds [plainText] by concatenating all sentence texts so the existing
/// TTS engine works unchanged. Each [RenderedSentence.startChar] records
/// the exact offset in [plainText] for TTS cursor sync.
class WfArticleConverter {
  WfArticleConverter._();

  static RenderedArticle convert(WfArticle article) {
    final buffer = StringBuffer();
    final renderedSections = <RenderedSection>[];

    for (final sec in article.sections) {
      if (sec.heading.isNotEmpty) {
        buffer.write('${sec.heading}\n');
      }

      final renderedSentences = <RenderedSentence>[];
      for (final s in sec.sentences) {
        final start = buffer.length;
        buffer.write(s.text);
        if (!s.text.endsWith(' ')) buffer.write(' ');
        renderedSentences.add(RenderedSentence(
          id:         s.id,
          text:       s.text,
          startChar:  start,
          imageIndex: s.imgIndex,
        ));
      }

      renderedSections.add(RenderedSection(
        id:        sec.id,
        heading:   sec.heading,
        sentences: renderedSentences,
        boxes: sec.boxes
            .map((b) => RenderedBox(
                  type:       b.type,
                  headline:   b.headline,
                  text:       b.text,
                  revealMode: b.revealMode,
                  revealText: b.revealText,
                ))
            .toList(),
      ));
    }

    final renderedImages = article.images.map((img) => RenderedImage(
          index:        img.index,
          filename:     img.filename,
          caption:      img.caption.isNotEmpty ? img.caption : null,
          thumbUrl:     img.thumbUrl.isNotEmpty ? img.thumbUrl : null,
          fromKlexikon: false,
          author:       img.licenseAuthor.isNotEmpty ? img.licenseAuthor : null,
          license:      img.license.isNotEmpty ? img.license : null,
          sourceUrl:    img.sourceUrl.isNotEmpty ? img.sourceUrl : null,
        )).toList();

    return RenderedArticle(
      source:     ArticleSource.json,
      title:      article.meta.title,
      subtitle:   article.meta.subtitle,
      emoji:      article.meta.emoji,
      themeColor: article.meta.themeColor,
      plainText:  buffer.toString().trimRight(),
      sections:   renderedSections,
      images:     renderedImages,
      links:      const [],
      quiz:       article.quiz.questions.isEmpty ? null : article.quiz,
      ttsConfig:  article.ttsConfig,
      sourceUrl:  article.meta.sourceUrl,
    );
  }
}
