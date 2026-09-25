import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/config/api_config.dart';
import '../core/network/dio_client.dart';
import 'models/availability_model.dart';
import 'models/barber_model.dart';
import 'models/booking_model.dart';
import 'models/service_model.dart';
import 'payment_gateway.dart';
import 'repositories/availability_repository.dart';
import 'repositories/auth_repository.dart';
import 'repositories/booking_repository.dart';
import 'repositories/catalog_repository.dart';
import 'repositories/mock_repositories.dart';

/// `true` while backend phases 1–3 are incomplete (mock repositories +
/// simulated Razorpay). Flip with `--dart-define=USE_MOCK_API=false`.
final useMockApiProvider = Provider<bool>((ref) => ApiConfig.useMockApi);

// ------------------------------------------------------------- repositories
// Same interfaces for both modes — switching is config-only.

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  if (ref.watch(useMockApiProvider)) return MockAuthRepository();
  return ApiAuthRepository(ref.watch(dioProvider));
});

final catalogRepositoryProvider = Provider<CatalogRepository>((ref) {
  if (ref.watch(useMockApiProvider)) return MockCatalogRepository();
  return ApiCatalogRepository(ref.watch(dioProvider));
});

final availabilityRepositoryProvider =
    Provider<AvailabilityRepository>((ref) {
  if (ref.watch(useMockApiProvider)) return MockAvailabilityRepository();
  return ApiAvailabilityRepository(ref.watch(dioProvider));
});

final bookingRepositoryProvider = Provider<BookingRepository>((ref) {
  if (ref.watch(useMockApiProvider)) return MockBookingRepository();
  return ApiBookingRepository(ref.watch(dioProvider));
});

/// Payment sheet only — repositories stay governed by [useMockApiProvider]
/// (`USE_MOCK_API`). The mock sheet also opens when the compile-time
/// `PAYMENT_MOCK` define is true, so local testing can pair the real API with
/// a simulated Razorpay success (`ApiConfig.paymentMock`).
final paymentGatewayProvider = Provider<PaymentGateway>((ref) {
  if (ref.watch(useMockApiProvider) || ApiConfig.paymentMock) {
    return const MockPaymentGateway();
  }
  return const RazorpayPaymentGateway();
});

// ---------------------------------------------------------------- catalog

final servicesProvider = FutureProvider<List<ServiceItem>>((ref) async {
  final items = await ref.watch(catalogRepositoryProvider).services();
  return items.where((s) => s.isActive).toList();
});

final barbersProvider = FutureProvider<List<Barber>>(
  (ref) => ref.watch(catalogRepositoryProvider).barbers(),
);

final barberProvider = FutureProvider.family<Barber, int>(
  (ref, id) => ref.watch(catalogRepositoryProvider).barber(id),
);

// ------------------------------------------------------------ availability

/// Identity of one availability query (`GET /barbers/{id}/availability`).
class AvailabilityQuery {
  const AvailabilityQuery({
    required this.barberId,
    required this.date,
    required this.serviceId,
    this.addons = const [],
  });

  final int barberId;
  final String date; // YYYY-MM-DD (Asia/Kolkata day)
  final int serviceId;
  final List<String> addons;

  @override
  bool operator ==(Object other) =>
      other is AvailabilityQuery &&
      other.barberId == barberId &&
      other.date == date &&
      other.serviceId == serviceId &&
      other.addons.length == addons.length &&
      [...other.addons].every(addons.contains);

  @override
  int get hashCode =>
      Object.hash(barberId, date, serviceId, Object.hashAll(addons));
}

/// Always refetched from the API — `autoDispose` drops the cached grid when
/// the picker leaves the tree, so each screen open hits the endpoint again
/// (contract integration note: local state is a UI hint only).
final availabilityProvider = FutureProvider.autoDispose
    .family<Availability, AvailabilityQuery>((ref, query) {
  return ref.watch(availabilityRepositoryProvider).availability(
        barberId: query.barberId,
        date: query.date,
        serviceId: query.serviceId,
        addons: query.addons,
      );
});

// --------------------------------------------------------------- bookings

final myBookingsProvider = FutureProvider<List<Booking>>(
  (ref) => ref.watch(bookingRepositoryProvider).myBookings(),
);
