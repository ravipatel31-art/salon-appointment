import '../../data/models/service_model.dart';

/// Pricing rules from AGENTS.md / docs/CONTRACT.md.
///
/// * Fixed services: `total = price (+30 if wash)`, `advance = ceil(total * 0.5)`,
///   balance paid in-shop.
/// * Hair color (`price_type=variable_advance`): flat **₹100** advance online,
///   actual price collected at the center.
/// * Duration: `service.duration (+15 if wash add-on)`.
abstract final class Pricing {
  static const int washAddonPrice = 30;
  static const int washAddonMinutes = 15;
  static const int hairColorAdvance = 100;

  static bool hasWash(List<String> addons) =>
      addons.any((a) => a.toLowerCase() == 'wash');

  static int durationMinutes(ServiceItem service, {required bool wash}) =>
      service.durationMinutes + (wash ? washAddonMinutes : 0);

  /// Online total in rupees. `null` when the final total is only known at the
  /// center (hair color).
  static int? onlineTotal(ServiceItem service, {required bool wash}) {
    if (service.isVariableAdvance) return null;
    return service.price + (wash ? washAddonPrice : 0);
  }

  /// Online advance due now (rupees).
  static int advance(ServiceItem service, {required bool wash}) {
    if (service.isVariableAdvance) return hairColorAdvance;
    final total = onlineTotal(service, wash: wash)!; // ignore: null_check
    return (total * 0.5).ceil();
  }

  /// Balance payable in-shop for fixed services; `null` for hair color
  /// (settled by admin against `final_price_at_center`).
  static int? balance(ServiceItem service, {required bool wash}) {
    if (service.isVariableAdvance) return null;
    final total = onlineTotal(service, wash: wash)!;
    return total - advance(service, wash: wash);
  }

  static bool isHairColor(ServiceItem service) => service.isVariableAdvance;
}
