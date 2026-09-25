import 'package:dio/dio.dart';

import '../../core/network/api_exception.dart';
import '../models/barber_model.dart';
import '../models/service_model.dart';

/// Public catalog: services + barbers.
abstract interface class CatalogRepository {
  Future<List<ServiceItem>> services();

  Future<List<Barber>> barbers();

  Future<Barber> barber(int id);
}

class ApiCatalogRepository implements CatalogRepository {
  ApiCatalogRepository(this._dio);

  final Dio _dio;

  @override
  Future<List<ServiceItem>> services() async {
    try {
      final res = await _dio.get<Object?>('/services');
      final data = (res.data as Map).cast<String, dynamic>();
      final items = (data['items'] as List? ?? const [])
          .cast<Map>()
          .map((m) => ServiceItem.fromJson(m.cast<String, dynamic>()))
          .where((s) => s.isActive)
          .toList();
      return items;
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @override
  Future<List<Barber>> barbers() async {
    try {
      final res = await _dio.get<Object?>('/barbers');
      final data = (res.data as Map).cast<String, dynamic>();
      return (data['items'] as List? ?? const [])
          .cast<Map>()
          .map((m) => Barber.fromJson(m.cast<String, dynamic>()))
          .where((b) => b.isActive)
          .toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @override
  Future<Barber> barber(int id) async {
    try {
      final res = await _dio.get<Object?>('/barbers/$id');
      final data = res.data;
      if (data is Map && data['barber'] is Map) {
        return Barber.fromJson((data['barber'] as Map).cast<String, dynamic>());
      }
      return Barber.fromJson((data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
