import 'package:dio/dio.dart';

import '../../core/network/api_exception.dart';
import '../models/user_model.dart';

/// Auth API (contract § Auth): register / login / me.
abstract interface class AuthRepository {
  Future<AuthSession> register({
    required String name,
    required String phone,
    required String email,
    required String password,
  });

  /// `identifier` may be an email or a phone — mapped to the contract's
  /// `{email,password}` or `{phone,password}` body.
  Future<AuthSession> login({
    required String identifier,
    required String password,
  });

  Future<User> me();
}

class ApiAuthRepository implements AuthRepository {
  ApiAuthRepository(this._dio);

  final Dio _dio;

  @override
  Future<AuthSession> register({
    required String name,
    required String phone,
    required String email,
    required String password,
  }) =>
      _post(
        '/auth/register',
        {
          'name': name,
          'phone': phone,
          'email': email,
          'password': password,
        },
      );

  @override
  Future<AuthSession> login({
    required String identifier,
    required String password,
  }) {
    final body = identifier.contains('@')
        ? {'email': identifier, 'password': password}
        : {'phone': identifier, 'password': password};
    return _post('/auth/login', body);
  }

  @override
  Future<User> me() async {
    try {
      final res = await _dio.get<Object?>('/auth/me');
      final data = res.data;
      if (data is Map && data['user'] is Map) {
        return User.fromJson((data['user'] as Map).cast<String, dynamic>());
      }
      if (data is Map) return User.fromJson(data.cast<String, dynamic>());
      throw const ApiException(statusCode: 500, detail: 'Malformed /auth/me');
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<AuthSession> _post(String path, Map<String, dynamic> body) async {
    try {
      final res = await _dio.post<Object?>(path, data: body);
      final data = (res.data as Map).cast<String, dynamic>();
      return AuthSession.fromJson(data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
