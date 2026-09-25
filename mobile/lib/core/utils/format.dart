import 'package:intl/intl.dart';

/// India-localized display helpers (₹ amounts, durations, dates).
/// API datetimes are UTC RFC3339; always display in Asia/Kolkata.
abstract final class AppFormat {
  static const Duration kIst = Duration(hours: 5, minutes: 30);

  static final NumberFormat _inr = NumberFormat.currency(
    locale: 'en_IN',
    symbol: '₹',
    decimalDigits: 0,
  );

  /// `100` → `₹100`, `100000` → `₹1,00,000` (Indian grouping, no decimals).
  static String rupees(num amount) => _inr.format(amount);

  /// `75` → `1h 15m`, `30` → `30m`, `60` → `1h`.
  static String duration(int minutes) {
    final h = minutes ~/ 60;
    final m = minutes % 60;
    if (h == 0) return '${m}m';
    if (m == 0) return '${h}h';
    return '${h}h ${m}m';
  }

  /// Booking/API datetimes are UTC RFC3339; display in Asia/Kolkata.
  static String dateTimeInKolkata(DateTime utc) {
    final ist = utc.toUtc().add(kIst);
    return DateFormat('d MMM yyyy, h:mm a').format(ist);
  }

  /// Date-only label in IST, e.g. `24 Sep 2026`.
  static String dateInKolkata(DateTime utc) {
    final ist = utc.toUtc().add(kIst);
    return DateFormat('d MMM yyyy').format(ist);
  }

  /// Time-only label in IST, e.g. `10:00 am` (slot chips).
  static String timeInKolkata(DateTime utc) {
    final ist = utc.toUtc().add(kIst);
    return DateFormat('h:mm a').format(ist).toLowerCase();
  }

  /// `2026-09-24` for the calendar day of an instant (Asia/Kolkata).
  static String isoDate(DateTime day) {
    final ist = day.toUtc().add(kIst);
    return DateFormat('yyyy-MM-dd').format(ist);
  }

  /// Current IST instant, labeled UTC (wall-clock reads Asia/Kolkata).
  static DateTime istNow() => DateTime.now().toUtc().add(kIst);

  /// Midnight IST for `addDays` from today — the "date picker" day model.
  static DateTime istDay(int addDays) {
    final now = istNow();
    final today = DateTime.utc(now.year, now.month, now.day);
    return today.add(Duration(days: addDays));
  }

  /// ISO date for a day produced by [istDay] (components already Asia/Kolkata).
  static String isoDateFromIstDay(DateTime istDay) =>
      DateFormat('yyyy-MM-dd').format(
    DateTime.utc(istDay.year, istDay.month, istDay.day),
  );

  /// Date-chip label, e.g. `Thu 24`.
  static String dayChipLabel(DateTime istDay) =>
      DateFormat('EEE d').format(istDay);

  /// True when the day is today's calendar day in Asia/Kolkata.
  static bool isToday(DateTime istDay) {
    final now = istNow();
    return istDay.year == now.year &&
        istDay.month == now.month &&
        istDay.day == now.day;
  }

  /// Hold countdown `m:ss` (hold TTL is 12 minutes → max `11:59`).
  static String countdown(Duration remaining) {
    if (remaining.isNegative) return '0:00';
    final total = remaining.inSeconds;
    final m = total ~/ 60;
    final s = total % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  /// RFC3339 UTC without milliseconds — `2026-09-24T04:30:00Z`.
  static String apiTimestamp(DateTime instant) {
    final iso = instant.toUtc().toIso8601String();
    return iso.replaceFirst(RegExp(r'\.\d+Z$'), 'Z');
  }

  /// Contract guest_phone: 10 digits after an optional `+91` / `0` prefix.
  /// Returns the normalized 10-digit number, or `null` when invalid.
  static String? normalizeIndianPhone(String? raw) {
    if (raw == null) return null;
    var s = raw.trim().replaceAll(RegExp(r'[\s\-( )]'), '');
    if (s.startsWith('+91')) s = s.substring(3);
    if (s.startsWith('0')) s = s.substring(1);
    if (RegExp(r'^\d{10}$').hasMatch(s)) return s;
    return null;
  }
}
