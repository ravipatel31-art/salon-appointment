import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:salon_mobile/core/config/api_config.dart';
import 'package:salon_mobile/data/payment_gateway.dart';
import 'package:salon_mobile/data/providers.dart';
import 'package:salon_mobile/data/repositories/booking_repository.dart';
import 'package:salon_mobile/data/repositories/mock_repositories.dart';

/// `PAYMENT_MOCK` is a compile-time `const` (`ApiConfig.paymentMock`) — it
/// cannot be flipped at runtime, only by rebuilding with
/// `--dart-define=PAYMENT_MOCK=true`. These tests pin the selection rules for
/// `paymentGatewayProvider` and its separation from `USE_MOCK_API`.
///
/// `useMockApiProvider` is always overridden so the suite passes under any
/// ambient `USE_MOCK_API` / `PAYMENT_MOCK` define combination.
void main() {
  ProviderContainer containerWith({required bool useMockApi}) {
    final container = ProviderContainer(
      overrides: [useMockApiProvider.overrideWithValue(useMockApi)],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('ApiConfig.paymentMock is a const bool (compile-time define only)',
      () {
    expect(ApiConfig.paymentMock, isA<bool>());
    // Default test runs omit the define → false. Re-running this suite with
    // `flutter test --dart-define=PAYMENT_MOCK=true` flips it for the whole
    // process; it never changes mid-run.
    if (!const bool.fromEnvironment('PAYMENT_MOCK', defaultValue: false)) {
      expect(ApiConfig.paymentMock, isFalse);
    }
    expect(ApiConfig.paymentMock, ApiConfig.paymentMock); // stable reads
  });

  test('USE_MOCK_API=true → MockPaymentGateway', () {
    final container = containerWith(useMockApi: true);

    expect(container.read(useMockApiProvider), isTrue);
    expect(
      container.read(paymentGatewayProvider),
      isA<MockPaymentGateway>(),
    );
  });

  test(
      'USE_MOCK_API=false → RazorpayPaymentGateway unless PAYMENT_MOCK is '
      'set at compile time', () {
    final container = containerWith(useMockApi: false);

    expect(container.read(useMockApiProvider), isFalse);
    final gateway = container.read(paymentGatewayProvider);
    if (ApiConfig.paymentMock) {
      // Built with --dart-define=PAYMENT_MOCK=true: mock sheet wins even
      // though repositories stay on the real API.
      expect(gateway, isA<MockPaymentGateway>());
    } else {
      expect(gateway, isA<RazorpayPaymentGateway>());
    }
  });

  test(
      'PAYMENT_MOCK=true (if defined) opens the mock sheet while '
      'repositories stay real API', () {
    final container = containerWith(useMockApi: false);

    // Selection rule under test: mock sheet ⇔ (useMockApi || paymentMock).
    final expectMockSheet =
        container.read(useMockApiProvider) || ApiConfig.paymentMock;
    expect(
      container.read(paymentGatewayProvider),
      expectMockSheet
          ? isA<MockPaymentGateway>()
          : isA<RazorpayPaymentGateway>(),
    );

    // Repositories are governed by USE_MOCK_API alone — still the dio-backed
    // API implementation regardless of PAYMENT_MOCK.
    expect(
      container.read(bookingRepositoryProvider),
      isA<ApiBookingRepository>(),
    );
    expect(
      container.read(bookingRepositoryProvider),
      isNot(isA<MockBookingRepository>()),
    );
  });

  test('USE_MOCK_API=true keeps mock repositories + mock sheet together', () {
    final container = containerWith(useMockApi: true);

    expect(
      container.read(bookingRepositoryProvider),
      isA<MockBookingRepository>(),
    );
    expect(
      container.read(paymentGatewayProvider),
      isA<MockPaymentGateway>(),
    );
  });
}
