import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/core/utils/pricing.dart';
import 'package:salon_mobile/data/models/service_model.dart';

ServiceItem _service({
  required int price,
  String priceType = 'fixed',
  int durationMinutes = 60,
}) =>
    ServiceItem(
      id: 1,
      name: 'Test',
      description: '',
      durationMinutes: durationMinutes,
      price: price,
      priceType: priceType,
      isActive: true,
      addons: const [
        ServiceAddon(
          id: 'wash',
          name: 'Wash',
          price: 30,
          durationMinutes: 15,
        ),
      ],
    );

void main() {
  group('fixed service pricing (AGENTS.md rules)', () {
    test('haircut: total ₹100, advance 50% ceil, balance in-shop', () {
      final haircut = _service(price: 100);
      expect(Pricing.onlineTotal(haircut, wash: false), 100);
      expect(Pricing.advance(haircut, wash: false), 50);
      expect(Pricing.balance(haircut, wash: false), 50);
      expect(Pricing.durationMinutes(haircut, wash: false), 60);
    });

    test('haircut + wash: +₹30 total, +15 min, advance ceil(total*0.5)', () {
      final haircut = _service(price: 100);
      expect(Pricing.onlineTotal(haircut, wash: true), 130);
      expect(Pricing.advance(haircut, wash: true), 65);
      expect(Pricing.balance(haircut, wash: true), 65);
      expect(Pricing.durationMinutes(haircut, wash: true), 75);
    });

    test('odd totals round the advance up (₹70 shave → ₹35)', () {
      final shave = _service(price: 70, durationMinutes: 30);
      expect(Pricing.advance(shave, wash: false), 35);
      final beard = _service(price: 50, durationMinutes: 15);
      expect(Pricing.advance(beard, wash: false), 25);
    });

    test('wash add-on price/duration constants match the catalog', () {
      expect(Pricing.washAddonPrice, 30);
      expect(Pricing.washAddonMinutes, 15);
    });
  });

  group('hair color (price_type=variable_advance)', () {
    final color = _service(
      price: 100,
      priceType: 'variable_advance',
      durationMinutes: 90,
    );

    test('flat ₹100 advance online regardless of wash', () {
      expect(Pricing.advance(color, wash: false), 100);
      expect(Pricing.advance(color, wash: true), 100);
      expect(Pricing.hairColorAdvance, 100);
    });

    test('final total/balance unknown until the center completes it', () {
      expect(Pricing.onlineTotal(color, wash: false), isNull);
      expect(Pricing.balance(color, wash: false), isNull);
      expect(Pricing.isHairColor(color), isTrue);
    });

    test('duration still grows with the wash add-on', () {
      expect(Pricing.durationMinutes(color, wash: false), 90);
      expect(Pricing.durationMinutes(color, wash: true), 105);
    });
  });
}
