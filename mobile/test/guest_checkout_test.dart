import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/app/app.dart';
import 'package:salon_mobile/core/network/auth_token_store.dart';
import 'package:salon_mobile/data/models/booking_model.dart';
import 'package:salon_mobile/data/providers.dart';
import 'package:salon_mobile/data/repositories/booking_repository.dart';
import 'package:salon_mobile/data/repositories/mocks/mock_backend.dart';
import 'package:salon_mobile/data/repositories/mock_repositories.dart';

import 'support/fake_image_http.dart';

/// Records the exact `POST /bookings` payload the checkout sends, then
/// delegates to the contract-shaped mock backend.
class _RecordingBookingRepository implements BookingRepository {
  _RecordingBookingRepository(this._inner);

  final BookingRepository _inner;

  int createCalls = 0;
  String? guestName;
  String? guestPhone;
  int? serviceId;
  int? barberId;
  List<String>? addons;
  DateTime? startAt;

  @override
  Future<CreateBookingResponse> createBooking({
    required int serviceId,
    required List<String> addons,
    required int barberId,
    required DateTime startAt,
    String notes = '',
    String? guestName,
    String? guestPhone,
  }) {
    createCalls++;
    this.guestName = guestName;
    this.guestPhone = guestPhone;
    this.serviceId = serviceId;
    this.barberId = barberId;
    this.addons = addons;
    this.startAt = startAt;
    return _inner.createBooking(
      serviceId: serviceId,
      addons: addons,
      barberId: barberId,
      startAt: startAt,
      notes: notes,
      guestName: guestName,
      guestPhone: guestPhone,
    );
  }

  @override
  Future<Booking> verifyPayment({
    required String bookingId,
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  }) =>
      _inner.verifyPayment(
        bookingId: bookingId,
        razorpayOrderId: razorpayOrderId,
        razorpayPaymentId: razorpayPaymentId,
        razorpaySignature: razorpaySignature,
      );

  @override
  Future<List<Booking>> myBookings() => _inner.myBookings();

  @override
  Future<Booking> booking(String id) => _inner.booking(id);

  @override
  Future<Booking> cancelBooking(String bookingId) =>
      _inner.cancelBooking(bookingId);
}

void main() {
  setUp(installFakePortraitHttp);
  tearDown(uninstallFakePortraitHttp);
  setUp(MockBackend.resetForTest);

  Future<ProviderContainer> pumpApp(
    WidgetTester tester,
    _RecordingBookingRepository repo,
  ) async {
    final container = ProviderContainer(
      overrides: [bookingRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SalonApp(),
      ),
    );
    await tester.pump(const Duration(milliseconds: 1300));
    await tester.pumpAndSettle();
    return container;
  }

  /// Barber-first path to checkout (no login).
  Future<void> reachCheckoutAsGuest(WidgetTester tester) async {
    await tester.tap(find.text('Aakash Mehta'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('wash_toggle')));
    await tester.tap(find.byKey(const Key('wash_toggle')));
    await tester.pumpAndSettle();

    final tomorrow = find.byKey(const ValueKey('date_chip_1'));
    await tester.ensureVisible(tomorrow);
    await tester.tap(tomorrow);
    await tester.pumpAndSettle();

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
  }

  testWidgets(
      'guest checkout: name+phone → POST /bookings without Bearer → '
      'stores access_token → Razorpay (no login wall)', (tester) async {
    final repo = _RecordingBookingRepository(MockBookingRepository());
    final container = await pumpApp(tester, repo);

    // No session before booking.
    expect(container.read(authTokenProvider), isNull);

    await reachCheckoutAsGuest(tester);

    // Guest identity card + optional login link; no forced login dialog.
    expect(find.text('Booking as guest'), findsOneWidget);
    expect(find.byKey(const Key('guest_name_field')), findsOneWidget);
    expect(find.byKey(const Key('guest_phone_field')), findsOneWidget);
    expect(find.byKey(const Key('checkout_login_link')), findsOneWidget);
    expect(find.text('Log in to pay'), findsNothing);

    // The pay button sits below the fold (ListView builds lazily) — scroll
    // it into view, then Pay with an empty identity → inline validation,
    // no create call yet.
    final verticalScroll = find
        .byWidgetPredicate((w) => w is Scrollable && w.axis == Axis.vertical)
        .first;
    final payBtn = find.byKey(const Key('pay_button'));
    final nameField = find.byKey(const Key('guest_name_field'));
    final phoneField = find.byKey(const Key('guest_phone_field'));

    await tester.scrollUntilVisible(payBtn, 300, scrollable: verticalScroll);
    await tester.pumpAndSettle();
    await tester.tap(payBtn);
    await tester.pump();
    expect(repo.createCalls, 0);

    // Back up to the guest card — errors render under each field.
    await tester.scrollUntilVisible(nameField, -300, scrollable: verticalScroll);
    await tester.pumpAndSettle();
    expect(find.text('Enter your name (max 80 characters)'), findsOneWidget);
    expect(
      find.text('Enter a 10-digit Indian mobile number'),
      findsOneWidget,
    );

    // Fill identity → Pay → guest payload (phone normalized to 10 digits).
    await tester.enterText(nameField, 'Rahul Sharma');
    await tester.enterText(phoneField, '+91 98765 43210');
    await tester.scrollUntilVisible(payBtn, 300, scrollable: verticalScroll);
    await tester.pumpAndSettle();
    await tester.tap(payBtn);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250)); // createBooking
    await tester.pump(const Duration(milliseconds: 450)); // sheet anim

    // Contract payload assertions.
    expect(repo.createCalls, 1);
    expect(repo.guestName, 'Rahul Sharma');
    expect(repo.guestPhone, '9876543210');
    expect(repo.serviceId, 1); // Haircut (barber-first default)
    expect(repo.barberId, 1);
    expect(repo.addons, ['wash']);
    expect(repo.startAt, isNotNull);

    // Guest `access_token` from the create response is stored for
    // verify/cancel/list — and the guest card disappears (session exists).
    expect(container.read(authTokenProvider), startsWith('mock-guest-token-'));
    expect(find.text('Booking as guest'), findsNothing);

    // Razorpay sheet opens straight away — Pay was never blocked on login.
    expect(find.text('Simulate Razorpay'), findsOneWidget);
    expect(find.textContaining('65 INR'), findsOneWidget);

    // Success → verify-payment (guest token attached by dio in live mode).
    await tester.tap(find.byKey(const Key('simulate_payment_success')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 150));
    expect(find.text('Verifying payment…'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();
    expect(find.text('Booking confirmed!'), findsOneWidget);
    expect(find.textContaining('SL-'), findsOneWidget);
  });

  testWidgets(
      'registered session: no guest fields, create omits guest payload',
      (tester) async {
    final repo = _RecordingBookingRepository(MockBookingRepository());
    final container = await pumpApp(tester, repo);

    // Login through the UI (Profile tab) — same as the registered flow.
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
    expect(container.read(authTokenProvider), isNotNull);

    // Barber-first checkout with an active session.
    await tester.tap(find.text('Barbers'));
    await tester.pumpAndSettle();
    await reachCheckoutAsGuest(tester);

    expect(find.text('Booking as guest'), findsNothing);
    expect(find.byKey(const Key('guest_name_field')), findsNothing);
    expect(find.byKey(const Key('checkout_login_link')), findsNothing);

    await tester.ensureVisible(find.byKey(const Key('pay_button')));
    await tester.tap(find.byKey(const Key('pay_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pump(const Duration(milliseconds: 450));

    expect(repo.createCalls, 1);
    expect(repo.guestName, isNull);
    expect(repo.guestPhone, isNull);
    // Registered create does not rotate the session.
    expect(container.read(authTokenProvider), 'mock-access-token');
    expect(find.text('Simulate Razorpay'), findsOneWidget);
  });
}
