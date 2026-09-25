/// Compile-time API configuration.
///
/// Pass `--dart-define=API_BASE_URL=https://api.example.com` at build/run time.
/// Default targets the Android emulator host loopback.
///
/// `USE_MOCK_API` selects the repository implementation behind the same
/// interfaces (see `lib/data/providers.dart`):
/// * `true` (default while backend phases 1–3 are incomplete) → in-memory mock
///   repositories + simulated Razorpay sheet.
/// * `false` → dio-backed API repositories + real `razorpay_flutter` checkout
///   (unless the separate `PAYMENT_MOCK` define below forces the mock sheet).
///
/// Swapping to the real backend is config-only:
/// `flutter run --dart-define=USE_MOCK_API=false --dart-define=API_BASE_URL=…`
abstract final class ApiConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// `true` → serve contract-shaped data from local mocks.
  static const bool useMockApi = bool.fromEnvironment(
    'USE_MOCK_API',
    defaultValue: true,
  );

  /// Test payment bypass (contract 2026-09-24): when `true`, open
  /// `MockPaymentGateway` (simulate sheet → `pay_MOCK*` / `sig_MOCK*`) even if
  /// `USE_MOCK_API=false` — repositories keep talking to the real API, and
  /// verify-payment still hits the real endpoint (accepted there only when the
  /// API runs with `RAZORPAY_MOCK=1`).
  ///
  /// Compile-time only: `--dart-define=PAYMENT_MOCK=true` (default `false`).
  /// **Never enable for Play Store / production builds** — omit the define or
  /// leave it `false` when shipping.
  static const bool paymentMock = bool.fromEnvironment(
    'PAYMENT_MOCK',
    defaultValue: false,
  );
}
