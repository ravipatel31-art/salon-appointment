import 'package:dio/dio.dart';

/// Normalized API failure carrying the contract's HTTP status + `detail`.
class ApiException implements Exception {
  const ApiException({required this.statusCode, required this.detail});

  final int? statusCode;
  final String detail;

  /// `409 {"detail":"slot_unavailable"}` — another booking took the slot.
  bool get isSlotUnavailable => statusCode == 409 && detail == 'slot_unavailable';

  bool get isUnauthorized => statusCode == 401;
  bool get isForbidden => statusCode == 403;
  bool get isConflict => statusCode == 409;

  /// Build from a dio error (network failure or HTTP error body).
  factory ApiException.fromDio(DioException error) {
    final response = error.response;
    if (response != null) {
      final detail = _extractDetail(response.data) ??
          (error.message ?? 'Request failed (${response.statusCode})');
      return ApiException(statusCode: response.statusCode, detail: detail);
    }
    return switch (error.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.sendTimeout ||
      DioExceptionType.receiveTimeout =>
        const ApiException(statusCode: null, detail: 'Connection timed out'),
      DioExceptionType.connectionError =>
        const ApiException(statusCode: null, detail: 'No connection to server'),
      _ => ApiException(
          statusCode: null,
          detail: error.message ?? 'Network error',
        ),
    };
  }

  static String? _extractDetail(Object? data) {
    if (data is Map && data['detail'] != null) {
      return data['detail'].toString();
    }
    if (data is String && data.isNotEmpty) return data;
    return null;
  }

  @override
  String toString() => detail;
}
