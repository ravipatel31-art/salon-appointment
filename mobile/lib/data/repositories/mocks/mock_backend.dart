import '../../../core/network/api_exception.dart';
import '../../../core/utils/format.dart';
import '../../../core/utils/pricing.dart';
import '../../models/availability_model.dart';
import '../../models/barber_model.dart';
import '../../models/booking_model.dart';
import '../../models/service_model.dart';
import '../../models/user_model.dart';

/// In-memory stand-in for the FastAPI backend (phases 1–3 are incomplete).
///
/// Everything is contract-shaped so switching to the real API is a
/// `--dart-define=USE_MOCK_API=false` config flip (see `ApiConfig`).
class MockBackend {
  MockBackend._();

  static const Duration _holdTtl = Duration(minutes: 12);
  static const Duration _minCancelAhead = Duration(hours: 2);
  static const Duration _latency = Duration(milliseconds: 180);

  // ---------------------------------------------------------------- catalog

  /// Seed catalog from AGENTS.md — no invented prices.
  static final List<ServiceItem> services = [
    _fixed(1, 'Haircut', 100, 60, 'Precision cut, styled to finish.'),
    _fixed(2, 'Shaving', 70, 30, 'Clean shave with hot towel.'),
    _fixed(3, 'Beard trim', 50, 15, 'Shape-up and line-up.'),
    _fixed(4, 'Massage + Haircut', 200, 90, 'Relaxing head massage then haircut.'),
    _fixed(5, 'Shaving + Massage', 130, 60, 'Shave paired with a stress-buster massage.'),
    _fixed(8, 'Haircut + Shaving', 180, 90, 'Haircut paired with a clean shave.'),
    _fixed(9, 'Haircut + Beard trim', 130, 75, 'Haircut with a shape-up beard trim.'),
    _fixed(6, 'Full combo', 250, 120,
        'Haircut + beard trim + head massage + wash.'),
    const ServiceItem(
      id: 7,
      name: 'Hair color',
      description: 'Color service — pay ₹100 advance online, actual price at center.',
      durationMinutes: 90,
      price: 100,
      priceType: 'variable_advance',
      isActive: true,
      addons: [washAddon],
    ),
  ];

  static const ServiceAddon washAddon = ServiceAddon(
    id: 'wash',
    name: 'Wash',
    price: Pricing.washAddonPrice,
    durationMinutes: Pricing.washAddonMinutes,
  );

  static ServiceItem _fixed(int id, String name, int price, int minutes,
          String description) =>
      ServiceItem(
        id: id,
        name: name,
        description: description,
        durationMinutes: minutes,
        price: price,
        priceType: 'fixed',
        isActive: true,
        addons: const [washAddon],
      );

  static ServiceItem? serviceById(int id) {
    for (final s in services) {
      if (s.id == id) return s;
    }
    return null;
  }

  /// 5 seeded barbers. `photo_url` mirrors the live seed style (phase 11:
  /// stable public demo portraits on i.pravatar.cc) so mock and API mode
  /// share the same photo-with-fallback rendering path.
  static final List<Barber> barbers = const [
    Barber(
      id: 1,
      name: 'Aakash Mehta',
      photoUrl: 'https://i.pravatar.cc/300?u=salon-aakash-mehta',
      bio: '12 years behind the chair. Fades and classic cuts.',
      specialties: ['Fades', 'Classic cuts'],
      isActive: true,
    ),
    Barber(
      id: 2,
      name: 'Rohan Patil',
      photoUrl: 'https://i.pravatar.cc/300?u=salon-rohan-patil',
      bio: 'Beard architecture is a science — and an art.',
      specialties: ['Beard sculpting', 'Shaves'],
      isActive: true,
    ),
    Barber(
      id: 3,
      name: 'Imran Shaikh',
      photoUrl: 'https://i.pravatar.cc/300?u=salon-imran-shaikh',
      bio: 'Known for scissor work and kid-friendly patience.',
      specialties: ['Scissor cut', 'Kids'],
      isActive: true,
    ),
    Barber(
      id: 4,
      name: 'Vikram Singh',
      photoUrl: 'https://i.pravatar.cc/300?u=salon-vikram-singh',
      bio: 'Massage-trained stylist. Steadiest hands in town.',
      specialties: ['Massage', 'Styling'],
      isActive: true,
    ),
    Barber(
      id: 5,
      name: 'Suresh Iyer',
      photoUrl: 'https://i.pravatar.cc/300?u=salon-suresh-iyer',
      bio: 'Color specialist — global color and touch-ups.',
      specialties: ['Hair color', 'Highlights'],
      isActive: true,
    ),
  ];

  static Barber? barberById(int id) {
    for (final b in barbers) {
      if (b.id == id) return b;
    }
    return null;
  }

  // ------------------------------------------------------------------- auth

  static User? _currentUser;
  static String? _currentToken;
  static int _userSeq = 1;

  /// Phone directory of every customer seen (registered or guest) — powers
  /// the contract's find-or-create-by-phone on guest booking create.
  static final List<User> _directory = <User>[];

  static User? get currentUser => _currentUser;
  static String? get currentToken => _currentToken;

  static Future<AuthSession> login({
    required String identifier,
    required String password,
  }) async {
    await _delay();
    if (password.isEmpty) {
      throw const ApiException(statusCode: 400, detail: 'Password is required');
    }
    final isEmail = identifier.contains('@');
    _currentUser = User(
      id: ++_userSeq,
      name: isEmail ? identifier.split('@').first : 'Guest $identifier',
      phone: isEmail ? '' : identifier,
      email: isEmail ? identifier : 'user$identifier@example.com',
      role: 'customer',
    );
    _remember(_currentUser!);
    _currentToken = 'mock-access-token';
    return AuthSession(
      accessToken: _currentToken!,
      tokenType: 'bearer',
      user: _currentUser!,
    );
  }

  static Future<AuthSession> register({
    required String name,
    required String phone,
    required String email,
    required String password,
  }) async {
    await _delay();
    if (password.length < 6) {
      throw const ApiException(
        statusCode: 400,
        detail: 'Password must be at least 6 characters',
      );
    }
    _currentUser = User(
      id: ++_userSeq,
      name: name,
      phone: phone,
      email: email,
      role: 'customer',
    );
    _remember(_currentUser!);
    _currentToken = 'mock-access-token';
    return AuthSession(
      accessToken: _currentToken!,
      tokenType: 'bearer',
      user: _currentUser!,
    );
  }

  static Future<User> me() async {
    await _delay();
    final user = _currentUser;
    if (user == null) {
      throw const ApiException(statusCode: 401, detail: 'Not authenticated');
    }
    return user;
  }

  static void logout() {
    _currentUser = null;
    _currentToken = null;
  }

  static void _remember(User user) {
    final phone = AppFormat.normalizeIndianPhone(user.phone) ?? user.phone;
    if (phone.isEmpty) return; // email-only logins aren't phone directory keys
    for (var i = 0; i < _directory.length; i++) {
      final existing = _directory[i].phone;
      final up = AppFormat.normalizeIndianPhone(existing) ?? existing;
      if (up == phone) {
        _directory[i] = user;
        return;
      }
    }
    _directory.add(user);
  }

  /// Contract find-or-create: match an existing customer by normalized phone,
  /// else create a new `role=customer` (guest) row. Never overwrites the
  /// existing profile of a matched user.
  static User _findOrCreateCustomer({required String name, required String phone}) {
    for (final u in _directory) {
      final up = AppFormat.normalizeIndianPhone(u.phone) ?? u.phone;
      if (up == phone) return u;
    }
    final created = User(
      id: ++_userSeq,
      name: name,
      phone: phone,
      email: '',
      role: 'customer',
    );
    _directory.add(created);
    return created;
  }

  // ------------------------------------------------------------ availability

  /// Shop hours (Asia/Kolkata): 09:00–21:00, all days, 15-min grid.
  static DateTime openUtcFor(DateTime istDay) => DateTime.utc(
        istDay.year,
        istDay.month,
        istDay.day,
        9,
      ).subtract(AppFormat.kIst);

  static DateTime closeUtcFor(DateTime istDay) => DateTime.utc(
        istDay.year,
        istDay.month,
        istDay.day,
        21,
      ).subtract(AppFormat.kIst);

  static Future<Availability> availability({
    required int barberId,
    required String date,
    required int serviceId,
    List<String> addons = const [],
  }) async {
    await _delay();
    final service = serviceById(serviceId);
    if (service == null) {
      throw const ApiException(statusCode: 404, detail: 'Service not found');
    }
    if (barberById(barberId) == null) {
      throw const ApiException(statusCode: 404, detail: 'Barber not found');
    }
    final duration = Pricing.durationMinutes(
      service,
      wash: Pricing.hasWash(addons),
    );
    return buildAvailability(
      barberId: barberId,
      date: date,
      serviceId: serviceId,
      duration: duration,
      bookings: _bookings,
      nowUtc: DateTime.now().toUtc(),
      seed: serviceId,
    );
  }

  /// Pure generator shared by `GET availability` and the mock overlap check.
  static Availability buildAvailability({
    required int barberId,
    required String date,
    required int serviceId,
    required int duration,
    required List<Booking> bookings,
    required DateTime nowUtc,
    int seed = 0,
  }) {
    final parts = date.split('-');
    final istDay = DateTime.utc(
      int.parse(parts[0]),
      int.parse(parts[1]),
      int.parse(parts[2]),
    );
    final open = openUtcFor(istDay);
    final close = closeUtcFor(istDay);
    final step = const Duration(minutes: 15);
    final slots = <AvailabilitySlot>[];

    var index = 0;
    for (var start = open;
        start.add(Duration(minutes: duration)).compareTo(close) <= 0;
        start = start.add(step), index++) {
      final end = start.add(Duration(minutes: duration));
      var available = true;

      // Past times are excluded for today.
      if (!start.isAfter(nowUtc)) available = false;

      // Deterministic "busy" pattern so the UI shows a realistic mix.
      if ((index * 3 + barberId + istDay.day + seed) % 11 == 0) {
        available = false;
      }

      // Overlaps with pending_payment / confirmed bookings.
      for (final b in bookings) {
        if (b.barberId != barberId) continue;
        final status = b.status;
        if (status != BookingStatus.pendingPayment &&
            status != BookingStatus.confirmed) {
          continue;
        }
        if (start.isBefore(b.endAt) && b.startAt.isBefore(end)) {
          available = false;
          break;
        }
      }

      slots.add(AvailabilitySlot(startAt: start, available: available));
    }

    return Availability(
      barberId: barberId,
      date: date,
      serviceId: serviceId,
      durationMinutes: duration,
      slots: slots,
    );
  }

  // --------------------------------------------------------------- bookings

  static final List<Booking> _bookings = <Booking>[];
  static bool _seeded = false;
  static int _bookingSeq = 40;
  static int _orderSeq = 1000;

  static List<Booking> _ensureSeeded() {
    if (_seeded) return _bookings;
    _seeded = true;
    final now = DateTime.now().toUtc();

    // Past completed haircut (shows under "Past").
    _bookings.add(
      _seedBooking(
        serviceId: 1,
        addons: const ['wash'],
        barberId: 1,
        startAt: AppFormat.istDay(-3).add(const Duration(hours: 11)).subtract(AppFormat.kIst),
        status: BookingStatus.completed,
        now: now,
        paidFraction: true,
      ),
    );

    // Past cancelled shave.
    _bookings.add(
      _seedBooking(
        serviceId: 2,
        addons: const [],
        barberId: 2,
        startAt: AppFormat.istDay(-6).add(const Duration(hours: 17)).subtract(AppFormat.kIst),
        status: BookingStatus.cancelled,
        now: now,
        paidFraction: false,
      ),
    );

    // Upcoming confirmed combo tomorrow evening.
    _bookings.add(
      _seedBooking(
        serviceId: 4,
        addons: const [],
        barberId: 3,
        startAt: AppFormat.istDay(1).add(const Duration(hours: 18)).subtract(AppFormat.kIst),
        status: BookingStatus.confirmed,
        now: now,
        paidFraction: true,
      ),
    );
    return _bookings;
  }

  static Booking _seedBooking({
    required int serviceId,
    required List<String> addons,
    required int barberId,
    required DateTime startAt,
    required String status,
    required DateTime now,
    required bool paidFraction,
  }) {
    final service = serviceById(serviceId)!;
    final wash = Pricing.hasWash(addons);
    final duration = Pricing.durationMinutes(service, wash: wash);
    final amounts = _amounts(service, wash);
    return Booking(
      id: 'seed-$serviceId-$barberId-${startAt.millisecondsSinceEpoch}',
      bookingRef: _ref(startAt),
      status: status,
      serviceId: serviceId,
      barberId: barberId,
      addons: addons,
      startAt: startAt,
      endAt: startAt.add(Duration(minutes: duration)),
      durationMinutes: duration,
      totalAmount: amounts.total,
      advanceAmount: amounts.advance,
      balanceAmount: amounts.balance,
      onlineAmountPaid: paidFraction ? amounts.advance : 0,
      expiresAt: now.add(_holdTtl),
      serviceName: service.name,
      barberName: barberById(barberId)?.name,
    );
  }

  static ({int total, int advance, int balance}) _amounts(
    ServiceItem service,
    bool wash,
  ) {
    if (service.isVariableAdvance) {
      // Hair color: ₹100 flat online; final price collected at the center.
      return (total: Pricing.hairColorAdvance, advance: Pricing.hairColorAdvance, balance: 0);
    }
    final total = Pricing.onlineTotal(service, wash: wash)!;
    final advance = Pricing.advance(service, wash: wash);
    return (total: total, advance: advance, balance: total - advance);
  }

  static String _ref(DateTime startUtc) {
    final ist = startUtc.toUtc().add(AppFormat.kIst);
    final ymd = AppFormat.isoDateFromIstDay(ist).replaceAll('-', '');
    return 'SL-$ymd-${(_bookingSeq++).toString().padLeft(4, '0')}';
  }

  static Future<CreateBookingResponse> createBooking({
    required int serviceId,
    required List<String> addons,
    required int barberId,
    required DateTime startAt,
    String notes = '',
    String? guestName,
    String? guestPhone,
  }) async {
    await _delay();
    _ensureSeeded();
    final service = serviceById(serviceId);
    if (service == null) {
      throw const ApiException(statusCode: 404, detail: 'Service not found');
    }
    if (barberById(barberId) == null) {
      throw const ApiException(statusCode: 404, detail: 'Barber not found');
    }

    // Guest identity (contract 2026-09-24): no session → guest_name +
    // guest_phone required; find-or-create customer by phone and issue a
    // guest-session token. With a session the guest fields are ignored and
    // no token is returned.
    final authenticated = _currentToken != null;
    User? issuedUser;
    String? issuedToken;
    if (!authenticated) {
      final name = (guestName ?? '').trim();
      final phone = AppFormat.normalizeIndianPhone(guestPhone);
      if (name.isEmpty || name.length > 80 || phone == null) {
        throw const ApiException(
          statusCode: 400,
          detail: 'guest_identity_required',
        );
      }
      issuedUser = _findOrCreateCustomer(name: name, phone: phone);
      issuedToken = 'mock-guest-token-${issuedUser.id}-'
          '${DateTime.now().microsecondsSinceEpoch}';
      _currentUser = issuedUser;
      _currentToken = issuedToken;
    }

    final wash = Pricing.hasWash(addons);
    final duration = Pricing.durationMinutes(service, wash: wash);
    final now = DateTime.now().toUtc();
    final start = startAt.toUtc();
    final end = start.add(Duration(minutes: duration));

    // 15-min grid alignment check.
    if (start.minute % 15 != 0 || start.second != 0) {
      throw const ApiException(
        statusCode: 422,
        detail: 'start_at must align to the 15-minute slot grid',
      );
    }

    // Live availability re-check (contract conflict → 409 slot_unavailable).
    final date = AppFormat.isoDate(start);
    final availability = buildAvailability(
      barberId: barberId,
      date: date,
      serviceId: serviceId,
      duration: duration,
      bookings: _bookings,
      nowUtc: now,
      seed: serviceId,
    );
    final slotOk = availability.slots.any(
      (s) => s.startAt.isAtSameMomentAs(start) && s.available,
    );
    if (!slotOk) {
      throw const ApiException(
        statusCode: 409,
        detail: 'slot_unavailable',
      );
    }

    final amounts = _amounts(service, wash);
    final expiresAt = now.add(_holdTtl);
    final booking = Booking(
      id: 'bk_${now.microsecondsSinceEpoch}_${++_bookingSeq}',
      bookingRef: _ref(start),
      status: BookingStatus.pendingPayment,
      serviceId: serviceId,
      barberId: barberId,
      addons: addons,
      startAt: start,
      endAt: end,
      durationMinutes: duration,
      totalAmount: amounts.total,
      advanceAmount: amounts.advance,
      balanceAmount: amounts.balance,
      onlineAmountPaid: 0,
      expiresAt: expiresAt,
      serviceName: service.name,
      barberName: barberById(barberId)?.name,
    );
    _bookings.insert(0, booking);

    final payment = PaymentOptions(
      razorpayOrderId: 'order_MOCK${++_orderSeq}',
      razorpayAmount: amounts.advance * 100, // paise
      razorpayCurrency: 'INR',
      keyId: 'rzp_test_MockPhase5Key',
    );
    return CreateBookingResponse(
      booking: booking,
      payment: payment,
      accessToken: issuedToken,
      tokenType: issuedToken == null ? null : 'bearer',
      user: issuedUser,
    );
  }

  static Future<Booking> verifyPayment({
    required String bookingId,
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  }) async {
    await _delay(_latency + const Duration(milliseconds: 120));
    _ensureSeeded();
    if (razorpayOrderId.isEmpty ||
        razorpayPaymentId.isEmpty ||
        razorpaySignature.isEmpty) {
      throw const ApiException(
        statusCode: 400,
        detail: 'Payment verification failed',
      );
    }
    final idx = _bookings.indexWhere((b) => b.id == bookingId);
    if (idx == -1) {
      throw const ApiException(statusCode: 404, detail: 'Booking not found');
    }
    final booking = _bookings[idx];
    final now = DateTime.now().toUtc();
    if (booking.status != BookingStatus.pendingPayment) {
      if (booking.status == BookingStatus.confirmed) return booking;
      throw const ApiException(
        statusCode: 400,
        detail: 'Payment verification failed: booking is no longer payable',
      );
    }
    if (now.isAfter(booking.expiresAt)) {
      throw const ApiException(
        statusCode: 400,
        detail: 'Payment verification failed: hold expired',
      );
    }
    final confirmed = _copy(booking, status: BookingStatus.confirmed, paid: booking.advanceAmount);
    _bookings[idx] = confirmed;
    return confirmed;
  }

  static Future<List<Booking>> myBookings() async {
    await _delay();
    final list = List<Booking>.from(_ensureSeeded());
    list.sort((a, b) => b.startAt.compareTo(a.startAt));
    return list;
  }

  static Future<Booking> booking(String id) async {
    await _delay();
    _ensureSeeded();
    final idx = _bookings.indexWhere((b) => b.id == id);
    if (idx == -1) {
      throw const ApiException(statusCode: 404, detail: 'Booking not found');
    }
    return _bookings[idx];
  }

  static Future<Booking> cancelBooking(String id) async {
    await _delay();
    _ensureSeeded();
    final idx = _bookings.indexWhere((b) => b.id == id);
    if (idx == -1) {
      throw const ApiException(statusCode: 404, detail: 'Booking not found');
    }
    final booking = _bookings[idx];
    final now = DateTime.now().toUtc();
    if (booking.startAt.difference(now) < _minCancelAhead) {
      throw const ApiException(
        statusCode: 403,
        detail: 'Cancel at least 2 hours before the appointment',
      );
    }
    final next = booking.onlineAmountPaid > 0
        ? _copy(booking, status: BookingStatus.refunded)
        : _copy(booking, status: BookingStatus.cancelled);
    _bookings[idx] = next;
    return next;
  }

  static Booking _copy(
    Booking b, {
    String? status,
    int? paid,
  }) =>
      Booking(
        id: b.id,
        bookingRef: b.bookingRef,
        status: status ?? b.status,
        serviceId: b.serviceId,
        barberId: b.barberId,
        addons: b.addons,
        startAt: b.startAt,
        endAt: b.endAt,
        durationMinutes: b.durationMinutes,
        totalAmount: b.totalAmount,
        advanceAmount: b.advanceAmount,
        balanceAmount: b.balanceAmount,
        onlineAmountPaid: paid ?? b.onlineAmountPaid,
        expiresAt: b.expiresAt,
        serviceName: b.serviceName,
        barberName: b.barberName,
        finalPriceAtCenter: b.finalPriceAtCenter,
        balanceDue: b.balanceDue,
      );

  /// Reset — used by tests.
  static void resetForTest() {
    _bookings.clear();
    _seeded = false;
    _bookingSeq = 40;
    _orderSeq = 1000;
    _currentUser = null;
    _currentToken = null;
    _userSeq = 1;
    _directory.clear();
  }

  static Future<void> _delay([Duration? d]) =>
      Future<void>.delayed(d ?? _latency);
}
