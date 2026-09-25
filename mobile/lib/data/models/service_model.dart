/// Contract `GET /services` models.
class ServiceAddon {
  const ServiceAddon({
    required this.id,
    required this.name,
    required this.price,
    required this.durationMinutes,
  });

  final String id;
  final String name;
  final int price;
  final int durationMinutes;

  factory ServiceAddon.fromJson(Map<String, dynamic> json) => ServiceAddon(
        id: json['id'] as String,
        name: json['name'] as String? ?? '',
        price: (json['price'] as num?)?.toInt() ?? 0,
        durationMinutes: (json['duration_minutes'] as num?)?.toInt() ?? 0,
      );
}

class ServiceItem {
  const ServiceItem({
    required this.id,
    required this.name,
    required this.description,
    required this.durationMinutes,
    required this.price,
    required this.priceType,
    required this.isActive,
    required this.addons,
  });

  final int id;
  final String name;
  final String description;
  final int durationMinutes;

  /// Online price in rupees (hair color: ₹100 flat advance).
  final int price;

  /// Contract PriceType: `fixed` | `variable_advance`.
  final String priceType;

  final bool isActive;
  final List<ServiceAddon> addons;

  bool get isVariableAdvance => priceType == 'variable_advance';

  bool get isHairColor => isVariableAdvance;

  ServiceAddon? get washAddon {
    for (final a in addons) {
      if (a.id.toLowerCase() == 'wash') return a;
    }
    return null;
  }

  factory ServiceItem.fromJson(Map<String, dynamic> json) => ServiceItem(
        id: (json['id'] as num).toInt(),
        name: json['name'] as String? ?? '',
        description: json['description'] as String? ?? '',
        durationMinutes: (json['duration_minutes'] as num?)?.toInt() ?? 0,
        price: (json['price'] as num?)?.toInt() ?? 0,
        priceType: json['price_type'] as String? ?? 'fixed',
        isActive: json['is_active'] as bool? ?? true,
        addons: [
          for (final a in (json['addons'] as List? ?? const []))
            ServiceAddon.fromJson((a as Map).cast<String, dynamic>()),
        ],
      );
}
