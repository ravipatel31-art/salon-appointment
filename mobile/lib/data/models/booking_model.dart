/// Contract booking models (`POST /bookings`, `GET /bookings`, verify).
library;

import 'user_model.dart';

/// Contract BookingStatus enum values.
abstract final class BookingStatus {
  static const String pendingPayment = 'pending_payment';
  static const String confirmed = 'confirmed';
  static const String completed = 'completed';
  static const String cancelled = 'cancelled';
  static const String refunded = 'refunded';
  static const String noShow = 'no_show';

  /// UI labels for the contract enums.
  static String label(String status) => switch (status) {
        pendingPayment => 'Pending payment',
        confirmed => 'Confirmed',
        completed => 'Completed',
        cancelled => 'Cancelled',
        refunded => 'Refunded',
        noShow => 'No show',
        _ => status,
      };

  static bool isUpcomingOpen(String status) =>
      status == pendingPayment || status == confirmed;
}

class Booking {
  const Booking({
    required this.id,
    required this.bookingRef,
    required this.status,
    required this.serviceId,
    required this.barberId,
    required this.addons,
    required this.startAt,
    required this.endAt,
    required this.durationMinutes,
    required this.totalAmount,
    required this.advanceAmount,
    required this.balanceAmount,
    required this.onlineAmountPaid,
    required this.expiresAt,
    this.serviceName,
    this.barberName,
    this.finalPriceAtCenter,
    this.balanceDue,
  });

  final String id;
  final String bookingRef;
  final String status;
  final int serviceId;
  final int barberId;
  final List<String> addons;
  final DateTime startAt;
  final DateTime endAt;
  final int durationMinutes;
  final int totalAmount;
  final int advanceAmount;
  final int balanceAmount;
  final int onlineAmountPaid;

  /// `pending_payment` hold expiry (12 minutes after creation).
  final DateTime expiresAt;

  /// Present on `GET /bookings*` responses.
  final String? serviceName;
  final String? barberName;
  final int? finalPriceAtCenter;
  final int? balanceDue;

  Duration holdRemaining([DateTime? now]) =>
      expiresAt.difference(now ?? DateTime.now().toUtc());

  bool get holdExpired => holdRemaining().isNegative;

  factory Booking.fromJson(Map<String, dynamic> json) => Booking(
        id: json['id'] as String? ?? '',
        bookingRef: json['booking_ref'] as String? ?? '',
        status: json['status'] as String? ?? BookingStatus.pendingPayment,
        serviceId: (json['service_id'] as num?)?.toInt() ?? 0,
        barberId: (json['barber_id'] as num?)?.toInt() ?? 0,
        addons: [
          for (final a in (json['addons'] as List? ?? const [])) a.toString(),
        ],
        startAt: DateTime.parse(json['start_at'] as String).toUtc(),
        endAt: DateTime.parse(json['end_at'] as String).toUtc(),
        durationMinutes: (json['duration_minutes'] as num?)?.toInt() ?? 0,
        totalAmount: (json['total_amount'] as num?)?.toInt() ?? 0,
        advanceAmount: (json['advance_amount'] as num?)?.toInt() ?? 0,
        balanceAmount: (json['balance_amount'] as num?)?.toInt() ?? 0,
        onlineAmountPaid: (json['online_amount_paid'] as num?)?.toInt() ?? 0,
        expiresAt: DateTime.parse(json['expires_at'] as String).toUtc(),
        serviceName: json['service_name'] as String?,
        barberName: json['barber_name'] as String?,
        finalPriceAtCenter: (json['final_price_at_center'] as num?)?.toInt(),
        balanceDue: (json['balance_due'] as num?)?.toInt(),
      );
}

/// Contract `payment` object returned by `POST /bookings`.
class PaymentOptions {
  const PaymentOptions({
    required this.razorpayOrderId,
    required this.razorpayAmount,
    required this.razorpayCurrency,
    required this.keyId,
  });

  final String razorpayOrderId;

  /// Amount in **paise** (contract: integer paise in payment fields).
  final int razorpayAmount;
  final String razorpayCurrency;
  final String keyId;

  int get amountRupees => (razorpayAmount / 100).round();

  factory PaymentOptions.fromJson(Map<String, dynamic> json) => PaymentOptions(
        razorpayOrderId: json['razorpay_order_id'] as String? ?? '',
        razorpayAmount: (json['razorpay_amount'] as num?)?.toInt() ?? 0,
        razorpayCurrency: json['razorpay_currency'] as String? ?? 'INR',
        keyId: json['key_id'] as String? ?? '',
      );
}

/// `POST /bookings` 201 response.
///
/// Guest create (contract 2026-09-24) additionally returns a session:
/// `access_token` / `token_type` / `user` — present only when the booking was
/// created without a prior Bearer token.
class CreateBookingResponse {
  const CreateBookingResponse({
    required this.booking,
    required this.payment,
    this.accessToken,
    this.tokenType,
    this.user,
  });

  final Booking booking;
  final PaymentOptions payment;

  /// Guest-session JWT issued at create (`null` for registered sessions).
  final String? accessToken;
  final String? tokenType;
  final User? user;

  /// True when the server issued a new session token for this client.
  bool get hasNewSession => accessToken != null && accessToken!.isNotEmpty;

  factory CreateBookingResponse.fromJson(Map<String, dynamic> json) =>
      CreateBookingResponse(
        booking: Booking.fromJson(
          (json['booking'] as Map).cast<String, dynamic>(),
        ),
        payment: PaymentOptions.fromJson(
          (json['payment'] as Map).cast<String, dynamic>(),
        ),
        accessToken: json['access_token'] as String?,
        tokenType: json['token_type'] as String?,
        user: json['user'] is Map
            ? User.fromJson((json['user'] as Map).cast<String, dynamic>())
            : null,
      );
}
