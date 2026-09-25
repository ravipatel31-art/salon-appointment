/// Contract `user` / auth session models.
class User {
  const User({
    required this.id,
    required this.name,
    required this.phone,
    required this.email,
    required this.role,
  });

  final int id;
  final String name;
  final String phone;
  final String email;

  /// `customer` | `admin` (contract Role enum).
  final String role;

  bool get isAdmin => role == 'admin';

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: (json['id'] as num?)?.toInt() ?? 0,
        name: json['name'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        email: json['email'] as String? ?? '',
        role: json['role'] as String? ?? 'customer',
      );
}

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.tokenType,
    required this.user,
  });

  final String accessToken;
  final String tokenType;
  final User user;

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
        accessToken: json['access_token'] as String? ?? '',
        tokenType: json['token_type'] as String? ?? 'bearer',
        user:
            User.fromJson((json['user'] as Map?)?.cast<String, dynamic>() ?? {}),
      );
}
