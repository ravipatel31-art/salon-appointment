import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/core/utils/format.dart';

void main() {
  group('AppFormat.rupees', () {
    test('formats whole rupees with Indian grouping', () {
      expect(AppFormat.rupees(50), '₹50');
      expect(AppFormat.rupees(100), '₹100');
      expect(AppFormat.rupees(1000), '₹1,000');
      expect(AppFormat.rupees(100000), '₹1,00,000');
    });
  });

  group('AppFormat.duration', () {
    test('formats hours and minutes', () {
      expect(AppFormat.duration(15), '15m');
      expect(AppFormat.duration(30), '30m');
      expect(AppFormat.duration(60), '1h');
      expect(AppFormat.duration(75), '1h 15m');
      expect(AppFormat.duration(90), '1h 30m');
      expect(AppFormat.duration(120), '2h');
    });
  });

  group('AppFormat times', () {
    test('isoDate uses Asia/Kolkata calendar day', () {
      // 2026-09-24T00:30Z → 06:00 IST on 24 Sep.
      final utc = DateTime.utc(2026, 9, 24, 0, 30);
      expect(AppFormat.isoDate(utc), '2026-09-24');
      // 2026-09-23T19:30Z → 01:00 IST on 24 Sep.
      final lateUtc = DateTime.utc(2026, 9, 23, 19, 30);
      expect(AppFormat.isoDate(lateUtc), '2026-09-24');
    });

    test('dateTimeInKolkata converts UTC to IST display', () {
      final utc = DateTime.utc(2026, 9, 24, 4, 30);
      expect(AppFormat.dateTimeInKolkata(utc), '24 Sep 2026, 10:00 AM');
    });

    test('timeInKolkata renders slot chips in IST', () {
      expect(AppFormat.timeInKolkata(DateTime.utc(2026, 9, 24, 4, 30)),
          '10:00 am');
      expect(AppFormat.timeInKolkata(DateTime.utc(2026, 9, 24, 10, 0)),
          '3:30 pm');
    });

    test('dateInKolkata renders a date-only IST label', () {
      expect(
        AppFormat.dateInKolkata(DateTime.utc(2026, 9, 23, 19, 30)),
        '24 Sep 2026',
      );
    });
  });

  group('AppFormat IST day helpers', () {
    test('isoDateFromIstDay keeps the IST wall-clock date', () {
      final istDay = DateTime.utc(2026, 9, 24);
      expect(AppFormat.isoDateFromIstDay(istDay), '2026-09-24');
      expect(AppFormat.dayChipLabel(istDay), 'Thu 24');
    });

    test('istDay(0) is today in Asia/Kolkata', () {
      final today = AppFormat.istDay(0);
      expect(AppFormat.isToday(today), isTrue);
      expect(AppFormat.istDay(1).difference(today), const Duration(days: 1));
    });
  });

  group('AppFormat.countdown', () {
    test('formats the 12-minute hold as m:ss', () {
      expect(AppFormat.countdown(const Duration(minutes: 11, seconds: 59)),
          '11:59');
      expect(AppFormat.countdown(const Duration(seconds: 9)), '0:09');
      expect(AppFormat.countdown(Duration.zero), '0:00');
      expect(
        AppFormat.countdown(const Duration(minutes: -1)),
        '0:00',
      );
    });
  });

  group('AppFormat.apiTimestamp', () {
    test('emits contract-style RFC3339 UTC without milliseconds', () {
      expect(
        AppFormat.apiTimestamp(DateTime.utc(2026, 9, 24, 4, 30)),
        '2026-09-24T04:30:00Z',
      );
      expect(
        AppFormat.apiTimestamp(
          DateTime.utc(2026, 9, 24, 4, 30).add(const Duration(minutes: 75)),
        ),
        '2026-09-24T05:45:00Z',
      );
    });
  });

  group('AppFormat.normalizeIndianPhone (contract guest_phone)', () {
    test('accepts 10-digit, +91 and 0-prefixed input', () {
      expect(AppFormat.normalizeIndianPhone('9876543210'), '9876543210');
      expect(AppFormat.normalizeIndianPhone('+91 98765 43210'), '9876543210');
      expect(AppFormat.normalizeIndianPhone('+919876543210'), '9876543210');
      expect(AppFormat.normalizeIndianPhone('09876543210'), '9876543210');
      expect(AppFormat.normalizeIndianPhone('98765-43210'), '9876543210');
      expect(AppFormat.normalizeIndianPhone('  9876543210 '), '9876543210');
    });

    test('rejects invalid lengths and null', () {
      expect(AppFormat.normalizeIndianPhone('12345'), isNull);
      expect(AppFormat.normalizeIndianPhone('98765432100'), isNull);
      expect(AppFormat.normalizeIndianPhone('987654321'), isNull);
      expect(AppFormat.normalizeIndianPhone('abcdefghij'), isNull);
      expect(AppFormat.normalizeIndianPhone(''), isNull);
      expect(AppFormat.normalizeIndianPhone(null), isNull);
    });
  });
}
