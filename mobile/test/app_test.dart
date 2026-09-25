import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/app/app.dart';

import 'support/fake_image_http.dart';

void main() {
  // Demo photo_url portraits must load (see support/fake_image_http.dart).
  setUp(installFakePortraitHttp);
  tearDown(uninstallFakePortraitHttp);

  testWidgets('splash lands on the barber list first (barber-first entry)',
      (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SalonApp()));

    // Splash brand screen.
    expect(find.text('Salon'), findsOneWidget);

    // Timer (1200ms) fires → barber list (shell tab 0), not services.
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();

    expect(find.text('Barbers'), findsWidgets); // AppBar + nav label
    expect(find.text('Aakash Mehta'), findsOneWidget);
    expect(find.text('Rohan Patil'), findsOneWidget);
    expect(find.text('Services'), findsOneWidget); // secondary tab (nav only)
    expect(find.text('Bookings'), findsOneWidget);
    expect(find.text('Profile'), findsOneWidget);
    // Services catalog is NOT the landing screen.
    expect(find.text('Precision cut, styled to finish.'), findsNothing);
  });

  testWidgets('services tab (secondary) shows the mock catalog with INR pricing',
      (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SalonApp()));
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();

    // Services is no longer tab 0 — switch to it from the shell.
    await tester.tap(find.text('Services'));
    await tester.pumpAndSettle();

    expect(find.text('Haircut'), findsOneWidget);
    expect(find.text('₹100'), findsWidgets);
    expect(find.textContaining('Wash +₹30'), findsWidgets);

    // Hair color note lives further down the list.
    await tester.scrollUntilVisible(
      find.text('Hair color'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      find.text('₹100 advance online — actual price at center'),
      findsOneWidget,
    );
    expect(find.text('₹100 advance'), findsWidgets); // color card price
  });

  testWidgets('services → barbers preselect flow (service_id entry)',
      (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SalonApp()));
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Services'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Haircut'));
    await tester.pumpAndSettle();

    // Lands on the barber tab with the service preselect carried in the URL.
    expect(find.text('Barbers'), findsWidgets);
    expect(find.text('Aakash Mehta'), findsOneWidget);

    // Barber detail = selection page (service + wash + date + slot).
    await tester.tap(find.text('Aakash Mehta'));
    await tester.pumpAndSettle();
    expect(find.text('Select service, date & time'), findsOneWidget);
    expect(find.text('Service'), findsOneWidget);
    expect(find.text('Date'), findsOneWidget);
    expect(find.text('Time'), findsOneWidget);
    expect(find.byKey(const Key('wash_toggle')), findsOneWidget);
  });

  testWidgets('bottom nav switches to bookings and profile', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SalonApp()));
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Bookings'));
    await tester.pumpAndSettle();
    expect(find.text('Upcoming'), findsOneWidget);
    expect(find.text('Past'), findsOneWidget);
    // Seeded upcoming row (mock backend).
    expect(find.text('Massage + Haircut'), findsOneWidget);
    expect(find.text('Confirmed'), findsOneWidget);

    await tester.tap(find.text('Past'));
    await tester.pumpAndSettle();
    expect(find.text('Completed'), findsOneWidget);
    expect(find.text('Cancelled'), findsOneWidget);

    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    expect(find.text('Not signed in'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    expect(find.text('Create account'), findsOneWidget);
  });

  testWidgets('profile → register route renders contract fields',
      (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SalonApp()));
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Create account'));
    await tester.pumpAndSettle();

    expect(find.text('Name'), findsOneWidget);
    expect(find.text('Phone'), findsOneWidget);
    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Register'), findsOneWidget);
  });
}
