import 'package:flutter_riverpod/flutter_riverpod.dart';

/// In-memory JWT holder. Phase 5 may persist to secure storage behind this
/// same provider so call sites stay unchanged.
class AuthTokenNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  void setToken(String? token) => state = token;

  void clear() => state = null;
}

final authTokenProvider =
    NotifierProvider<AuthTokenNotifier, String?>(AuthTokenNotifier.new);
