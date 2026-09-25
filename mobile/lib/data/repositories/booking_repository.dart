import 'package:dio/dio.dart';

import '../../core/network/api_exception.dart';
import '../../core/utils/format.dart';
import '../models/booking_model.dart';

/// Customer bookings: create hold → verify payment → list → cancel.
abstract interface class BookingRepository {
  /// Creates a `pending_payment` hold; returns booking + Razorpay `payment`.
  ///
  /// Guest checkout (contract 2026-09-24): when the client has no session it
  /// MUST pass [guestName] + [guestPhone] — the request goes out without a
  /// Bearer token and the response carries `access_token` for
  /// verify/cancel/list. Registered sessions omit both (server ignores them).
  Future<CreateBookingResponse> createBooking({
    required int serviceId,
    required List<String> addons,
    required int barberId,
    required DateTime startAt,
    String notes = '',
    String? guestName,
    String? guestPhone,
  });

  /// Confirms the booking after Razorpay checkout (`400` on bad signature /
  /// expired hold / overlap).
  Future<Booking> verifyPayment({
    required String bookingId,
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  });

  Future<List<Booking>> myBookings();

  Future<Booking> booking(String id);

  /// `start ≥ now+2h` → cancelled (+refund if paid); otherwise `403`.
  Future<Booking> cancelBooking(String bookingId);
}

class ApiBookingRepository implements BookingRepository {
  ApiBookingRepository(this._dio);

  final Dio _dio;

  @override
  Future<CreateBookingResponse> createBooking({
    required int serviceId,
    required List<String> addons,
    required int barberId,
    required DateTime startAt,
    String notes = '',
    String? guestName,
    String? guestPhone,
  }) async {
    try {
      final res = await _dio.post<Object?>(
        '/bookings',
        data: {
          'service_id': serviceId,
          'addons': addons,
          'barber_id': barberId,
          'start_at': AppFormat.apiTimestamp(startAt),
          'notes': notes,
          // Guest identity (only sent when the client has no Bearer token).
          if (guestName != null && guestName.trim().isNotEmpty)
            'guest_name': guestName.trim(),
          if (guestPhone != null && guestPhone.trim().isNotEmpty)
            'guest_phone': guestPhone.trim(),
        },
      );
      return CreateBookingResponse.fromJson(
        (res.data as Map).cast<String, dynamic>(),
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @override
  Future<Booking> verifyPayment({
    required String bookingId,
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  }) async {
    try {
      final res = await _dio.post<Object?>(
        '/bookings/$bookingId/verify-payment',
        data: {
          'razorpay_order_id': razorpayOrderId,
          'razorpay_payment_id': razorpayPaymentId,
          'razorpay_signature': razorpaySignature,
        },
      );
      final data = (res.data as Map).cast<String, dynamic>();
      if (data['booking'] is Map) {
        return Booking.fromJson(
          (data['booking'] as Map).cast<String, dynamic>(),
        );
      }
      return Booking.fromJson(data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @override
  Future<List<Booking>> myBookings() async {
    try {
      final res = await _dio.get<Object?>('/bookings');
      final data = res.data;
      final List<dynamic> items;
      if (data is Map && data['items'] is List) {
        items = data['items'] as List;
      } else if (data is List) {
        items = data;
      } else {
        items = const [];
      }
      return items
          .cast<Map>()
          .map((m) => Booking.fromJson(m.cast<String, dynamic>()))
          .toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @override
  Future<Booking> booking(String id) async {
    try {
      final res = await _dio.get<Object?>('/bookings/$id');
      final data = (res.data as Map).cast<String, dynamic>();
      if (data['booking'] is Map) {
        return Booking.fromJson(
          (data['booking'] as Map).cast<String, dynamic>(),
        );
      }
      return Booking.fromJson(data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @override
  Future<Booking> cancelBooking(String bookingId) async {
    try {
      final res = await _dio.post<Object?>('/bookings/$bookingId/cancel');
      final data = (res.data as Map).cast<String, dynamic>();
      if (data['booking'] is Map) {
        return Booking.fromJson(
          (data['booking'] as Map).cast<String, dynamic>(),
        );
      }
      return Booking.fromJson(data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
