import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/shop_item.dart';
import '../services/license_cache_db.dart';
import '../services/profile_service.dart';
import '../services/reward_service.dart';

/// Shop (Baustein 3): spend ⭐ on items. Cosmetic only. Item art is placeholder
/// emoji for now.
class ShopScreen extends StatefulWidget {
  const ShopScreen({super.key});

  @override
  State<ShopScreen> createState() => _ShopScreenState();
}

class _ShopScreenState extends State<ShopScreen> {
  Map<String, bool> _owned = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final pid = ProfileService.instance.activeProfile?.id;
    final owned =
        pid == null ? <String, bool>{} : await LicenseCacheDb.instance.getOwnedItems(pid);
    if (mounted) setState(() { _owned = owned; _loading = false; });
  }

  Future<void> _buy(ShopItem item) async {
    final ok = await RewardService.instance.buyItem(itemId: item.id, price: item.price);
    if (!mounted) return;
    if (ok) {
      setState(() => _owned[item.id] = false);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text('„${item.name}" gekauft! 🎉')));
    } else {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(content: Text('Nicht genug Sterne dafür.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final stars = context.watch<RewardService>().stars;
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(
        title: const Text('Shop'),
        centerTitle: false,
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Text('$stars ⭐',
                  style: const TextStyle(
                      fontSize: 17, fontWeight: FontWeight.bold)),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : GridView.builder(
              padding: const EdgeInsets.all(16),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 0.82,
                crossAxisSpacing: 14,
                mainAxisSpacing: 14,
              ),
              itemCount: kShopItems.length,
              itemBuilder: (context, i) {
                final item = kShopItems[i];
                final owned = _owned.containsKey(item.id);
                final affordable = stars >= item.price;
                return _ShopTile(
                  item: item,
                  owned: owned,
                  affordable: affordable,
                  onBuy: owned || !affordable ? null : () => _buy(item),
                );
              },
            ),
    );
  }
}

class _ShopTile extends StatelessWidget {
  final ShopItem item;
  final bool owned;
  final bool affordable;
  final VoidCallback? onBuy;
  const _ShopTile({
    required this.item,
    required this.owned,
    required this.affordable,
    required this.onBuy,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: owned ? const Color(0xFF66A759) : const Color(0xFFE0D8C9),
          width: owned ? 2 : 1.5,
        ),
      ),
      padding: const EdgeInsets.all(10),
      child: Column(
        children: [
          Expanded(
            child: Center(
              child: Text(item.emoji, style: const TextStyle(fontSize: 46)),
            ),
          ),
          Text(
            item.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
          ),
          Text(item.slot,
              style: const TextStyle(fontSize: 11, color: Color(0xFF9A8F7E))),
          const SizedBox(height: 6),
          if (owned)
            const _Pill(text: '✓ Besitzt', color: Color(0xFF2E7D32))
          else
            SizedBox(
              width: double.infinity,
              height: 34,
              child: FilledButton(
                onPressed: onBuy,
                style: FilledButton.styleFrom(
                  backgroundColor: affordable
                      ? const Color(0xFFB8860B)
                      : const Color(0xFFCFC5B6),
                  padding: EdgeInsets.zero,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                ),
                child: Text('${item.price} ⭐',
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.bold)),
              ),
            ),
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final String text;
  final Color color;
  const _Pill({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: 34,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.bold, color: color)),
    );
  }
}
