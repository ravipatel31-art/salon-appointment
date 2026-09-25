import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/core/network/api_exception.dart';
import 'package:salon_mobile/core/utils/format.dart';
import 'package:salon_mobile/data/models/booking_model.dart';
import 'package:salon_mobile/data/models/service_model.dart';
import 'package:salon_mobile/data/repositories/mocks/mock_backend.dart';
import 'package:salon_mobile/data/repositories/mock_repositories.dart';

void main() {
  setUp(MockBackend.resetForTest);

  group('MockCatalogRepository (AGENTS.md catalog)', () {
    test('serves the seeded services with contract prices', () async {
      final services = await MockCatalogRepository().services();
      expect(
        services.map((s) => s.name),
        containsAll([
          'Haircut',
          'Shaving',
          'Beard trim',
          'Massage + Haircut',
          'Shaving + Massage',
          'Haircut + Shaving',
          'Haircut + Beard trim',
          'Full combo',
          'Hair color',
        ]),
      );

      ServiceItem serviceNamed(String name) =>
          services.firstWhere((s) => s.name == name);
      final haircut = serviceNamed('Haircut');
      expect(haircut.price, 100);
      expect(haircut.durationMinutes, 60);
      expect(haircut.priceType, 'fixed');
      expect(haircut.addons.single.id, 'wash');

      final color = serviceNamed('Hair color');
      expect(color.price, 100);
      expect(color.durationMinutes, 90);
      expect(color.isVariableAdvance, isTrue);

      final combo = serviceNamed('Full combo');
      expect(combo.price, 250);
      expect(combo.durationMinutes, 120);

      final haircutShave = serviceNamed('Haircut + Shaving');
      expect(haircutShave.price, 180);
      expect(haircutShave.durationMinutes, 90);
      expect(haircutShave.priceType, 'fixed');

      final haircutTrim = serviceNamed('Haircut + Beard trim');
      expect(haircutTrim.price, 130);
      expect(haircutTrim.durationMinutes, 75);
      expect(haircutTrim.priceType, 'fixed');
    });

    test('serves exactly 5 active barbers', () async {
      final barbers = await MockCatalogRepository().barbers();
      expect(barbers, hasLength(5));
      expect(barbers.map((b) => b.id), [1, 2, 3, 4, 5]);
    });
  });

  group('MockAvailabilityRepository', () {
    test('returns a 15-minute grid for tomorrow with the service duration',
        () async {
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(1));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 1,
        date: date,
        serviceId: 1, // haircut 60m, wash off → 60
        addons: const [],
      );
      expect(availability.date, date);
      expect(availability.durationMinutes, 60);
      expect(availability.slots, isNotEmpty);
      for (final slot in availability.slots) {
        expect(slot.startAt.minute % 15, 0);
      }
      expect(availability.slots.any((s) => s.available), isTrue);
      // Same start spacing = 15 minutes.
      for (var i = 1; i < availability.slots.length; i++) {
        expect(
          availability.slots[i]
              .startAt
              .difference(availability.slots[i - 1].startAt),
          const Duration(minutes: 15),
        );
      }
    });

    test('duration grows with the wash add-on', () async {
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(2));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 1,
        date: date,
        serviceId: 1,
        addons: const ['wash'],
      );
      expect(availability.durationMinutes, 75);
    });

    test('excludes past slots for today (Asia/Kolkata)', () async {
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(0));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 2,
        date: date,
        serviceId: 3, // beard trim 15m — many slots late in the day
      );
      final now = DateTime.now().toUtc();
      for (final slot in availability.slots) {
        if (!slot.available) continue;
        expect(slot.startAt.isAfter(now), isTrue);
      }
    });
  });

  group('MockBookingRepository', () {
    test('creates a pending_payment hold with 50% advance + payment object',
        () async {
      final repo = MockBookingRepository();
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(1));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 1,
        date: date,
        serviceId: 1,
        addons: const ['wash'],
      );
      final slot = availability.slots.firstWhere((s) => s.available);

      final result = await repo.createBooking(
        serviceId: 1,
        addons: const ['wash'],
        barberId: 1,
        startAt: slot.startAt,
        guestName: 'Test User',
        guestPhone: '9876543210',
      );

      final booking = result.booking;
      expect(booking.status, BookingStatus.pendingPayment);
      expect(booking.bookingRef, startsWith('SL-'));
      expect(booking.addons, ['wash']);
      expect(booking.totalAmount, 130);
      expect(booking.advanceAmount, 65);
      expect(booking.balanceAmount, 65);
      expect(booking.durationMinutes, 75);
      final hold = booking.holdRemaining(DateTime.now().toUtc());
      expect(hold.inMinutes, lessThanOrEqualTo(11));
      expect(hold.inMinutes, greaterThanOrEqualTo(10));

      // Payment object: paise + contract fields.
      expect(result.payment.razorpayAmount, 6500);
      expect(result.payment.razorpayCurrency, 'INR');
      expect(result.payment.razorpayOrderId, startsWith('order_'));
      expect(result.payment.keyId, isNotEmpty);
    });

    test('hair color books a flat ₹100 advance', () async {
      final repo = MockBookingRepository();
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(2));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 5,
        date: date,
        serviceId: 7,
      );
      final slot = availability.slots.firstWhere((s) => s.available);
      final result = await repo.createBooking(
        serviceId: 7,
        addons: const [],
        barberId: 5,
        startAt: slot.startAt,
        guestName: 'Test User',
        guestPhone: '9876543210',
      );
      expect(result.booking.advanceAmount, 100);
      expect(result.payment.razorpayAmount, 10000);
      expect(result.booking.durationMinutes, 90);
    });

    test('double-booking the same slot → 409 slot_unavailable', () async {
      final repo = MockBookingRepository();
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(1));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 2,
        date: date,
        serviceId: 2,
      );
      final slot = availability.slots.firstWhere((s) => s.available);

      await repo.createBooking(
        serviceId: 2,
        addons: const [],
        barberId: 2,
        startAt: slot.startAt,
        guestName: 'Test User',
        guestPhone: '9876543210',
      );

      await expectLater(
        repo.createBooking(
          serviceId: 2,
          addons: const [],
          barberId: 2,
          startAt: slot.startAt,
          guestName: 'Test User',
          guestPhone: '9876543210',
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'statusCode', 409)
              .having((e) => e.detail, 'detail', 'slot_unavailable')
              .having((e) => e.isSlotUnavailable, 'isSlotUnavailable', true),
        ),
      );
    });

    test('verify-payment confirms the hold', () async {
      final repo = MockBookingRepository();
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(1));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 4,
        date: date,
        serviceId: 3,
      );
      final slot = availability.slots.firstWhere((s) => s.available);
      final created = await repo.createBooking(
        serviceId: 3,
        addons: const [],
        barberId: 4,
        startAt: slot.startAt,
        guestName: 'Test User',
        guestPhone: '9876543210',
      );

      final confirmed = await repo.verifyPayment(
        bookingId: created.booking.id,
        razorpayOrderId: created.payment.razorpayOrderId,
        razorpayPaymentId: 'pay_test_1',
        razorpaySignature: 'sig_test_1',
      );
      expect(confirmed.status, BookingStatus.confirmed);
      expect(confirmed.onlineAmountPaid, created.booking.advanceAmount);
    });

    test('verify-payment rejects a bad signature with 400', () async {
      final repo = MockBookingRepository();
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(3));
      final availability = await MockAvailabilityRepository().availability(
        barberId: 4,
        date: date,
        serviceId: 3,
      );
      final slot = availability.slots.firstWhere((s) => s.available);
      final created = await repo.createBooking(
        serviceId: 3,
        addons: const [],
        barberId: 4,
        startAt: slot.startAt,
        guestName: 'Test User',
        guestPhone: '9876543210',
      );

      await expectLater(
        repo.verifyPayment(
          bookingId: created.booking.id,
          razorpayOrderId: created.payment.razorpayOrderId,
          razorpayPaymentId: '',
          razorpaySignature: '',
        ),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'statusCode', 400),
        ),
      );
    });

    test('cancel ≥2h ahead refunds a paid booking; too late → 403',
        () async {
      final repo = MockBookingRepository();
      final all = await repo.myBookings();
      final confirmedFuture = all.firstWhere(
        (b) => b.status == BookingStatus.confirmed,
      );
      final cancelled = await repo.cancelBooking(confirmedFuture.id);
      expect(cancelled.status, BookingStatus.refunded);

      // A past booking cannot be cancelled (outside the 2-hour window).
      final completed = all.firstWhere(
        (b) => b.status == BookingStatus.completed,
      );
      await expectLater(
        repo.cancelBooking(completed.id),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'statusCode', 403),
        ),
      );
    });

    test('myBookings seeds upcoming + past rows', () async {
      final bookings = await MockBookingRepository().myBookings();
      expect(
        bookings.map((b) => b.status),
        containsAll([
          BookingStatus.completed,
          BookingStatus.cancelled,
          BookingStatus.confirmed,
        ]),
      );
      final now = DateTime.now().toUtc();
      final upcoming = bookings
          .where((b) => BookingStatus.isUpcomingOpen(b.status) && b.startAt.isAfter(now))
          .toList();
      expect(upcoming, isNotEmpty);
      expect(upcoming.first.serviceName, isNotNull);
    });
  });

  group('guest booking contract (2026-09-24)', () {
    Future<DateTime> freeSlot({
      required int barberId,
      required int serviceId,
    }) async {
      final date = AppFormat.isoDateFromIstDay(AppFormat.istDay(3));
      final availability = await MockAvailabilityRepository().availability(
        barberId: barberId,
        date: date,
        serviceId: serviceId,
      );
      return availability.slots.firstWhere((s) => s.available).startAt;
    }

    test('unauthenticated create without guest identity → 400 '
        'guest_identity_required', () async {
      final repo = MockBookingRepository();
      final startAt = await freeSlot(barberId: 1, serviceId: 1);
      await expectLater(
        repo.createBooking(
          serviceId: 1,
          addons: const [],
          barberId: 1,
          startAt: startAt,
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'statusCode', 400)
              .having((e) => e.detail, 'detail', 'guest_identity_required'),
        ),
      );
      // Invalid phone also rejected (contract: 10 digits after +91/0).
      await expectLater(
        repo.createBooking(
          serviceId: 1,
          addons: const [],
          barberId: 1,
          startAt: startAt,
          guestName: 'Rahul',
          guestPhone: '12345',
        ),
        throwsA(
          isA<ApiException>().having((e) => e.detail, 'detail',
              'guest_identity_required'),
        ),
      );
    });

    test('guest create returns access_token + user for verify/cancel/list',
        () async {
      final repo = MockBookingRepository();
      final startAt = await freeSlot(barberId: 2, serviceId: 3);
      final result = await repo.createBooking(
        serviceId: 3,
        addons: const [],
        barberId: 2,
        startAt: startAt,
        guestName: 'Walk-in Guest',
        guestPhone: '+91 97111 22333',
      );

      expect(result.hasNewSession, isTrue);
      expect(result.accessToken, startsWith('mock-guest-token-'));
      expect(result.tokenType, 'bearer');
      expect(result.user, isNotNull);
      expect(result.user!.name, 'Walk-in Guest');
      expect(result.user!.phone, '9711122333'); // normalized 10 digits
      expect(result.booking.status, BookingStatus.pendingPayment);

      // The issued session now authenticates subsequent calls (mock mirrors
      // the dio interceptor attaching the stored Bearer token).
      expect(MockBackend.currentToken, result.accessToken);

      // A second create without re-sending identity works (session present).
      final second = await repo.createBooking(
        serviceId: 3,
        addons: const [],
        barberId: 2,
        startAt: await freeSlot(barberId: 2, serviceId: 3),
      );
      expect(second.hasNewSession, isFalse);
      expect(second.accessToken, isNull);
      expect(second.user, isNull);
    });

    test('guest create with an existing customer phone links that profile '
        '(find-or-create, no overwrite)', () async {
      // Registered customer first.
      final authRepo = MockAuthRepository();
      await authRepo.register(
        name: 'Rahul Sharma',
        phone: '9876543210',
        email: 'rahul@example.com',
        password: 'secret1',
      );
      // Drop the session — now a guest books with the same phone.
      MockBackend.logout();
      expect(MockBackend.currentToken, isNull);

      final repo = MockBookingRepository();
      final startAt = await freeSlot(barberId: 4, serviceId: 1);
      final result = await repo.createBooking(
        serviceId: 1,
        addons: const [],
        barberId: 4,
        startAt: startAt,
        guestName: 'Someone Else',
        guestPhone: '09876543210', // leading 0 → same 10-digit number
      );

      expect(result.hasNewSession, isTrue);
      expect(result.user, isNotNull);
      // Existing profile is linked, NOT overwritten by guest_name.
      expect(result.user!.name, 'Rahul Sharma');
      expect(result.user!.phone, '9876543210');
      expect(result.accessToken, isNotEmpty);
    });

    test('authenticated create ignores guest fields and returns no token',
        () async {
      await MockAuthRepository().login(
        identifier: '9876543210',
        password: 'secret1',
      );
      final repo = MockBookingRepository();
      final startAt = await freeSlot(barberId: 5, serviceId: 2);
      final result = await repo.createBooking(
        serviceId: 2,
        addons: const [],
        barberId: 5,
        startAt: startAt,
        guestName: 'Ignored',
        guestPhone: '9111111111',
      );
      expect(result.hasNewSession, isFalse);
      expect(result.accessToken, isNull);
      expect(result.user, isNull);
    });
  });
}
