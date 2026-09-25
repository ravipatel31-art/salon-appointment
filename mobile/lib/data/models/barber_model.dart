/// Contract `GET /barbers` models (5 seeded rows).
class Barber {
  const Barber({
    required this.id,
    required this.name,
    required this.photoUrl,
    required this.bio,
    required this.specialties,
    required this.isActive,
  });

  final int id;
  final String name;
  final String? photoUrl;
  final String bio;
  final List<String> specialties;
  final bool isActive;

  /// First letters for the avatar fallback when `photo_url` is null.
  String get initials {
    final parts =
        name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    final first = parts.first.substring(0, 1).toUpperCase();
    if (parts.length == 1) return first;
    return '$first${parts.last.substring(0, 1).toUpperCase()}';
  }

  factory Barber.fromJson(Map<String, dynamic> json) => Barber(
        id: (json['id'] as num).toInt(),
        name: json['name'] as String? ?? '',
        photoUrl: json['photo_url'] as String?,
        bio: json['bio'] as String? ?? '',
        specialties: _parseSpecialties(json['specialties']),
        isActive: json['is_active'] as bool? ?? true,
      );

  /// Backend may return a list or a comma-separated string; accept both.
  static List<String> _parseSpecialties(Object? raw) {
    if (raw is List) return raw.map((e) => e.toString()).toList();
    if (raw is String && raw.trim().isNotEmpty) {
      return raw
          .split(',')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList();
    }
    return const [];
  }
}
