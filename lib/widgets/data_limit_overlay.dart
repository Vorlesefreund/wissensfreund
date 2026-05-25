import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/data_limit_overlay_service.dart';
import '../services/license_cache_db.dart';
import '../services/network_settings_service.dart';
import '../services/parental_lock_service.dart';

/// Fullscreen overlay shown when the child has reached a data limit.
/// Rendered in main.dart's _AppShell Stack — always above the app content.
class DataLimitOverlay extends StatelessWidget {
  const DataLimitOverlay({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<DataLimitOverlayService>(
      builder: (_, service, __) {
        if (!service.isVisible) return const SizedBox.shrink();
        return _DataLimitContent(service: service);
      },
    );
  }
}

// ── Phases ────────────────────────────────────────────────────────────────────

enum _Phase { loading, locked, unlocked, adjustingDaily, adjustingMonthly }

class _DataLimitContent extends StatefulWidget {
  final DataLimitOverlayService service;
  const _DataLimitContent({required this.service});

  @override
  State<_DataLimitContent> createState() => _DataLimitContentState();
}

class _DataLimitContentState extends State<_DataLimitContent> {
  _Phase _phase = _Phase.loading;

  int _dailyUsedBytes   = 0;
  int _monthlyUsedBytes = 0;
  int _dailyLimitMb     = 0;
  int _monthlyLimitMb   = 0;
  String _connType      = 'wifi';

  int _selectedDailyMb   = 0;
  int _selectedMonthlyMb = 0;
  bool _saving = false;

  // Simplified tiers shown in the overlay (0 = Unbegrenzt).
  static const _dailyTiers   = [100, 200, 500, 0];
  static const _monthlyTiers = [500, 1024, 2048, 0];

  @override
  void initState() {
    super.initState();
    _connType = widget.service.connectionType;
    _loadData();
  }

  Future<void> _loadData() async {
    final settings = NetworkSettingsService.instance;
    final db       = LicenseCacheDb.instance;
    final today    = DateTime.now().toIso8601String().substring(0, 10);
    final month    = DateTime.now().toIso8601String().substring(0, 7);

    final int dailyLimitMb;
    final int monthlyLimitMb;
    if (_connType == 'wifi') {
      dailyLimitMb   = await settings.wifiDailyLimitMb;
      monthlyLimitMb = await settings.wifiMonthlyLimitMb;
    } else {
      dailyLimitMb   = await settings.mobileDailyLimitMb;
      monthlyLimitMb = await settings.mobileMonthlyLimitMb;
    }

    final dailyUsed   = await db.getDailyUsage(today, _connType);
    final monthlyUsed = await db.getMonthlyUsage(month, _connType);

    if (!mounted) return;
    setState(() {
      _dailyLimitMb     = dailyLimitMb;
      _monthlyLimitMb   = monthlyLimitMb;
      _dailyUsedBytes   = dailyUsed;
      _monthlyUsedBytes = monthlyUsed;
      _selectedDailyMb  = _nextTier(dailyLimitMb, _dailyTiers);
      _selectedMonthlyMb = _nextTier(monthlyLimitMb, _monthlyTiers);
      _phase = _Phase.locked;
    });
  }

  // Returns the next tier above [current], or 0 (Unbegrenzt) if already at max.
  int _nextTier(int current, List<int> tiers) {
    for (final t in tiers) {
      if (t == 0 || t > current) return t;
    }
    return 0;
  }

  Future<void> _authenticate() async {
    final ps = context.read<ParentalLockService>();
    final ok = await ps.authenticate('Datenlimit entsperren und anpassen');
    if (ok && mounted) setState(() => _phase = _Phase.unlocked);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final settings = NetworkSettingsService.instance;
    if (_phase == _Phase.adjustingDaily) {
      if (_connType == 'wifi') {
        if (_selectedDailyMb == 0) await settings.setWifiUnlimited(true);
        await settings.setWifiDailyLimitMb(_selectedDailyMb);
      } else {
        await settings.setMobileDailyLimitMb(_selectedDailyMb);
      }
    } else {
      if (_connType == 'wifi') {
        if (_selectedMonthlyMb == 0) await settings.setWifiUnlimited(true);
        await settings.setWifiMonthlyLimitMb(_selectedMonthlyMb);
      } else {
        await settings.setMobileMonthlyLimitMb(_selectedMonthlyMb);
      }
    }
    if (mounted) widget.service.dismiss(retry: true);
  }

  void _cancel() => widget.service.dismiss(retry: false);

  // ── Formatters ────────────────────────────────────────────────────────────

  String _mb(int mb) {
    if (mb == 0) return 'Unbegrenzt';
    if (mb >= 1024) {
      final gb = mb / 1024;
      return '${gb == gb.roundToDouble() ? gb.round() : gb.toStringAsFixed(1)} GB';
    }
    return '$mb MB';
  }

  String _bytes(int bytes) {
    if (bytes < 1024 * 1024) return '${(bytes / 1024).round()} KB';
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).round()} MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  double _pct(int usedBytes, int limitMb) {
    if (limitMb == 0) return 0.0;
    return (usedBytes / (limitMb * 1024 * 1024)).clamp(0.0, 1.0);
  }

  Color _barColor(double pct) {
    if (pct >= 1.0) return Colors.red.shade600;
    if (pct >= 0.8) return Colors.orange.shade600;
    return const Color(0xFF4CAF50);
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      body: SafeArea(
        child: switch (_phase) {
          _Phase.loading                                       => _buildLoading(),
          _Phase.locked                                        => _buildLocked(),
          _Phase.unlocked                                      => _buildUnlocked(),
          _Phase.adjustingDaily || _Phase.adjustingMonthly    => _buildAdjusting(),
        },
      ),
    );
  }

  Widget _buildLoading() =>
      const Center(child: CircularProgressIndicator(color: Color(0xFF2E7D32)));

  Widget _buildLocked() {
    final dailyPct   = _pct(_dailyUsedBytes, _dailyLimitMb);
    final monthlyPct = _pct(_monthlyUsedBytes, _monthlyLimitMb);

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🎓', style: TextStyle(fontSize: 56)),
            const SizedBox(height: 4),
            const Text(
              'Wissensfreund',
              style: TextStyle(
                fontSize: 26, fontWeight: FontWeight.w900,
                color: Color(0xFF2E7D32), letterSpacing: 0.5,
              ),
            ),
            const SizedBox(height: 36),
            Container(
              width: 80, height: 80,
              decoration: const BoxDecoration(
                color: Color(0xFFE8F5E9), shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.data_usage_rounded, size: 44, color: Color(0xFF2E7D32),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Datenlimit erreicht',
              style: TextStyle(
                fontSize: 22, fontWeight: FontWeight.bold,
                color: Color(0xFF2E7D32),
              ),
            ),
            const SizedBox(height: 24),
            // Usage card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.06),
                    blurRadius: 8, offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                children: [
                  _UsageProgressBar(
                    label: 'Heute',
                    usedLabel: _bytes(_dailyUsedBytes),
                    limitLabel: _dailyLimitMb == 0
                        ? 'Unbegrenzt' : _mb(_dailyLimitMb),
                    pct: dailyPct,
                    color: _barColor(dailyPct),
                  ),
                  const SizedBox(height: 14),
                  _UsageProgressBar(
                    label: 'Dieser Monat',
                    usedLabel: _bytes(_monthlyUsedBytes),
                    limitLabel: _monthlyLimitMb == 0
                        ? 'Unbegrenzt' : _mb(_monthlyLimitMb),
                    pct: monthlyPct,
                    color: _barColor(monthlyPct),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 36),
            FilledButton.icon(
              icon: const Icon(Icons.fingerprint_rounded, size: 26),
              label: const Text(
                'Entsperren',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF2E7D32),
                padding: const EdgeInsets.symmetric(horizontal: 44, vertical: 18),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(50),
                ),
              ),
              onPressed: _authenticate,
            ),
            const SizedBox(height: 12),
            TextButton(
              onPressed: _cancel,
              child: const Text(
                'Abbrechen',
                style: TextStyle(color: Color(0xFF888888), fontSize: 15),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUnlocked() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🎓', style: TextStyle(fontSize: 56)),
            const SizedBox(height: 4),
            const Text(
              'Wissensfreund',
              style: TextStyle(
                fontSize: 26, fontWeight: FontWeight.w900,
                color: Color(0xFF2E7D32), letterSpacing: 0.5,
              ),
            ),
            const SizedBox(height: 40),
            const Text(
              'Was soll ich anpassen?',
              style: TextStyle(
                fontSize: 20, fontWeight: FontWeight.bold,
                color: Color(0xFF1B5E20),
              ),
            ),
            const SizedBox(height: 32),
            Row(
              children: [
                Expanded(
                  child: _OptionCard(
                    icon: Icons.today_rounded,
                    label: 'Tageslimit\nerhöhen',
                    onTap: () =>
                        setState(() => _phase = _Phase.adjustingDaily),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _OptionCard(
                    icon: Icons.calendar_month_rounded,
                    label: 'Monatslimit\nerhöhen',
                    onTap: () =>
                        setState(() => _phase = _Phase.adjustingMonthly),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 28),
            TextButton(
              onPressed: _cancel,
              child: const Text(
                'Abbrechen',
                style: TextStyle(color: Color(0xFF888888), fontSize: 15),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAdjusting() {
    final isDaily  = _phase == _Phase.adjustingDaily;
    final tiers    = isDaily ? _dailyTiers : _monthlyTiers;
    final current  = isDaily ? _dailyLimitMb : _monthlyLimitMb;
    final selected = isDaily ? _selectedDailyMb : _selectedMonthlyMb;
    final unit     = isDaily ? '/Tag' : '/Monat';

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isDaily ? 'Tageslimit anpassen' : 'Monatslimit anpassen',
              style: const TextStyle(
                fontSize: 22, fontWeight: FontWeight.bold,
                color: Color(0xFF2E7D32),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'Aktuell: ${_mb(current)}$unit',
              style: const TextStyle(fontSize: 14, color: Color(0xFF888888)),
            ),
            const SizedBox(height: 20),
            ...tiers.map((tier) {
              final isCurrent  = current == tier;
              return RadioListTile<int>(
                value: tier,
                groupValue: selected,
                onChanged: (v) {
                  if (v == null) return;
                  setState(() {
                    if (isDaily) _selectedDailyMb = v;
                    else _selectedMonthlyMb = v;
                  });
                },
                title: Text(
                  '${_mb(tier)}$unit${isCurrent ? '  (aktuell)' : ''}',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: selected == tier
                        ? FontWeight.w700 : FontWeight.normal,
                    color: selected == tier
                        ? const Color(0xFF2E7D32)
                        : const Color(0xFF1B1B1B),
                  ),
                ),
                activeColor: const Color(0xFF2E7D32),
                contentPadding: EdgeInsets.zero,
                dense: true,
              );
            }),
            const SizedBox(height: 28),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () =>
                        setState(() => _phase = _Phase.unlocked),
                    child: const Text('Zurück'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF2E7D32)),
                    onPressed: _saving ? null : _save,
                    child: _saving
                        ? const SizedBox(
                            width: 20, height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white,
                            ),
                          )
                        : const Text('Speichern'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── Helper Widgets ────────────────────────────────────────────────────────────

class _UsageProgressBar extends StatelessWidget {
  final String label;
  final String usedLabel;
  final String limitLabel;
  final double pct;
  final Color  color;

  const _UsageProgressBar({
    required this.label,
    required this.usedLabel,
    required this.limitLabel,
    required this.pct,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 13, color: Color(0xFF888888))),
            Text('$usedLabel / $limitLabel',
                style: const TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w600,
                    color: Color(0xFF1B1B1B))),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: pct,
            minHeight: 8,
            backgroundColor: const Color(0xFFE8F5E9),
            valueColor: AlwaysStoppedAnimation(color),
          ),
        ),
      ],
    );
  }
}

class _OptionCard extends StatelessWidget {
  final IconData icon;
  final String   label;
  final VoidCallback onTap;

  const _OptionCard({
    required this.icon, required this.label, required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding:
            const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.07),
              blurRadius: 10, offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 36, color: const Color(0xFF2E7D32)),
            const SizedBox(height: 12),
            Text(
              label,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 15, fontWeight: FontWeight.w600,
                color: Color(0xFF1B5E20),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
