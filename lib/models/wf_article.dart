class WfArticleMeta {
  final String id;
  final String title;
  final String subtitle;
  final String emoji;
  final int ageLevel;
  final String pattern;
  final String themeColor;
  final int wordCount;
  final String sourceUrl;
  final String generatedAt;
  final String schemaVersion;
  final bool reviewFlag;
  final String categoryTop;
  final String categorySub;

  const WfArticleMeta({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.emoji,
    required this.ageLevel,
    required this.pattern,
    required this.themeColor,
    required this.wordCount,
    required this.sourceUrl,
    required this.generatedAt,
    required this.schemaVersion,
    required this.reviewFlag,
    required this.categoryTop,
    required this.categorySub,
  });

  factory WfArticleMeta.fromJson(Map<String, dynamic> j) => WfArticleMeta(
        id:            j['id']             as String? ?? '',
        title:         j['title']          as String? ?? '',
        subtitle:      j['subtitle']       as String? ?? '',
        emoji:         j['emoji']          as String? ?? '',
        ageLevel:      j['age_level']      as int?    ?? 2,
        pattern:       j['pattern']        as String? ?? '',
        themeColor:    j['theme_color']    as String? ?? '#4caf50',
        wordCount:     j['word_count']     as int?    ?? 0,
        sourceUrl:     j['source_url']     as String? ?? '',
        generatedAt:   j['generated_at']   as String? ?? '',
        schemaVersion: j['schema_version'] as String? ?? '',
        reviewFlag:    j['review_flag']    as bool?   ?? false,
        categoryTop:   j['category_top']   as String? ?? '',
        categorySub:   j['category_sub']   as String? ?? '',
      );
}

class WfImage {
  final int index;
  final String filename;
  final String alt;
  final String caption;
  final String license;
  final String licenseAuthor;
  final String sourceUrl;
  final String thumbUrl;
  final String? zimHash;

  const WfImage({
    required this.index,
    required this.filename,
    required this.alt,
    required this.caption,
    required this.license,
    required this.licenseAuthor,
    required this.sourceUrl,
    required this.thumbUrl,
    this.zimHash,
  });

  factory WfImage.fromJson(Map<String, dynamic> j) => WfImage(
        index:         j['index']          as int?    ?? 0,
        filename:      j['filename']       as String? ?? '',
        alt:           j['alt']            as String? ?? '',
        caption:       j['caption']        as String? ?? '',
        license:       j['license']        as String? ?? '',
        licenseAuthor: j['license_author'] as String? ?? '',
        sourceUrl:     j['source_url']     as String? ?? '',
        thumbUrl:      j['thumb_url']      as String?
                    ?? j['source_url']  as String? ?? '',
        zimHash:       j['zim_hash']       as String?,
      );
}

class WfSentence {
  final String id;
  final String text;
  final int imgIndex;

  const WfSentence({
    required this.id,
    required this.text,
    required this.imgIndex,
  });

  factory WfSentence.fromJson(Map<String, dynamic> j) => WfSentence(
        id:       j['id']        as String? ?? '',
        text:     j['text']      as String? ?? '',
        imgIndex: j['img_index'] as int?    ?? 0,
      );
}

class WfBox {
  final String type;
  final String? headline;
  final String text;
  final bool revealMode;
  final bool? answer;        // stimmt_das: true = correct, false = incorrect
  final String? explanation; // stimmt_das: shown after reveal

  const WfBox({
    required this.type,
    this.headline,
    required this.text,
    this.revealMode = false,
    this.answer,
    this.explanation,
  });

  factory WfBox.fromJson(Map<String, dynamic> j) => WfBox(
        type:        j['type']        as String? ?? '',
        headline:    j['headline']    as String?,
        text:        j['text']        as String? ?? '',
        revealMode:  j['reveal_mode'] == 'auto',
        answer:      j['answer']      as bool?,
        explanation: j['reveal_text'] as String?,
      );
}

class WfTable {
  final String caption;
  final List<List<String>> rows;

  const WfTable({required this.caption, required this.rows});

  factory WfTable.fromJson(Map<String, dynamic> j) => WfTable(
        caption: j['caption'] as String? ?? '',
        rows: (j['rows'] as List<dynamic>? ?? [])
            .map((r) => (r as List<dynamic>).map((c) => c as String).toList())
            .toList(),
      );
}

class WfSection {
  final String id;
  final String heading;
  final String sectionRole;
  final List<WfSentence> sentences;
  final List<WfBox> boxes;
  final WfTable? table;

  const WfSection({
    required this.id,
    required this.heading,
    required this.sectionRole,
    required this.sentences,
    required this.boxes,
    this.table,
  });

  factory WfSection.fromJson(Map<String, dynamic> j) => WfSection(
        id:          j['id']           as String? ?? '',
        heading:     j['heading']      as String? ?? '',
        sectionRole: j['section_role'] as String? ?? '',
        sentences: (j['sentences'] as List<dynamic>? ?? [])
            .map((s) => WfSentence.fromJson(s as Map<String, dynamic>))
            .toList(),
        boxes: (j['boxes'] as List<dynamic>? ?? [])
            .map((b) => WfBox.fromJson(b as Map<String, dynamic>))
            .toList(),
        table: j['table'] != null
            ? WfTable.fromJson(j['table'] as Map<String, dynamic>)
            : null,
      );
}

class WfQuizOption {
  final String key;
  final String text;

  const WfQuizOption({required this.key, required this.text});

  factory WfQuizOption.fromJson(Map<String, dynamic> j) => WfQuizOption(
        key:  j['key']  as String? ?? '',
        text: j['text'] as String? ?? '',
      );
}

class WfQuizQuestion {
  final String id;
  final String question;
  final List<WfQuizOption> options;
  final String correctKey;
  final String explanation;
  final bool imageQuiz;

  const WfQuizQuestion({
    required this.id,
    required this.question,
    required this.options,
    required this.correctKey,
    required this.explanation,
    required this.imageQuiz,
  });

  factory WfQuizQuestion.fromJson(Map<String, dynamic> j) => WfQuizQuestion(
        id:          j['id']          as String? ?? '',
        question:    j['text']        as String? ?? '',
        options: (j['options'] as List<dynamic>? ?? [])
            .map((o) => WfQuizOption.fromJson(o as Map<String, dynamic>))
            .toList(),
        correctKey:  j['correct_key'] as String? ?? '',
        explanation: j['explanation'] as String? ?? '',
        imageQuiz:   j['image_quiz']  as bool?   ?? false,
      );
}

class WfQuiz {
  final String heading;
  final List<WfQuizQuestion> questions;

  const WfQuiz({required this.heading, required this.questions});

  factory WfQuiz.fromJson(Map<String, dynamic> j) => WfQuiz(
        heading: j['heading'] as String? ?? '',
        questions: (j['questions'] as List<dynamic>? ?? [])
            .map((q) => WfQuizQuestion.fromJson(q as Map<String, dynamic>))
            .toList(),
      );
}

class WfTtsConfig {
  final double readingSpeedFactor;
  final int pauseAfterHeadingMs;
  final int pauseAfterSentenceMs;
  final int pauseBeforeQuizMs;

  const WfTtsConfig({
    required this.readingSpeedFactor,
    required this.pauseAfterHeadingMs,
    required this.pauseAfterSentenceMs,
    required this.pauseBeforeQuizMs,
  });

  factory WfTtsConfig.fromJson(Map<String, dynamic> j) => WfTtsConfig(
        readingSpeedFactor:   (j['reading_speed_factor']    as num? ?? 1.0).toDouble(),
        pauseAfterHeadingMs:   j['pause_after_heading_ms']  as int? ?? 400,
        pauseAfterSentenceMs:  j['pause_after_sentence_ms'] as int? ?? 150,
        pauseBeforeQuizMs:     j['pause_before_quiz_ms']    as int? ?? 800,
      );
}

class WfArticle {
  final WfArticleMeta meta;
  final List<WfImage> images;
  final List<WfSection> sections;
  final WfQuiz quiz;
  final WfTtsConfig ttsConfig;

  const WfArticle({
    required this.meta,
    required this.images,
    required this.sections,
    required this.quiz,
    required this.ttsConfig,
  });

  factory WfArticle.fromJson(Map<String, dynamic> j) => WfArticle(
        meta: WfArticleMeta.fromJson(j['meta'] as Map<String, dynamic>),
        images: (j['images'] as List<dynamic>? ?? [])
            .map((i) => WfImage.fromJson(i as Map<String, dynamic>))
            .toList(),
        sections: (j['sections'] as List<dynamic>? ?? [])
            .map((s) => WfSection.fromJson(s as Map<String, dynamic>))
            .toList(),
        quiz: WfQuiz.fromJson(j['quiz'] as Map<String, dynamic>? ?? {}),
        ttsConfig: WfTtsConfig.fromJson(
            j['tts_config'] as Map<String, dynamic>? ?? {}),
      );
}
