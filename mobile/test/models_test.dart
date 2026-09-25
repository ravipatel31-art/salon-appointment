import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/core/network/api_exception.dart';
import 'package:salon_mobile/core/utils/format.dart';
import 'package:salon_mobile/data/models/availability_model.dart';
import 'package:salon_mobile/data/models/booking_model.dart';
import 'package:salon_mobile/data/models/service_model.dart';

void main() {
  group('ServiceItem.fromJson (contract GET /services)', () {
    test('parses a service with the wash add-on', () {
      final json = {
        'id': 1,
        'name': 'Haircut',
        'description': '',
        'duration_minutes': 60,
        'price': 100,
        'price_type': 'fixed',
        'is_active': true,
        'addons': [
          {'id': 'wash', 'name': 'Wash', 'price': 30, 'duration_minutes': 15},
        ],
      };
      final service = ServiceItem.fromJson(json);
      expect(service.name, 'Haircut');
      expect(service.durationMinutes, 60);
      expect(service.price, 100);
      expect(service.priceType, 'fixed');
      expect(service.addons.single.id, 'wash');
      expect(service.washAddon?.price, 30);
      expect(service.isVariableAdvance, isFalse);
    });

    test('parses hair color as variable_advance', () {
      final service = ServiceItem.fromJson({
        'id': 7,
        'name': 'Hair color',
        'duration_minutes': 90,
        'price': 100,
        'price_type': 'variable_advance',
        'is_active': true,
        'addons': <Map<String, dynamic>>[],
      });
      expect(service.isHairColor, isTrue);
      expect(service.price, 100);
    });
  });

  group('Availability.fromJson (contract slots[].start_at)', () {
    test('parses UTC slot instants and availability flags', () {
      final json = {
        'barber_id': 1,
        'date': '2026-09-24',
        'service_id': 1,
        'duration_minutes': 75,
        'slots': [
          {'start_at': '2026-09-24T04:30:00Z', 'available': true},
          {'start_at': '2026-09-24T04:45:00Z', 'available': false},
        ],
      };
      final availability = Availability.fromJson(json);
      expect(availability.barberId, 1);
      expect(availability.date, '2026-09-24');
      expect(availability.durationMinutes, 75);
      expect(availability.slots, hasLength(2));
      expect(availability.slots.first.startAt, DateTime.utc(2026, 9, 24, 4, 30));
      expect(availability.slots.first.available, isTrue);
      expect(availability.slots.last.available, isFalse);
      // Displayed in IST: 04:30Z → 10:00 am.
      expect(
        AppFormat.timeInKolkata(availability.slots.first.startAt),
        '10:00 am',
      );
    });
  });

  group('CreateBookingResponse.fromJson (contract POST /bookings 201)', () {
    test('parses booking amounts and payment paise/key', () {
      final json = {
        'booking': {
          'id': 'uuid-1',
          'booking_ref': 'SL-20260924-0042',
          'status': 'pending_payment',
          'service_id': 1,
          'barber_id': 2,
          'addons': ['wash'],
          'start_at': '2026-09-24T04:30:00Z',
          'end_at': '2026-09-24T05:45:00Z',
          'duration_minutes': 75,
          'total_amount': 130,
          'advance_amount': 65,
          'balance_amount': 65,
          'online_amount_paid': 0,
          'expires_at': '2026-09-24T06:00:00Z',
        },
        'payment': {
          'razorpay_order_id': 'order_xxx',
          'razorpay_amount': 6500,
          'razorpay_currency': 'INR',
          'key_id': 'rzp_live_xxx',
        },
      };
      final result = CreateBookingResponse.fromJson(json);
      expect(result.booking.bookingRef, 'SL-20260924-0042');
      expect(result.booking.status, BookingStatus.pendingPayment);
      expect(result.booking.addons, ['wash']);
      expect(result.booking.totalAmount, 130);
      expect(result.booking.advanceAmount, 65);
      expect(result.booking.balanceAmount, 65);
      expect(result.booking.startAt, DateTime.utc(2026, 9, 24, 4, 30));
      expect(result.booking.durationMinutes, 75);
      expect(result.payment.razorpayOrderId, 'order_xxx');
      expect(result.payment.razorpayAmount, 6500);
      expect(result.payment.amountRupees, 65);
      expect(result.payment.keyId, 'rzp_live_xxx');
      expect(
        result.booking.holdRemaining(DateTime.utc(2026, 9, 24, 5, 54)),
        const Duration(minutes: 6),
      );
    });

    test('parses guest access_token / user (contract guest create, 2026-09-24)',
        () {
      final json = {
        'booking': {
          'id': 'uuid-2',
          'booking_ref': 'SL-20260924-0043',
          'status': 'pending_payment',
          'service_id': 1,
          'barber_id': 2,
          'addons': <String>[],
          'start_at': '2026-09-24T04:30:00Z',
          'end_at': '2026-09-24T05:30:00Z',
          'duration_minutes': 60,
          'total_amount': 100,
          'advance_amount': 50,
          'balance_amount': 50,
          'online_amount_paid': 0,
          'expires_at': '2026-09-24T06:00:00Z',
          'guest_name': 'Walk-in',
          'guest_phone': '9876543210',
        },
        'payment': {
          'razorpay_order_id': 'order_yyy',
          'razorpay_amount': 5000,
          'razorpay_currency': 'INR',
          'key_id': 'rzp_test_xxx',
        },
        'access_token': 'jwt.guest.token',
        'token_type': 'bearer',
        'user': {
          'id': 7,
          'name': 'Walk-in',
          'phone': '9876543210',
          'email': null,
          'role': 'customer',
        },
      };
      final result = CreateBookingResponse.fromJson(json);
      expect(result.hasNewSession, isTrue);
      expect(result.accessToken, 'jwt.guest.token');
      expect(result.tokenType, 'bearer');
      expect(result.user, isNotNull);
      expect(result.user!.name, 'Walk-in');
      expect(result.user!.phone, '9876543210');
      expect(result.booking.bookingRef, 'SL-20260924-0043');
    });

    test('registered create omits access_token (hasNewSession false)', () {
      final result = CreateBookingResponse.fromJson({
        'booking': {
          'id': 'uuid-3',
          'booking_ref': 'SL-20260924-0044',
          'status': 'pending_payment',
          'service_id': 1,
          'barber_id': 2,
          'addons': <String>[],
          'start_at': '2026-09-24T04:30:00Z',
          'end_at': '2026-09-24T05:30:00Z',
          'duration_minutes': 60,
          'total_amount': 100,
          'advance_amount': 50,
          'balance_amount': 50,
          'online_amount_paid': 0,
          'expires_at': '2026-09-24T06:00:00Z',
        },
        'payment': {
          'razorpay_order_id': 'order_zzz',
          'razorpay_amount': 5000,
          'razorpay_currency': 'INR',
          'key_id': 'rzp_test_xxx',
        },
      });
      expect(result.hasNewSession, isFalse);
      expect(result.accessToken, isNull);
      expect(result.user, isNull);
    });

    test('parses GET /bookings extras (names, balance_due)', () {
      final booking = Booking.fromJson({
        'id': 'uuid-1',
        'booking_ref': 'SL-20260924-0042',
        'status': 'confirmed',
        'service_id': 7,
        'barber_id': 5,
        'addons': <String>[],
        'start_at': '2026-09-24T04:30:00Z',
        'end_at': '2026-09-24T06:00:00Z',
        'duration_minutes': 90,
        'total_amount': 100,
        'advance_amount': 100,
        'balance_amount': 0,
        'online_amount_paid': 100,
        'expires_at': '2026-09-24T06:00:00Z',
        'service_name': 'Hair color',
        'barber_name': 'Suresh Iyer',
        'final_price_at_center': 350,
        'balance_due': 250,
      });
      expect(booking.serviceName, 'Hair color');
      expect(booking.barberName, 'Suresh Iyer');
      expect(booking.finalPriceAtCenter, 350);
      expect(booking.balanceDue, 250);
      expect(BookingStatus.label(booking.status), 'Confirmed');
    });
  });

  group('BookingStatus labels (contract enums)', () {
    test('maps every contract status to a UI label', () {
      expect(BookingStatus.label('pending_payment'), 'Pending payment');
      expect(BookingStatus.label('confirmed'), 'Confirmed');
      expect(BookingStatus.label('completed'), 'Completed');
      expect(BookingStatus.label('cancelled'), 'Cancelled');
      expect(BookingStatus.label('refunded'), 'Refunded');
      expect(BookingStatus.label('no_show'), 'No show');
    });

    test('isUpcomingOpen covers the two open statuses', () {
      expect(BookingStatus.isUpcomingOpen('pending_payment'), isTrue);
      expect(BookingStatus.isUpcomingOpen('confirmed'), isTrue);
      expect(BookingStatus.isUpcomingOpen('completed'), isFalse);
      expect(BookingStatus.isUpcomingOpen('cancelled'), isFalse);
      expect(BookingStatus.isUpcomingOpen('refunded'), isFalse);
      expect(BookingStatus.isUpcomingOpen('no_show'), isFalse);
    });
  });

  group('ApiException', () {
    test('flags contract 409 slot_unavailable', () {
      const e = ApiException(statusCode: 409, detail: 'slot_unavailable');
      expect(e.isSlotUnavailable, isTrue);
      expect(e.isConflict, isTrue);
    });

    test('does not flag other 409s as slot conflicts', () {
      const e = ApiException(statusCode: 409, detail: 'other_conflict');
      expect(e.isSlotUnavailable, isFalse);
    });

    test('flags 401/403', () {
      expect(
        const ApiException(statusCode: 401, detail: 'x').isUnauthorized,
        isTrue,
      );
      expect(
        const ApiException(statusCode: 403, detail: 'x').isForbidden,
        isTrue,
      );
    });
  });
}
