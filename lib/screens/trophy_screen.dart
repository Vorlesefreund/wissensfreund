import 'package:flutter/material.dart';

import '../models/trophy.dart';
import '../services/license_cache_db.dart';
import '../services/profile_service.dart';

/// Trophäen & Urkunden (Baustein 4). Reads area_stats for the active profile and
/// renders cross-area pokals + per-area certificates with progress — all derived,
/// no dedicated art or DB state.
class TrophyScreen extends StatefulWidget {
  const TrophyScreen({super.key});

  @override
  State<TrophyScreen> createState() => _TrophyScreenState();
}

class _TrophyScreenState extends State<TrophyScreen> {
  List<AreaTitle> _titles = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final pid = ProfileService.instance.activeProfile?.id;
    final stats =
        pid == null ? <AreaStat>[] : await LicenseCacheDb.instance.getAreaStats(pid);
    final titles = stats
        .where((s) => s.area.isNotEmpty)
        .map(AreaTitle.fromStat)
        .toList()
      ..sort((a, b) {
        if (a.tierIndex != b.tierIndex) return b.tierIndex.compareTo(a.tierIndex);
        return b.passed.compareTo(a.passed);
      });
    if (mounted) {
      setState(() {
        _titles = titles;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(title: const Text('Trophäen & Urkunden'), centerTitle: false),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _titles.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Text(
                      'Noch keine Trophäen.\nLöse Quizze, um Urkunden und Pokale zu sammeln!',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 16, color: Color(0xFF6D6257)),
                    ),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    const _SectionHeader('🏅 Pokale'),
                    const SizedBox(height: 10),
                    _PokalRow(titles: _titles),
                    const SizedBox(height: 24),
                    const _SectionHeader('📜 Urkunden'),
                    const SizedBox(height: 10),
                    ..._titles.map((t) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _CertificateCard(title: t),
                        )),
                  ],
                ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String text;
  const _SectionHeader(this.text);

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: const TextStyle(
            fontSize: 20, fontWeight: FontWeight.w900, color: Color(0xFF2E7D32)),
      );
}

class _PokalRow extends StatelessWidget {
  final List<AreaTitle> titles;
  const _PokalRow({required this.titles});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: kPokals.map((p) {
        final earned = p.earnedBy(titles);
        return _PokalBadge(
          pokal: p,
          earned: earned,
          progress: p.progressCount(titles),
        );
      }).toList(),
    );
  }
}

class _PokalBadge extends StatelessWidget {
  final Pokal pokal;
  final bool earned;
  final int progress;
  const _PokalBadge(
      {required this.pokal, required this.earned, required this.progress});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 104,
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
      decoration: BoxDecoration(
        color: earned ? const Color(0xFFFFF3D6) : const Color(0xFFEDE7DD),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: earned ? const Color(0xFFF0C36D) : const Color(0xFFD8CFC2),
          width: 1.5,
        ),
      ),
      child: Column(
        children: [
          Opacity(
            opacity: earned ? 1.0 : 0.35,
            child: Text(pokal.emoji, style: const TextStyle(fontSize: 38)),
          ),
          const SizedBox(height: 6),
          Text(
            pokal.name,
            textAlign: TextAlign.center,
            maxLines: 2,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: earned ? const Color(0xFF9A6B00) : const Color(0xFF9A8F7E),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            earned ? 'Erreicht!' : '$progress/${pokal.requiredAreas} Gebiete',
            style: TextStyle(
              fontSize: 10,
              color: earned ? const Color(0xFF2E7D32) : const Color(0xFF9A8F7E),
            ),
          ),
        ],
      ),
    );
  }
}

class _CertificateCard extends StatelessWidget {
  final AreaTitle title;
  const _CertificateCard({required this.title});

  @override
  Widget build(BuildContext context) {
    final ranked = title.hasRank;
    final seal = title.current?.seal ?? '🔒';
    final rankName = title.current?.name ?? 'Noch kein Rang';
    final next = title.next;
    final remaining = next != null ? (next.threshold - title.passed) : 0;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ranked ? const Color(0xFFFFFDF6) : const Color(0xFFF3EFE7),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ranked ? const Color(0xFFD9C48A) : const Color(0xFFD8CFC2),
          width: ranked ? 2 : 1.5,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: ranked ? const Color(0xFFFFF3D6) : const Color(0xFFE7E0D5),
              shape: BoxShape.circle,
              border: Border.all(
                color: ranked ? const Color(0xFFE0C377) : const Color(0xFFCFC5B6),
                width: 2,
              ),
            ),
            child: Text(seal, style: const TextStyle(fontSize: 28)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  rankName,
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                    color: ranked ? const Color(0xFF8A6D1F) : const Color(0xFF9A8F7E),
                  ),
                ),
                Text(
                  'Gebiet: ${title.area}',
                  style: const TextStyle(fontSize: 13, color: Color(0xFF6D6257)),
                ),
                const SizedBox(height: 8),
                if (next != null) ...[
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(
                      value: title.progressToNext,
                      minHeight: 7,
                      backgroundColor: const Color(0xFFE7E0D5),
                      valueColor: const AlwaysStoppedAnimation(Color(0xFF66A759)),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Noch $remaining ${remaining == 1 ? 'Quiz' : 'Quizze'} bis „${next.name}"',
                    style: const TextStyle(fontSize: 12, color: Color(0xFF6D6257)),
                  ),
                ] else
                  const Text(
                    '👑 Höchster Rang erreicht!',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF2E7D32)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
