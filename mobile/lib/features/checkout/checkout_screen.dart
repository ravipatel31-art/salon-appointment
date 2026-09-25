import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_exception.dart';
import '../../core/network/auth_token_store.dart';
import '../../core/utils/format.dart';
import '../../core/utils/pricing.dart';
import '../../core/widgets/service_art.dart';
import '../../data/payment_gateway.dart';
import '../../data/providers.dart';
import '../auth/auth_controller.dart';
import '../booking/booking_state.dart';

/// Booking summary + `POST /bookings` → Razorpay pay advance flow.
///
/// Guest checkout (contract 2026-09-24): with no session, name + phone are
/// collected here and sent as `guest_name`/`guest_phone` without a Bearer
/// token; the returned `access_token` is stored for verify/cancel/list.
/// Pay is never blocked on login — an optional "Log in instead" link only
/// appears before the booking is created.
class CheckoutScreen extends ConsumerStatefulWidget {
  const CheckoutScreen({super.key});

  @override
  ConsumerState<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends ConsumerState<CheckoutScreen> {
  Timer? _timer;
  bool _creating = false;

  final _guestNameCtrl = TextEditingController();
  final _guestPhoneCtrl = TextEditingController();
  String? _guestNameError;
  String? _guestPhoneError;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _guestNameCtrl.dispose();
    _guestPhoneCtrl.dispose();
    super.dispose();
  }

  void _tick() {
    if (!mounted) return;
    final pending = ref.read(pendingPaymentProvider);
    if (pending == null) {
      // Nothing to count down — keep the timer idle (no setState → no churn).
      return;
    }
    if (pending.holdExpired) {
      _timer?.cancel();
      _timer = null;
    }
    setState(() {}); // refresh the hold countdown label
  }

  /// Back to the slot picker. Checkout may have been re-entered with
  /// `context.go` (payment retry), which replaces the router stack and leaves
  /// nothing to pop — fall back to the barber detail route from the draft.
  void _backToPicker() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    final draft = ref.read(bookingDraftProvider);
    final barber = draft.barber;
    final service = draft.service;
    if (barber == null || service == null) {
      context.go('/barbers');
      return;
    }
    final addons = draft.addons.join(',');
    final query = addons.isEmpty
        ? '?service_id=${service.id}'
        : '?service_id=${service.id}&addons=$addons';
    context.go('/barbers/${barber.id}$query');
  }

  /// Validates the guest identity fields (contract: name ≤ 80 chars, phone =
  /// 10 digits after optional `+91`/`0`). Returns normalized values or null.
  ({String name, String phone})? _validateGuestIdentity() {
    final name = _guestNameCtrl.text.trim();
    final phone = AppFormat.normalizeIndianPhone(_guestPhoneCtrl.text);
    final nameError = name.isEmpty || name.length > 80
        ? 'Enter your name (max 80 characters)'
        : null;
    final phoneError = phone == null
        ? 'Enter a 10-digit Indian mobile number'
        : null;
    setState(() {
      _guestNameError = nameError;
      _guestPhoneError = phoneError;
    });
    if (nameError != null || phone == null) return null;
    return (name: name, phone: phone);
  }

  Future<void> _startPayment() async {
    final draft = ref.read(bookingDraftProvider);
    final service = draft.service;
    final barber = draft.barber;
    final startAt = draft.startAt;
    if (service == null || barber == null || startAt == null) return;

    // No session → guest checkout: collect name + phone, never force login.
    final hasSession = ref.read(authTokenProvider) != null;
    String? guestName;
    String? guestPhone;
    if (!hasSession) {
      final identity = _validateGuestIdentity();
      if (identity == null) return;
      guestName = identity.name;
      guestPhone = identity.phone;
    }

    setState(() => _creating = true);
    try {
      var pending = ref.read(pendingPaymentProvider);
      if (pending == null || pending.holdExpired) {
        if (pending != null) {
          ref.read(pendingPaymentProvider.notifier).clear();
        }
        final result =
            await ref.read(bookingRepositoryProvider).createBooking(
                  serviceId: service.id,
                  addons: draft.addons,
                  barberId: barber.id,
                  startAt: startAt,
                  guestName: guestName,
                  guestPhone: guestPhone,
                );
        // Guest create returns `access_token` — store it (token store) so
        // verify-payment / cancel / list run without a login wall.
        if (result.hasNewSession && ref.read(authTokenProvider) == null) {
          ref.read(authControllerProvider.notifier).adoptSession(
                accessToken: result.accessToken!,
                user: result.user,
              );
        }
        pending = PendingPayment(
          booking: result.booking,
          payment: result.payment,
        );
        ref.read(pendingPaymentProvider.notifier).set(pending);
        _ensureTimer();
      }
      if (!mounted) return;
      await _openGateway(pending);
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.isSlotUnavailable) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('That slot was just taken. Pick another time.'),
          ),
        );
        _backToPicker(); // back to the slot picker
      } else {        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.detail)));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not start payment: $e')),
      );
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  /// Opens the configured gateway (real Razorpay, or the simulate sheet when
  /// `USE_MOCK_API=true` or the `PAYMENT_MOCK` dart-define is set). With both
  /// defines on, this sheet is mock but verify below still calls the real API
  /// with the mock signature (accepted only when the API runs `RAZORPAY_MOCK=1`).
  Future<void> _openGateway(PendingPayment pending) async {
    final outcome = await ref.read(paymentGatewayProvider).pay(
          context: context,
          keyId: pending.payment.keyId,
          orderId: pending.payment.razorpayOrderId,
          amountPaise: pending.payment.razorpayAmount,
          currency: pending.payment.razorpayCurrency,
          title: 'Salon',
          description: pending.booking.serviceName,
        );
    if (!mounted) return;
    switch (outcome) {
      case PaymentSuccess():
        ref.read(pendingPaymentProvider.notifier).setSuccess(outcome);
        context.go('/payment/processing');
      case PaymentCancelled():
        context.go('/payment/failed');
      case PaymentFailure(:final message):
        context.go(
          '/payment/failed?reason=${Uri.encodeComponent(message)}',
        );
    }
  }

  /// Optional secondary path — never blocks Pay. Only offered before the
  /// booking is created (contract: guest checkout is the primary path).
  void _goLogin() {
    context.push('/login');
  }

  void _ensureTimer() {
    if (_timer == null || !(_timer?.isActive ?? false)) {
      _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    }
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(bookingDraftProvider);
    final service = draft.service;
    final barber = draft.barber;
    final startAt = draft.startAt;

    if (service == null || barber == null || startAt == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Checkout')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.shopping_bag_outlined, size: 56),
                const SizedBox(height: 12),
                const Text(
                  'Choose a barber, then pick a service and time slot first.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => context.go('/barbers'),
                  child: const Text('Choose a barber'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final hasSession = ref.watch(authTokenProvider) != null;
    final pending = ref.watch(pendingPaymentProvider);
    final wash = draft.hasWash;
    final duration = Pricing.durationMinutes(service, wash: wash);
    final total = Pricing.onlineTotal(service, wash: wash);
    final advance = Pricing.advance(service, wash: wash);
    final balance = Pricing.balance(service, wash: wash);
    final expired = pending?.holdExpired ?? false;
    final canRetry = pending != null && !expired;

    return Scaffold(
      appBar: AppBar(title: const Text('Checkout')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ----------------------------------------------------- summary
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      ServiceArtChip(art: ServiceArt.forService(service)),
                      const SizedBox(width: 10),
                      Text(
                        'Summary',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _Row(label: 'Service', value: service.name),
                  _Row(label: 'Barber', value: barber.name),
                  _Row(
                    label: 'When',
                    value: AppFormat.dateTimeInKolkata(startAt),
                  ),
                  _Row(
                    label: 'Duration',
                    value: AppFormat.duration(duration),
                  ),
                  _Row(
                    label: 'Add-ons',
                    value: wash ? 'Wash (+₹30 · +15m)' : 'None',
                  ),
                  const Divider(height: 24),
                  if (service.isHairColor) ...[
                    Text(
                      '${AppFormat.rupees(Pricing.hairColorAdvance)} advance '
                      'online — actual price at center',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.primary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const _Row(
                      label: 'Advance online now',
                      value: '₹100',
                    ),
                  ] else ...[
                    _Row(label: 'Total', value: AppFormat.rupees(total!)),
                    _Row(
                      label: 'Advance online now',
                      value: AppFormat.rupees(advance),
                      emphasized: true,
                    ),
                    _Row(
                      label: 'Balance in-shop',
                      value: AppFormat.rupees(balance!),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // --------------------------------------------- guest identity
          // Shown only while there is no session; Pay stays enabled — the
          // optional login link never blocks checkout.
          if (!hasSession) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Booking as guest',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'No account needed — we\u2019ll use this to link your '
                      'booking for payment, tracking and cancellation.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      key: const Key('guest_name_field'),
                      controller: _guestNameCtrl,
                      decoration: InputDecoration(
                        labelText: 'Your name',
                        hintText: 'e.g. Rahul Sharma',
                        errorText: _guestNameError,
                      ),
                      textCapitalization: TextCapitalization.words,
                      maxLength: 80,
                    ),
                    const SizedBox(height: 4),
                    TextField(
                      key: const Key('guest_phone_field'),
                      controller: _guestPhoneCtrl,
                      decoration: InputDecoration(
                        labelText: 'Phone number',
                        hintText: '10-digit mobile',
                        prefixText: '+91 ',
                        errorText: _guestPhoneError,
                      ),
                      keyboardType: TextInputType.phone,
                      autofillHints: const [AutofillHints.telephoneNumber],
                    ),
                    if (pending == null)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton(
                          key: const Key('checkout_login_link'),
                          onPressed: _goLogin,
                          child: const Text('Log in instead'),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],

          // --------------------------------------------------- hold info
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: pending == null
                  ? const Text(
                      'Tapping pay creates a booking hold that lasts '
                      '12 minutes while you complete the payment.',
                    )
                  : expired
                      ? Text(
                          'Your 12-minute hold expired. Tap pay to create a '
                          'fresh hold for this slot.',
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                            fontWeight: FontWeight.w600,
                          ),
                        )
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Hold expires in '
                              '${AppFormat.countdown(pending.booking.holdRemaining())}',
                              key: const Key('hold_countdown'),
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.primary,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Booking ${pending.booking.bookingRef} · '
                              'status ${pending.booking.status.replaceAll('_', ' ')}',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                        ),
            ),
          ),
          const SizedBox(height: 20),

          // -------------------------------------------------------- pay
          FilledButton.icon(
            key: const Key('pay_button'),
            onPressed: _creating ? null : _startPayment,
            icon: _creating
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.lock_clock_outlined),
            label: Text(
              _creating
                  ? 'Please wait…'
                  : canRetry
                      ? 'Retry payment ${AppFormat.rupees(advance)}'
                      : 'Pay advance ${AppFormat.rupees(advance)}',
            ),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _backToPicker,
            child: const Text('Back'),
          ),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.label,
    required this.value,
    this.emphasized = false,
  });

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: TextStyle(
              fontWeight: emphasized ? FontWeight.w700 : FontWeight.w600,
              color: emphasized ? Theme.of(context).colorScheme.primary : null,
            ),
          ),
        ],
      ),
    );
  }
}
