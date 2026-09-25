import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_exception.dart';
import '../../core/network/auth_token_store.dart';
import '../../data/models/user_model.dart';
import '../../data/providers.dart';

/// Session state for the customer (login/register/`GET /auth/me`).
class AuthState {
  const AuthState({this.user, this.busy = false, this.error});

  final User? user;
  final bool busy;
  final String? error;

  bool get isAuthenticated => user != null;

  AuthState copyWith({User? user, bool? busy, String? error, bool clearError = false}) =>
      AuthState(
        user: user ?? this.user,
        busy: busy ?? this.busy,
        error: clearError ? null : (error ?? this.error),
      );
}

class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() {
    // If a token already exists (future persistence), restore the profile.
    if (ref.read(authTokenProvider) != null) {
      Future.microtask(loadMe);
    }
    return const AuthState();
  }

  Future<bool> login({
    required String identifier,
    required String password,
  }) =>
      _authCall(
        () => ref
            .read(authRepositoryProvider)
            .login(identifier: identifier, password: password),
      );

  Future<bool> register({
    required String name,
    required String phone,
    required String email,
    required String password,
  }) =>
      _authCall(
        () => ref.read(authRepositoryProvider).register(
              name: name,
              phone: phone,
              email: email,
              password: password,
            ),
      );

  Future<bool> _authCall(Future<AuthSession> Function() run) async {
    state = state.copyWith(busy: true, clearError: true);
    try {
      final session = await run();
      ref.read(authTokenProvider.notifier).setToken(session.accessToken);
      state = AuthState(user: session.user);
      return true;
    } catch (e) {
      state = AuthState(error: _message(e), user: state.user);
      return false;
    }
  }

  /// `GET /auth/me` — keeps the profile fresh after a restored token.
  Future<void> loadMe() async {
    if (ref.read(authTokenProvider) == null) return;
    try {
      final user = await ref.read(authRepositoryProvider).me();
      state = state.copyWith(user: user, clearError: true);
    } on ApiException catch (e) {
      if (e.isUnauthorized) logout();
    } catch (_) {
      // Offline / mock-only: keep whatever we have.
    }
  }

  /// Stores a session issued outside login — guest checkout
  /// (`POST /bookings` response `access_token`, contract 2026-09-24) — so
  /// verify/cancel/list reuse the token without a login wall.
  void adoptSession({required String accessToken, User? user}) {
    if (accessToken.isEmpty) return;
    ref.read(authTokenProvider.notifier).setToken(accessToken);
    if (user != null) state = AuthState(user: user);
  }

  void logout() {
    ref.read(authTokenProvider.notifier).clear();
    state = const AuthState();
  }

  String _message(Object error) {
    if (error is ApiException) return error.detail;
    return 'Something went wrong. Please try again.';
  }
}

final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);
