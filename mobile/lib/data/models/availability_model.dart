/// Contract `GET /barbers/{id}/availability` models.
class AvailabilitySlot {
  const AvailabilitySlot({required this.startAt, required this.available});

  /// Slot start (UTC, from RFC3339 `start_at`).
  final DateTime startAt;
  final bool available;

  factory AvailabilitySlot.fromJson(Map<String, dynamic> json) =>
      AvailabilitySlot(
        startAt: DateTime.parse(json['start_at'] as String).toUtc(),
        available: json['available'] as bool? ?? true,
      );
}

class Availability {
  const Availability({
    required this.barberId,
    required this.date,
    required this.serviceId,
    required this.durationMinutes,
    required this.slots,
  });

  final int barberId;
  final String date; // YYYY-MM-DD (Asia/Kolkata calendar day)
  final int serviceId;
  final int durationMinutes;
  final List<AvailabilitySlot> slots;

  factory Availability.fromJson(Map<String, dynamic> json) => Availability(
        barberId: (json['barber_id'] as num).toInt(),
        date: json['date'] as String? ?? '',
        serviceId: (json['service_id'] as num).toInt(),
        durationMinutes: (json['duration_minutes'] as num?)?.toInt() ?? 0,
        slots: [
          for (final s in (json['slots'] as List? ?? const []))
            AvailabilitySlot.fromJson((s as Map).cast<String, dynamic>()),
        ],
      );
}
