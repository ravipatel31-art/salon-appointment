import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/app/app.dart';
import 'package:salon_mobile/data/repositories/mocks/mock_backend.dart';

import 'support/fake_image_http.dart';

/// End-to-end booking flows against the mock repositories + simulated
/// Razorpay sheet (the swap to the real API/gateway is config-only).
void main() {
  setUp(installFakePortraitHttp);
  tearDown(uninstallFakePortraitHttp);
  setUp(MockBackend.resetForTest);

  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SalonApp()));
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();
  }

  Future<void> login(WidgetTester tester) async {
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Log in'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).at(0), '9876543210');
    await tester.enterText(find.byType(TextFormField).at(1), 'secret12');
    await tester.tap(find.widgetWithText(FilledButton, 'Log in'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pumpAndSettle();

    expect(find.text('Guest 9876543210'), findsOneWidget);
  }

  /// Barber-first primary flow: barber list → barber detail (selection page:
  /// service + wash + date + slot) → checkout.
  Future<void> reachCheckout(WidgetTester tester) async {
    // Splash lands on /barbers; after login we come back from another tab.
    if (find.text('Aakash Mehta').evaluate().isEmpty) {
      await tester.tap(find.text('Barbers'));
      await tester.pumpAndSettle();
    }

    await tester.tap(find.text('Aakash Mehta'));
    await tester.pumpAndSettle();
    expect(find.text('Select service, date & time'), findsOneWidget);

    // Live pricing: wash add-on flips ₹100/1h → ₹130/1h 15m.
    await tester.ensureVisible(find.byKey(const Key('wash_toggle')));
    await tester.tap(find.byKey(const Key('wash_toggle')));
    await tester.pumpAndSettle();

    // Next-14-days date chips: pick tomorrow for guaranteed free slots.
    final tomorrow = find.byKey(const ValueKey('date_chip_1'));
    await tester.ensureVisible(tomorrow);
    await tester.tap(tomorrow);
    await tester.pumpAndSettle();

    // First enabled slot chip (15-minute grid).
    final slots = find.byWidgetPredicate(
      (w) =>
          w is ChoiceChip &&
          w.key is ValueKey<String> &&
          (w.key as ValueKey<String>).value.startsWith('slot_') &&
          w.onSelected != null,
    );
    expect(slots, findsWidgets);
    await tester.ensureVisible(slots.first);
    await tester.tap(slots.first);
    await tester.pump();

    expect(find.text('1h 15m'), findsOneWidget);
    expect(find.text('₹65'), findsWidgets);

    // The continue button sits below the fold — drag the vertical list.
    final verticalScroll = find
        .byWidgetPredicate((w) => w is Scrollable && w.axis == Axis.vertical)
        .first;
    final continueBtn = find.byKey(const Key('continue_to_checkout'));
    await tester.scrollUntilVisible(
      continueBtn,
      300,
      scrollable: verticalScroll,
    );
    await tester.pumpAndSettle();
    await tester.tap(continueBtn);
    await tester.pumpAndSettle();

    // Checkout summary comes from the draft + pricing rules.
    expect(find.text('Checkout'), findsOneWidget);
    expect(find.text('Haircut'), findsOneWidget);
    expect(find.text('Aakash Mehta'), findsOneWidget);
    expect(find.text('Wash (+₹30 · +15m)'), findsOneWidget);
    expect(find.text('Pay advance ₹65'), findsOneWidget);
  }

  testWidgets('full flow: login → book haircut+wash → pay → confirmed',
      (tester) async {
    await pumpApp(tester);
    await login(tester);
    await reachCheckout(tester);

    // Registered session (token present) → no guest identity card.
    expect(find.text('Booking as guest'), findsNothing);
    expect(find.byKey(const Key('guest_name_field')), findsNothing);
    expect(find.byKey(const Key('checkout_login_link')), findsNothing);

    // POST /bookings → simulated Razorpay sheet.
    await tester.ensureVisible(find.byKey(const Key('pay_button')));
    await tester.tap(find.byKey(const Key('pay_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250)); // createBooking
    await tester.pump(const Duration(milliseconds: 450)); // sheet anim
    expect(find.text('Simulate Razorpay'), findsOneWidget);
    expect(find.textContaining('65 INR'), findsOneWidget); // payment amount

    // Success → verify-payment → success screen.
    await tester.tap(find.byKey(const Key('simulate_payment_success')));
    await tester.pump(); // routes to processing, verify starts
    await tester.pump(const Duration(milliseconds: 150));
    expect(find.text('Verifying payment…'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 600)); // verify latency
    await tester.pumpAndSettle(); // transition to success

    expect(find.text('Booking confirmed!'), findsOneWidget);
    expect(find.textContaining('SL-'), findsOneWidget);
    expect(find.text('Paid online ₹65 · Balance ₹65 in-shop'), findsOneWidget);

    // Lands in My Bookings with the new confirmed row.
    await tester.tap(find.byKey(const Key('view_bookings')));
    await tester.pumpAndSettle();
    expect(find.text('Haircut'), findsOneWidget);
    expect(find.textContaining('Ref SL-'), findsWidgets);
    expect(find.text('Confirmed'), findsWidgets);
  });

  testWidgets('payment failure → failed screen with retry path',
      (tester) async {
    await pumpApp(tester);
    await login(tester);
    await reachCheckout(tester);

    await tester.ensureVisible(find.byKey(const Key('pay_button')));
    await tester.tap(find.byKey(const Key('pay_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pump(const Duration(milliseconds: 450));
    expect(find.text('Simulate Razorpay'), findsOneWidget);

    await tester.tap(find.byKey(const Key('simulate_payment_failure')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));
    await tester.pumpAndSettle();

    // Failure path: hold still active → retry / cancel options.
    expect(find.text('Payment not completed'), findsWidgets);
    expect(find.text('Simulated payment error'), findsOneWidget);
    expect(find.byKey(const Key('retry_payment')), findsOneWidget);
    expect(find.byKey(const Key('cancel_booking')), findsOneWidget);

    // Retry returns to checkout resuming the same hold/order.
    // NOTE: checkout runs a 1s hold-countdown timer — use bounded pumps,
    // never pumpAndSettle, while it is mounted.
    await tester.tap(find.byKey(const Key('retry_payment')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Retry payment ₹65'), findsOneWidget);
    expect(find.byKey(const Key('hold_countdown')), findsOneWidget);

    // Leaving checkout disposes the hold countdown timer cleanly.
    await tester.tap(find.text('Back'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Time'), findsOneWidget);
    await tester.pumpAndSettle();
  });
}
