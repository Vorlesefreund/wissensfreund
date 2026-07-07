// Shop catalog (Baustein 3). Prices in ⭐. `slot` is where the item belongs in
// the room; `wearable` items can be put on the character. Emojis are PLACEHOLDERS
// for the real item art (swapped in later) — the mechanic works today.

class ShopItem {
  final String id;
  final String name;
  final String emoji;
  final int price; // ⭐
  final String slot;
  final bool wearable; // can be worn on the character

  const ShopItem({
    required this.id,
    required this.name,
    required this.emoji,
    required this.price,
    required this.slot,
    this.wearable = false,
  });
}

const List<ShopItem> kShopItems = [
  ShopItem(id: 'kompass', name: 'Kompass', emoji: '🧭', price: 3, slot: 'Schreibtisch'),
  ShopItem(id: 'lupe', name: 'Lupe', emoji: '🔍', price: 3, slot: 'Regal'),
  ShopItem(id: 'vogelfuehrer', name: 'Vogelführer', emoji: '📗', price: 4, slot: 'Regal'),
  ShopItem(id: 'taucherbrille', name: 'Taucherbrille', emoji: '🥽', price: 4, slot: 'Kopf', wearable: true),
  ShopItem(id: 'feldflasche', name: 'Feldflasche', emoji: '🍶', price: 4, slot: 'Gürtel', wearable: true),
  ShopItem(id: 'fernglas', name: 'Fernglas', emoji: '🔭', price: 5, slot: 'Hals', wearable: true),
  ShopItem(id: 'tropenhelm', name: 'Tropenhelm', emoji: '⛑️', price: 5, slot: 'Kopf', wearable: true),
  ShopItem(id: 'feldtagebuch', name: 'Feldtagebuch', emoji: '📔', price: 5, slot: 'Schreibtisch'),
  ShopItem(id: 'schmetterlingsnetz', name: 'Schmetterlingsnetz', emoji: '🥅', price: 5, slot: 'Wand'),
  ShopItem(id: 'muschelsammlung', name: 'Muschel-Sammlung', emoji: '🐚', price: 6, slot: 'Regal'),
  ShopItem(id: 'pflanzenpresse', name: 'Pflanzenpresse', emoji: '🌿', price: 6, slot: 'Schreibtisch'),
  ShopItem(id: 'rucksack', name: 'Rucksack', emoji: '🎒', price: 6, slot: 'Rücken', wearable: true),
  ShopItem(id: 'schatzkarte', name: 'Schatzkarte', emoji: '🗺️', price: 6, slot: 'Wand'),
  ShopItem(id: 'kletterseil', name: 'Kletterseil', emoji: '🪢', price: 7, slot: 'Boden'),
  ShopItem(id: 'geologenhammer', name: 'Geologenhammer', emoji: '⛏️', price: 7, slot: 'Schreibtisch'),
  ShopItem(id: 'barometer', name: 'Barometer', emoji: '🌡️', price: 7, slot: 'Wand'),
  ShopItem(id: 'globus', name: 'Globus', emoji: '🌍', price: 7, slot: 'Schreibtisch'),
  ShopItem(id: 'schatzkarte_gerahmt', name: 'Antike Schatzkarte', emoji: '🖼️', price: 8, slot: 'Wand'),
  ShopItem(id: 'fossilien', name: 'Fossilien-Schaukasten', emoji: '🦴', price: 8, slot: 'Regal'),
  ShopItem(id: 'sammlerkoffer', name: 'Sammlerkoffer', emoji: '🧳', price: 8, slot: 'Boden'),
  ShopItem(id: 'unterwasserkamera', name: 'Unterwasserkamera', emoji: '📷', price: 8, slot: 'Regal'),
  ShopItem(id: 'archaeologenset', name: 'Archäologen-Set', emoji: '🖌️', price: 9, slot: 'Schreibtisch'),
  ShopItem(id: 'schiffsmodell', name: 'Schiffsmodell im Glas', emoji: '⛵', price: 9, slot: 'Regal'),
  ShopItem(id: 'amphore', name: 'Alte Amphore', emoji: '🏺', price: 9, slot: 'Boden'),
  ShopItem(id: 'taucheranzug', name: 'Taucheranzug', emoji: '🤿', price: 10, slot: 'Outfit', wearable: true),
  ShopItem(id: 'mikroskop', name: 'Mikroskop', emoji: '🔬', price: 10, slot: 'Schreibtisch'),
  ShopItem(id: 'mondgestein', name: 'Mondgestein', emoji: '🌑', price: 10, slot: 'Regal'),
  ShopItem(id: 'chemielabor', name: 'Mini-Chemielabor', emoji: '⚗️', price: 12, slot: 'Schreibtisch'),
  ShopItem(id: 'raumfahrerhelm', name: 'Raumfahrerhelm', emoji: '🪐', price: 12, slot: 'Kopf', wearable: true),
  ShopItem(id: 'teleskop', name: 'Teleskop', emoji: '🔭', price: 12, slot: 'Boden'),
  ShopItem(id: 'astronautenanzug', name: 'Astronautenanzug', emoji: '🧑‍🚀', price: 15, slot: 'Outfit', wearable: true),
];

ShopItem? shopItemById(String id) {
  for (final it in kShopItems) {
    if (it.id == id) return it;
  }
  return null;
}
