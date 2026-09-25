import '../models/availability_model.dart';
import '../models/barber_model.dart';
import '../models/booking_model.dart';
import '../models/service_model.dart';
import '../models/user_model.dart';
import 'availability_repository.dart';
import 'auth_repository.dart';
import 'booking_repository.dart';
import 'catalog_repository.dart';
import 'mocks/mock_backend.dart';

/// Repository implementations backed by [MockBackend].
///
/// They share the exact interfaces as the `Api*` classes, so flipping
/// `USE_MOCK_API=false` is the only change needed once phases 1–3 are done.
class MockAuthRepository implements AuthRepository {
  @override
  Future<AuthSession> register({
    required String name,
    required String phone,
    required String email,
    required String password,
  }) =>
      MockBackend.register(
        name: name,
        phone: phone,
        email: email,
        password: password,
      );

  @override
  Future<AuthSession> login({
    required String identifier,
    required String password,
  }) =>
      MockBackend.login(identifier: identifier, password: password);

  @override
  Future<User> me() => MockBackend.me();
}

class MockCatalogRepository implements CatalogRepository {
  @override
  Future<List<ServiceItem>> services() async {
    await Future<void>.delayed(const Duration(milliseconds: 120));
    return MockBackend.services;
  }

  @override
  Future<List<Barber>> barbers() async {
    await Future<void>.delayed(const Duration(milliseconds: 120));
    return MockBackend.barbers;
  }

  @override
  Future<Barber> barber(int id) async {
    await Future<void>.delayed(const Duration(milliseconds: 120));
    final barber = MockBackend.barberById(id);
    if (barber == null) {
      throw Exception('Barber not found');
    }
    return barber;
  }
}

class MockAvailabilityRepository implements AvailabilityRepository {
  @override
  Future<Availability> availability({
    required int barberId,
    required String date,
    required int serviceId,
    List<String> addons = const [],
  }) =>
      MockBackend.availability(
        barberId: barberId,
        date: date,
        serviceId: serviceId,
        addons: addons,
      );
}

class MockBookingRepository implements BookingRepository {
  @override
  Future<CreateBookingResponse> createBooking({
    required int serviceId,
    required List<String> addons,
    required int barberId,
    required DateTime startAt,
    String notes = '',
    String? guestName,
    String? guestPhone,
  }) =>
      MockBackend.createBooking(
        serviceId: serviceId,
        addons: addons,
        barberId: barberId,
        startAt: startAt,
        notes: notes,
        guestName: guestName,
        guestPhone: guestPhone,
      );

  @override
  Future<Booking> verifyPayment({
    required String bookingId,
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  }) =>
      MockBackend.verifyPayment(
        bookingId: bookingId,
        razorpayOrderId: razorpayOrderId,
        razorpayPaymentId: razorpayPaymentId,
        razorpaySignature: razorpaySignature,
      );

  @override
  Future<List<Booking>> myBookings() => MockBackend.myBookings();

  @override
  Future<Booking> booking(String id) => MockBackend.booking(id);

  @override
  Future<Booking> cancelBooking(String bookingId) =>
      MockBackend.cancelBooking(bookingId);
}
