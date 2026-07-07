import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/wissensfreund_provider.dart';
import '../services/json_article_service.dart';
import '../services/profile_service.dart';
import 'article_screen.dart';

class WfArticleListScreen extends StatefulWidget {
  const WfArticleListScreen({super.key});

  @override
  State<WfArticleListScreen> createState() => _WfArticleListScreenState();
}

class _WfArticleListScreenState extends State<WfArticleListScreen> {
  late int _level;
  List<WfArticleIndexEntry> _entries = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _level = ProfileService.instance.activeAgeLevel;
    _loadIndex();
  }

  Future<void> _loadIndex() async {
    setState(() => _loading = true);
    final entries = await JsonArticleService.instance.loadLevelIndex(_level);
    if (mounted) setState(() { _entries = entries; _loading = false; });
  }

  void _switchLevel(int level) {
    if (level == _level) return;
    setState(() => _level = level);
    _loadIndex();
  }

  Future<void> _openArticle(String articleId) async {
    final provider = context.read<WissensfreundProvider>();
    await provider.loadAndSpeakJsonArticle(articleId);
    if (!mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ArticleScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Neue Artikel'),
        centerTitle: false,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Row(
              children: [1, 2, 3].map((lvl) {
                final active = lvl == _level;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilledButton(
                    onPressed: () => _switchLevel(lvl),
                    style: FilledButton.styleFrom(
                      backgroundColor: active
                          ? Theme.of(context).colorScheme.primary
                          : Theme.of(context).colorScheme.surfaceVariant,
                      foregroundColor: active
                          ? Theme.of(context).colorScheme.onPrimary
                          : Theme.of(context).colorScheme.onSurfaceVariant,
                      minimumSize: const Size(52, 36),
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    child: Text('S$lvl',
                        style: const TextStyle(fontWeight: FontWeight.bold)),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _entries.isEmpty
              ? const Center(
                  child: Text('Keine Artikel gefunden.',
                      style: TextStyle(fontSize: 16)))
              : ListView.builder(
                  itemCount: _entries.length,
                  itemBuilder: (context, i) {
                    final e = _entries[i];
                    final articleId = '${JsonArticleService.baseId(e.id)}_l$_level';
                    return ListTile(
                      leading: Text(e.emoji,
                          style: const TextStyle(fontSize: 28)),
                      title: Text(e.title,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: e.subtitle.isNotEmpty ? Text(e.subtitle) : null,
                      onTap: () => _openArticle(articleId),
                    );
                  },
                ),
    );
  }
}
