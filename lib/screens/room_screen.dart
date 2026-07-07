import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/character_config.dart';
import '../models/shop_item.dart';
import '../services/license_cache_db.dart';
import '../services/profile_service.dart';
import '../services/reward_service.dart';
import '../widgets/character_avatar.dart';
import 'character_customize_screen.dart';
import 'shop_screen.dart';

/// Mein Zimmer (Baustein 3): the character with worn items, the item inventory,
/// and entries to the shop and customization. Placeholder art throughout.
class RoomScreen extends StatefulWidget {
  const RoomScreen({super.key});

  @override
  State<RoomScreen> createState() => _RoomScreenState();
}

class _RoomScreenState extends State<RoomScreen> {
  CharacterConfig _cfg = const CharacterConfig();
  Map<String, bool> _owned = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final pid = ProfileService.instance.activeProfile?.id;
    final cfg = pid == null ? null : await LicenseCacheDb.instance.getCharacter(pid);
    final owned =
        pid == null ? <String, bool>{} : await LicenseCacheDb.instance.getOwnedItems(pid);
    if (mounted) {
      setState(() {
        _cfg = cfg ?? const CharacterConfig();
        _owned = owned;
        _loading = false;
      });
    }
  }

  Future<void> _toggleWorn(ShopItem item) async {
    final pid = ProfileService.instance.activeProfile?.id;
    if (pid == null) return;
    final next = !(_owned[item.id] ?? false);
    await LicenseCacheDb.instance.setItemWorn(pid, item.id, next);
    setState(() => _owned[item.id] = next);
  }

  List<ShopItem> get _wornItems => _owned.entries
      .where((e) => e.value)
      .map((e) => shopItemById(e.key))
      .whereType<ShopItem>()
      .where((it) => it.wearable)
      .toList();

  Future<void> _open(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    _load(); // refresh after buying / customizing
  }

  @override
  Widget build(BuildContext context) {
    final stars = context.watch<RewardService>().stars;
    final ownedItems = _owned.keys
        .map(shopItemById)
        .whereType<ShopItem>()
        .toList()
      ..sort((a, b) => a.price.compareTo(b.price));

    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(
        title: const Text('Mein Zimmer'),
        centerTitle: false,
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Text('$stars ⭐',
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // Character stage
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFFEAF4EA), Color(0xFFFFFDF6)],
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                    ),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: const Color(0xFFD9E4D6)),
                  ),
                  child: Center(
                    child: CharacterAvatar(config: _cfg, worn: _wornItems, size: 200),
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _open(const CharacterCustomizeScreen()),
                        icon: const Icon(Icons.face_retouching_natural, size: 18),
                        label: const Text('Anpassen'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF2E7D32),
                          side: const BorderSide(color: Color(0xFF2E7D32)),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: () => _open(const ShopScreen()),
                        icon: const Text('🛒', style: TextStyle(fontSize: 16)),
                        label: const Text('Shop'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFB8860B),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                const Text('Meine Sachen',
                    style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFF2E7D32))),
                const SizedBox(height: 4),
                if (ownedItems.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 20),
                    child: Text(
                      'Noch keine Sachen. Sammle Sterne mit Quizzen und kauf dir etwas im Shop! 🛒',
                      style: TextStyle(fontSize: 15, color: Color(0xFF6D6257)),
                    ),
                  )
                else
                  GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    padding: const EdgeInsets.only(top: 10),
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      childAspectRatio: 0.80,
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                    ),
                    itemCount: ownedItems.length,
                    itemBuilder: (context, i) {
                      final item = ownedItems[i];
                      final worn = _owned[item.id] ?? false;
                      return _InventoryTile(
                        item: item,
                        worn: worn,
                        onTap: item.wearable ? () => _toggleWorn(item) : null,
                      );
                    },
                  ),
              ],
            ),
    );
  }
}

class _InventoryTile extends StatelessWidget {
  final ShopItem item;
  final bool worn;
  final VoidCallback? onTap;
  const _InventoryTile({required this.item, required this.worn, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: worn ? const Color(0xFF2E7D32) : const Color(0xFFE0D8C9),
            width: worn ? 2 : 1.5,
          ),
        ),
        padding: const EdgeInsets.all(6),
        child: Column(
          children: [
            Expanded(
              child: Center(
                child: Text(item.emoji, style: const TextStyle(fontSize: 34)),
              ),
            ),
            Text(item.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
            if (item.wearable)
              Text(worn ? '✓ angezogen' : 'anziehen',
                  style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: worn ? const Color(0xFF2E7D32) : const Color(0xFF9A8F7E))),
          ],
        ),
      ),
    );
  }
}
