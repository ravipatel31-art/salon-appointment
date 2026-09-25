import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/barber_model.dart';
import '../../data/models/booking_model.dart';
import '../../data/models/service_model.dart';
import '../../data/payment_gateway.dart';

/// Selection made on barber detail / availability → consumed by checkout.
class BookingDraft {
  const BookingDraft({
    this.service,
    this.addons = const [],
    this.barber,
    this.startAt,
  });

  final ServiceItem? service;
  final List<String> addons;
  final Barber? barber;

  /// Slot start (UTC, from `slots[].start_at`).
  final DateTime? startAt;

  bool get isComplete => service != null && startAt != null && barber != null;
  bool get hasWash => addons.any((a) => a.toLowerCase() == 'wash');

  /// Service duration + 15 min when the wash add-on is on.
  Duration get duration {
    final s = service;
    if (s == null) return Duration.zero;
    return Duration(
      minutes: s.durationMinutes + (hasWash ? washMinutes : 0),
    );
  }

  static const int washMinutes = 15;
}

class BookingDraftNotifier extends Notifier<BookingDraft> {
  @override
  BookingDraft build() => const BookingDraft();

  void select({
    required ServiceItem service,
    required List<String> addons,
    required Barber barber,
    required DateTime startAt,
  }) {
    state = BookingDraft(
      service: service,
      addons: List.unmodifiable(addons),
      barber: barber,
      startAt: startAt.toUtc(),
    );
  }

  void clear() => state = const BookingDraft();
}

final bookingDraftProvider =
    NotifierProvider<BookingDraftNotifier, BookingDraft>(
  BookingDraftNotifier.new,
);

/// Created `pending_payment` hold + Razorpay `payment` object for the
/// in-flight checkout (survives checkout → failed → retry navigation).
class PendingPayment {
  const PendingPayment({
    required this.booking,
    required this.payment,
    this.success,
  });

  final Booking booking;
  final PaymentOptions payment;
  final PaymentSuccess? success;

  bool get holdExpired => booking.holdExpired;

  PendingPayment withSuccess(PaymentSuccess value) =>
      PendingPayment(booking: booking, payment: payment, success: value);
}

class PendingPaymentNotifier extends Notifier<PendingPayment?> {
  @override
  PendingPayment? build() => null;

  void set(PendingPayment value) => state = value;

  void setSuccess(PaymentSuccess value) {
    final current = state;
    if (current != null) state = current.withSuccess(value);
  }

  void clear() => state = null;
}

final pendingPaymentProvider =
    NotifierProvider<PendingPaymentNotifier, PendingPayment?>(
  PendingPaymentNotifier.new,
);

/// Booking confirmed by `POST /bookings/{id}/verify-payment` — shown on the
/// success screen.
class LastConfirmedNotifier extends Notifier<Booking?> {
  @override
  Booking? build() => null;

  void set(Booking booking) => state = booking;

  void clear() => state = null;
}

final lastConfirmedProvider = NotifierProvider<LastConfirmedNotifier, Booking?>(
  LastConfirmedNotifier.new,
);
