import 'package:dio/dio.dart';

import '../../core/network/api_exception.dart';
import '../models/availability_model.dart';

/// Slot availability — always refetched from the API (no offline truth).
abstract interface class AvailabilityRepository {
  /// `date` is the Asia/Kolkata calendar day `YYYY-MM-DD`;
  /// `addons` are contract addon ids (`wash`).
  Future<Availability> availability({
    required int barberId,
    required String date,
    required int serviceId,
    List<String> addons = const [],
  });
}

class ApiAvailabilityRepository implements AvailabilityRepository {
  ApiAvailabilityRepository(this._dio);

  final Dio _dio;

  @override
  Future<Availability> availability({
    required int barberId,
    required String date,
    required int serviceId,
    List<String> addons = const [],
  }) async {
    try {
      final res = await _dio.get<Object?>(
        '/barbers/$barberId/availability',
        queryParameters: {
          'date': date,
          'service_id': serviceId,
          if (addons.isNotEmpty) 'addons': addons.join(','),
        },
      );
      return Availability.fromJson((res.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
