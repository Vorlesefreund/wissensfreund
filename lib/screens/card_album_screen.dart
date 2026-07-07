import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../models/collected_card.dart';
import '../services/hires_image_service.dart';
import '../services/json_article_service.dart';
import '../services/license_cache_db.dart';
import '../services/network_service.dart';
import '../services/profile_service.dart';

/// Sammelkarten-Album. Shows every topic at the child's level as a card slot:
/// collected cards show image + title (tap to flip to the fact), missing cards
/// show a silhouette so the child sees what's left to discover.
class CardAlbumScreen extends StatefulWidget {
  const CardAlbumScreen({super.key});

  @override
  State<CardAlbumScreen> createState() => _CardAlbumScreenState();
}

class _CardAlbumScreenState extends State<CardAlbumScreen> {
  late int _level;
  List<WfArticleIndexEntry> _catalog = [];
  Map<String, CollectedCard> _owned = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _level = ProfileService.instance.activeAgeLevel;
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final pid = ProfileService.instance.activeProfile?.id;
    final catalog = await JsonArticleService.instance.loadLevelIndex(_level);
    final owned = <String, CollectedCard>{};
    if (pid != null) {
      for (final c in await LicenseCacheDb.instance.getCollectedCards(pid)) {
        owned[c.cardId] = c;
      }
    }
    if (mounted) {
      setState(() {
        _catalog = catalog;
        _owned = owned;
        _loading = false;
      });
    }
  }

  void _switchLevel(int level) {
    if (level == _level) return;
    setState(() => _level = level);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final ownedCount = _catalog
        .where((e) => _owned.containsKey(JsonArticleService.baseId(e.id)))
        .length;
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(
        title: const Text('Sammelkarten'),
        centerTitle: false,
        actions: [
          if (!_loading && _catalog.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(
                child: Text(
                  '$ownedCount / ${_catalog.length}',
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.bold),
                ),
              ),
            ),
        ],
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
                          : Theme.of(context).colorScheme.surfaceContainerHighest,
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
          : _catalog.isEmpty
              ? const Center(
                  child: Text('Noch keine Karten für diese Stufe.',
                      style: TextStyle(fontSize: 16)))
              : GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate:
                      const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    childAspectRatio: 0.70,
                    crossAxisSpacing: 14,
                    mainAxisSpacing: 14,
                  ),
                  itemCount: _catalog.length,
                  itemBuilder: (context, i) {
                    final e = _catalog[i];
                    final card = _owned[JsonArticleService.baseId(e.id)];
                    return _AlbumTile(
                      entry: e,
                      card: card,
                      onTap: card == null
                          ? () => _showLocked(context, e)
                          : () => _showCard(context, e, card),
                    );
                  },
                ),
    );
  }

  void _showLocked(BuildContext context, WfArticleIndexEntry e) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text('„${e.title}" — löse das Quiz ganz richtig, um die Karte zu bekommen!'),
        duration: const Duration(seconds: 3),
      ));
  }

  void _showCard(
      BuildContext context, WfArticleIndexEntry e, CollectedCard card) {
    showDialog(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.6),
      builder: (_) => _CardDetailDialog(entry: e, card: card),
    );
  }
}

/// One grid slot: collected (image + title) or a locked silhouette.
class _AlbumTile extends StatelessWidget {
  final WfArticleIndexEntry entry;
  final CollectedCard? card;
  final VoidCallback onTap;
  const _AlbumTile({required this.entry, required this.card, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final owned = card != null;
    final bg = _parseHexColor(entry.themeColor);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: owned ? Colors.white : const Color(0xFFEDE7DD),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: owned ? bg.withValues(alpha: 0.5) : const Color(0xFFD8CFC2),
            width: 1.5,
          ),
          boxShadow: owned
              ? [
                  BoxShadow(
                    color: bg.withValues(alpha: 0.18),
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ]
              : null,
        ),
        clipBehavior: Clip.antiAlias,
        child: owned
            ? Column(
                children: [
                  Expanded(
                    child: _CardThumb(
                      thumbUrl: entry.thumbUrl,
                      emoji: entry.emoji,
                      bg: bg,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 8),
                    child: Text(
                      entry.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              )
            : Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Text('❓', style: TextStyle(fontSize: 40, color: Color(0xFFB0A695))),
                  SizedBox(height: 8),
                  Text('Noch nicht\nentdeckt',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 12,
                          color: Color(0xFF9A8F7E),
                          fontWeight: FontWeight.w600)),
                ],
              ),
      ),
    );
  }
}

/// Card face image: tries the CDN thumb (network-gated + session-cached),
/// falls back to the emoji on the theme color when offline/unavailable.
class _CardThumb extends StatefulWidget {
  final String thumbUrl;
  final String emoji;
  final Color bg;
  const _CardThumb({required this.thumbUrl, required this.emoji, required this.bg});

  @override
  State<_CardThumb> createState() => _CardThumbState();
}

class _CardThumbState extends State<_CardThumb> {
  static final Map<String, Uint8List> _cache = {};
  Uint8List? _bytes;

  @override
  void initState() {
    super.initState();
    _bytes = _cache[widget.thumbUrl];
    if (_bytes == null && widget.thumbUrl.isNotEmpty) _fetch();
  }

  Future<void> _fetch() async {
    final allowed = await NetworkService.instance.isContentFetchAllowed();
    if (!allowed) return;
    final bytes = await HiResImageService.instance.fetchUrlBytes(widget.thumbUrl);
    if (bytes != null) {
      _cache[widget.thumbUrl] = bytes;
      if (mounted) setState(() => _bytes = bytes);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_bytes != null) {
      return Image.memory(_bytes!, fit: BoxFit.cover, width: double.infinity);
    }
    return Container(
      width: double.infinity,
      color: widget.bg.withValues(alpha: 0.12),
      alignment: Alignment.center,
      child: Text(widget.emoji.isNotEmpty ? widget.emoji : '🃏',
          style: const TextStyle(fontSize: 48)),
    );
  }
}

/// Full card dialog: a flip card (front = image + title, back = "Wusstest du?").
class _CardDetailDialog extends StatelessWidget {
  final WfArticleIndexEntry entry;
  final CollectedCard card;
  const _CardDetailDialog({required this.entry, required this.card});

  @override
  Widget build(BuildContext context) {
    final bg = _parseHexColor(entry.themeColor);
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 260,
            height: 360,
            child: _FlipCard(
              front: _CardFront(entry: entry, bg: bg),
              back: _CardBack(card: card, bg: bg),
            ),
          ),
          const SizedBox(height: 12),
          const Text('Tippe die Karte zum Umdrehen',
              style: TextStyle(color: Colors.white, fontSize: 13)),
        ],
      ),
    );
  }
}

class _CardFront extends StatelessWidget {
  final WfArticleIndexEntry entry;
  final Color bg;
  const _CardFront({required this.entry, required this.bg});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: bg, width: 3),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.3), blurRadius: 16),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Expanded(
            child: _CardThumb(
                thumbUrl: entry.thumbUrl, emoji: entry.emoji, bg: bg),
          ),
          Container(
            width: double.infinity,
            color: bg.withValues(alpha: 0.12),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            child: Text(
              entry.title,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}

class _CardBack extends StatelessWidget {
  final CollectedCard card;
  final Color bg;
  const _CardBack({required this.card, required this.bg});

  @override
  Widget build(BuildContext context) {
    final fact = card.fact.trim();
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [bg.withValues(alpha: 0.95), bg.withValues(alpha: 0.7)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.6), width: 3),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.3), blurRadius: 16),
        ],
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Wusstest du?',
              style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: Colors.white)),
          const SizedBox(height: 12),
          Expanded(
            child: SingleChildScrollView(
              child: Text(
                fact.isNotEmpty
                    ? fact
                    : 'Zu dieser Karte gibt es noch keinen Extra-Fakt.',
                style: const TextStyle(
                    fontSize: 16, height: 1.4, color: Colors.white),
              ),
            ),
          ),
          Align(
            alignment: Alignment.bottomRight,
            child: Text(card.title,
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Colors.white.withValues(alpha: 0.85))),
          ),
        ],
      ),
    );
  }
}

/// Tap to flip between [front] and [back] with a Y-axis rotation.
class _FlipCard extends StatefulWidget {
  final Widget front;
  final Widget back;
  const _FlipCard({required this.front, required this.back});

  @override
  State<_FlipCard> createState() => _FlipCardState();
}

class _FlipCardState extends State<_FlipCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 420));

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _flip() {
    if (_ctrl.isAnimating) return;
    _ctrl.value < 0.5 ? _ctrl.forward() : _ctrl.reverse();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _flip,
      child: AnimatedBuilder(
        animation: _ctrl,
        builder: (context, _) {
          final angle = _ctrl.value * 3.14159265;
          final showFront = angle <= 1.5707963;
          final transform = Matrix4.identity()
            ..setEntry(3, 2, 0.001)
            ..rotateY(angle);
          return Transform(
            alignment: Alignment.center,
            transform: transform,
            child: showFront
                ? widget.front
                : Transform(
                    alignment: Alignment.center,
                    transform: Matrix4.identity()..rotateY(3.14159265),
                    child: widget.back,
                  ),
          );
        },
      ),
    );
  }
}

Color _parseHexColor(String hex) {
  var h = hex.replaceAll('#', '').trim();
  if (h.length == 6) h = 'FF$h';
  final v = int.tryParse(h, radix: 16);
  return v == null ? const Color(0xFF4CAF50) : Color(v);
}
