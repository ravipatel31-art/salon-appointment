import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/app/app.dart';
import 'package:salon_mobile/core/widgets/barber_photo.dart';
import 'package:salon_mobile/core/widgets/service_art.dart';
import 'package:salon_mobile/data/models/barber_model.dart';
import 'package:salon_mobile/data/repositories/mocks/mock_backend.dart';
import 'package:salon_mobile/data/repositories/mock_repositories.dart';

import 'support/fake_image_http.dart';

/// Phase 12 — visual polish: client-owned service art, barber photo
/// fallbacks (contract § Imagery), and the premium screen treatments.
void main() {
  setUp(installFakePortraitHttp);
  tearDown(uninstallFakePortraitHttp);
  setUp(MockBackend.resetForTest);

  group('ServiceArt (client-owned catalog art, no API fields)', () {
    test('every seeded catalog service resolves distinct art', () async {
      final services = await MockCatalogRepository().services();
      expect(services, hasLength(9));
      final arts = services.map(ServiceArt.forService).toList();
      // Distinct icon + distinct gradient per catalog row.
      expect(arts.map((a) => a.icon).toSet(), hasLength(9));
      expect(arts.map((a) => Object.hashAll(a.gradient.colors)).toSet(),
          hasLength(9));
    });

    test('name fallback covers keywords for admin-added rows', () {
      expect(ServiceArt.fromName('Hair color').icon, Icons.palette);
      expect(ServiceArt.fromName('Wash').icon, Icons.water_drop);
      expect(ServiceArt.fromName('Beard trim').icon, Icons.brush);
      // Compound words: color wins for color services.
      expect(ServiceArt.fromName('Beard dye color').icon,
          ServiceArt.hairColor.icon);
      expect(ServiceArt.fromName('Haircut + Shaving').icon,
          ServiceArt.haircutShaving.icon);
      expect(
          ServiceArt.fromName('Something new').icon, ServiceArt.generic.icon);
      expect(ServiceArt.of(id: null, name: '').icon,
          ServiceArt.generic.icon);
    });

    test('wash add-on art exists with a distinct icon', () {
      expect(ServiceArt.wash.icon, Icons.water_drop);
      expect(
        ServiceArt.wash.icon,
        isNot(ServiceArt.haircut.icon),
      );
    });
  });

  group('mock barbers (phase 11 parity)', () {
    test('all five ship a demo https photo_url', () {
      expect(MockBackend.barbers, hasLength(5));
      for (final b in MockBackend.barbers) {
        expect(b.photoUrl, isNotNull, reason: b.name);
        expect(b.photoUrl!, startsWith('https://'), reason: b.name);
      }
    });
  });

  group('BarberAvatar / BarberHeroImage (offline-safe imagery)', () {
    const noPhoto = Barber(
      id: 99,
      name: 'Aakash Mehta',
      photoUrl: null,
      bio: '',
      specialties: [],
      isActive: true,
    );

    testWidgets('null photo_url → gradient circle with initials, no network',
        (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: BarberAvatar(barber: noPhoto, radius: 30)),
        ),
      );
      expect(find.text('AM'), findsOneWidget);
      expect(find.byType(Image), findsNothing);
    });

    testWidgets(
        'failing network photo → errorBuilder gradient + initials '
        '(contract Imagery client rule)', (tester) async {
      const withPhoto = Barber(
        id: 99,
        name: 'Aakash Mehta',
        photoUrl: 'https://i.pravatar.cc/300?u=salon-broken',
        bio: '',
        specialties: [],
        isActive: true,
      );
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: BarberAvatar(barber: withPhoto, radius: 30)),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.text('AM'), findsOneWidget);
    });

    testWidgets('large header image falls back to gradient + initials',
        (tester) async {
      const broken = Barber(
        id: 3,
        name: 'Imran Shaikh',
        photoUrl: 'https://example.invalid/portrait.jpg',
        bio: '',
        specialties: [],
        isActive: true,
      );
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: BarberHeroImage(barber: broken, height: 160)),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.text('IS'), findsOneWidget);
    });
  });

  group('screen polish', () {
    Future<void> pumpApp(WidgetTester tester) async {
      await tester.pumpWidget(const ProviderScope(child: SalonApp()));
      await tester.pump(const Duration(milliseconds: 1300));
      await tester.pumpAndSettle();
    }

    testWidgets('splash: gradient brand screen with logo mark + tagline',
        (tester) async {
      await tester.pumpWidget(const ProviderScope(child: SalonApp()));
      expect(find.text('Salon'), findsOneWidget);
      expect(find.text('Book your chair in seconds'), findsOneWidget);
      expect(find.byIcon(Icons.content_cut), findsWidgets);

      // Let the 1200ms splash timer fire so no timer is pending at teardown.
      await tester.pump(const Duration(milliseconds: 1300));
      await tester.pumpAndSettle();
    });

    testWidgets('barbers list: branded header + portrait cards',
        (tester) async {
      await pumpApp(tester);
      expect(find.text('Master barbers, one tap away'), findsOneWidget);
      // ListView builds lazily — the first screenful carries the portraits.
      expect(find.byType(BarberAvatar), findsAtLeastNWidgets(4));
      expect(find.text('Aakash Mehta'), findsOneWidget);
    });

    testWidgets('services tab: illustration banners on catalog cards',
        (tester) async {
      await pumpApp(tester);
      await tester.tap(find.text('Services'));
      await tester.pumpAndSettle();
      // ListView builds lazily — at least the first cards carry art banners.
      expect(find.byType(ServiceArtBanner), findsWidgets);
      expect(find.byType(ServiceArtChip), findsNothing); // chips are checkout-only
    });

    testWidgets('selection page: service chips lead with art icons',
        (tester) async {
      await pumpApp(tester);
      await tester.tap(find.text('Aakash Mehta'));
      await tester.pumpAndSettle();
      expect(find.text('Select service, date & time'), findsOneWidget);

      final artChips = find.byWidgetPredicate(
        (w) => w is ChoiceChip && w.avatar != null,
      );
      expect(artChips, findsWidgets);
    });
  });
}
