import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import '../config/asset_config.dart';
import '../models/wf_article.dart';

class WfArticleIndexEntry {
  final String id;
  final String title;
  final String subtitle;
  final String emoji;
  final int ageLevel;
  final String themeColor;
  final String thumbUrl;
  final String categoryTop;
  final String categorySub;

  const WfArticleIndexEntry({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.emoji,
    required this.ageLevel,
    required this.themeColor,
    required this.thumbUrl,
    required this.categoryTop,
    required this.categorySub,
  });

  factory WfArticleIndexEntry.fromJson(Map<String, dynamic> j) =>
      WfArticleIndexEntry(
        id:          j['id']           as String? ?? '',
        title:       j['title']        as String? ?? '',
        subtitle:    j['subtitle']     as String? ?? '',
        emoji:       j['emoji']        as String? ?? '',
        ageLevel:    j['age_level']    as int?    ?? 2,
        themeColor:  j['theme_color']  as String? ?? '#4caf50',
        thumbUrl:    j['thumb_url']    as String? ?? '',
        categoryTop: j['category_top'] as String? ?? '',
        categorySub: j['category_sub'] as String? ?? '',
      );
}

class JsonArticleService extends ChangeNotifier {
  JsonArticleService._();
  static final JsonArticleService instance = JsonArticleService._();

  static const Duration _indexTtl = Duration(hours: 24);

  final http.Client _client = http.Client();
  Directory? _cacheDir;
  bool _initialized = false;

  // ── Public API ───────────────────────────────────────────────────────────────

  Future<void> initialize() async {
    if (_initialized) return;
    final docs = await getApplicationDocumentsDirectory();
    _cacheDir = Directory('${docs.path}/wf_articles');
    if (!await _cacheDir!.exists()) {
      await _cacheDir!.create(recursive: true);
    }
    _initialized = true;
    debugPrint('[JsonArticleService] cache dir: ${_cacheDir!.path}');
  }

  Future<List<WfArticleIndexEntry>> loadCategoryIndex(
      String categoryId) async {
    return _loadIndexFile('index/cat_$categoryId.json');
  }

  Future<List<WfArticleIndexEntry>> loadSubcategoryIndex(
      String subcategoryId) async {
    return _loadIndexFile('index/sub_$subcategoryId.json');
  }

  /// Loads index/level_{level}.json from the articles R2 bucket.
  Future<List<WfArticleIndexEntry>> loadLevelIndex(int level) async {
    await _ensureInit();
    final path = 'index/level_$level.json';
    final cacheFile = File('${_cacheDir!.path}/$path');
    if (await cacheFile.exists()) {
      final age = DateTime.now().difference((await cacheFile.stat()).modified);
      if (age < _indexTtl) {
        try {
          return _parseIndexResponse(await cacheFile.readAsString());
        } catch (e) {
          debugPrint('[JsonArticleService] level index cache parse error: $e');
        }
      }
    }
    final url = '${AssetConfig.r2ArticlesBaseUrl}/$path';
    try {
      final resp = await _client.get(Uri.parse(url));
      if (resp.statusCode == 404) return [];
      if (resp.statusCode != 200) {
        debugPrint('[JsonArticleService] HTTP ${resp.statusCode} for $path');
        return [];
      }
      final body = resp.body;
      await cacheFile.parent.create(recursive: true);
      await cacheFile.writeAsString(body);
      return _parseIndexResponse(body);
    } catch (e) {
      debugPrint('[JsonArticleService] level index network error: $e');
      if (await cacheFile.exists()) {
        try {
          return _parseIndexResponse(await cacheFile.readAsString());
        } catch (_) {}
      }
      return [];
    }
  }

  /// "biene_l2" → "biene"
  static String baseId(String articleId) {
    final idx = articleId.lastIndexOf('_l');
    return idx >= 0 ? articleId.substring(0, idx) : articleId;
  }

  /// "biene_l2" → 2
  static int levelFromId(String articleId) {
    final m = RegExp(r'_l(\d)$').firstMatch(articleId);
    return m != null ? int.parse(m.group(1)!) : 2;
  }

  Future<WfArticle?> loadArticle(String articleId) async {
    await _ensureInit();
    final cacheFile = File('${_cacheDir!.path}/articles/$articleId.json');
    if (await cacheFile.exists()) {
      try {
        final raw = await cacheFile.readAsString();
        final cached = WfArticle.fromJson(json.decode(raw) as Map<String, dynamic>);
        if (cached.images.isNotEmpty) return cached;
      } catch (e) {
        debugPrint('[JsonArticleService] cache parse error for $articleId: $e');
      }
    }
    // Fetch from R2
    final url = '${AssetConfig.r2ArticlesBaseUrl}/articles/$articleId.json';
    try {
      final resp = await _client.get(Uri.parse(url));
      if (resp.statusCode == 200) {
        final body = resp.body;
        final article =
            WfArticle.fromJson(json.decode(body) as Map<String, dynamic>);
        if (article.images.isEmpty) {
          final testArticle = await _loadFromAsset(articleId);
          if (testArticle != null && testArticle.images.isNotEmpty) {
            return testArticle;
          }
        }
        await cacheFile.parent.create(recursive: true);
        await cacheFile.writeAsString(body);
        return article;
      }
      debugPrint('[JsonArticleService] HTTP ${resp.statusCode} for $articleId');
    } catch (e) {
      debugPrint('[JsonArticleService] network error for $articleId: $e');
    }
    return _loadFromAsset(articleId);
  }

  Future<WfArticle?> _loadFromAsset(String articleId) async {
    try {
      final raw = await rootBundle.loadString('assets/test/$articleId.json');
      final parsed = json.decode(raw) as Map<String, dynamic>;
      return WfArticle.fromJson(parsed);
    } catch (e) {
      debugPrint('[JsonArticleService] asset load error for $articleId: $e');
      return null;
    }
  }

  String articleIdFor(String title, int ageLevel) =>
      '${_slugify(title)}_l$ageLevel';

  // ── Internal helpers ─────────────────────────────────────────────────────────

  Future<List<WfArticleIndexEntry>> _loadIndexFile(String path) async {
    await _ensureInit();
    final cacheFile = File('${_cacheDir!.path}/$path');
    // Use cache if fresh
    if (await cacheFile.exists()) {
      final age = DateTime.now().difference(
          (await cacheFile.stat()).modified);
      if (age < _indexTtl) {
        try {
          final raw = await cacheFile.readAsString();
          return _parseIndexList(raw);
        } catch (e) {
          debugPrint('[JsonArticleService] index parse error ($path): $e');
        }
      }
    }
    // Fetch from R2
    final url = '${AssetConfig.r2BaseUrl}/$path';
    try {
      final resp = await _client.get(Uri.parse(url));
      if (resp.statusCode == 404) return [];
      if (resp.statusCode != 200) {
        debugPrint('[JsonArticleService] HTTP ${resp.statusCode} for $path');
        return [];
      }
      final body = resp.body;
      await cacheFile.parent.create(recursive: true);
      await cacheFile.writeAsString(body);
      return _parseIndexList(body);
    } catch (e) {
      debugPrint('[JsonArticleService] network error ($path): $e');
      // Serve stale cache if available
      if (await cacheFile.exists()) {
        try {
          final raw = await cacheFile.readAsString();
          return _parseIndexList(raw);
        } catch (_) {}
      }
      return [];
    }
  }

  List<WfArticleIndexEntry> _parseIndexList(String body) {
    final data = json.decode(body);
    if (data is List) {
      return data
          .map((e) =>
              WfArticleIndexEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  // Handles both a raw JSON array and {"articles": [...]} wrapper (upload_articles.py format).
  List<WfArticleIndexEntry> _parseIndexResponse(String body) {
    final data = json.decode(body);
    final List<dynamic> list;
    if (data is List) {
      list = data;
    } else if (data is Map && data['articles'] is List) {
      list = data['articles'] as List<dynamic>;
    } else {
      return [];
    }
    return list
        .map((e) => WfArticleIndexEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> _ensureInit() async {
    if (!_initialized) await initialize();
  }

  static String _slugify(String title) {
    return title
        .toLowerCase()
        .replaceAll('ä', 'ae')
        .replaceAll('ö', 'oe')
        .replaceAll('ü', 'ue')
        .replaceAll('ß', 'ss')
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
  }
}
