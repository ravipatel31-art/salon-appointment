import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_exception.dart';
import '../../data/providers.dart';
import '../booking/booking_state.dart';

/// Runs `POST /bookings/{id}/verify-payment` after a successful Razorpay
/// checkout, then routes to success or the failure path.
///
/// Verify always hits the configured API (`USE_MOCK_API=false` → real server)
/// even when the sheet was simulated via `PAYMENT_MOCK` — with both defines
/// set, the mock signature is accepted only if the API has `RAZORPAY_MOCK=1`.
class ProcessingScreen extends ConsumerStatefulWidget {
  const ProcessingScreen({super.key});

  @override
  ConsumerState<ProcessingScreen> createState() => _ProcessingScreenState();
}

class _ProcessingScreenState extends ConsumerState<ProcessingScreen> {
  bool _started = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _verify());
  }

  Future<void> _verify() async {
    if (_started) return;
    _started = true;

    final pending = ref.read(pendingPaymentProvider);
    final success = pending?.success;
    if (pending == null || success == null) {
      if (mounted) context.go('/checkout');
      return;
    }

    try {
      final confirmed =
          await ref.read(bookingRepositoryProvider).verifyPayment(
                bookingId: pending.booking.id,
                razorpayOrderId: success.orderId,
                razorpayPaymentId: success.paymentId,
                razorpaySignature: success.signature,
              );
      ref.read(lastConfirmedProvider.notifier).set(confirmed);
      ref.read(pendingPaymentProvider.notifier).clear();
      ref.read(bookingDraftProvider.notifier).clear();
      if (mounted) context.go('/success');
    } on ApiException catch (e) {
      if (mounted) {
        context.go(
          '/payment/failed?reason=${Uri.encodeComponent(e.detail)}',
        );
      }
    } catch (_) {
      if (mounted) {
        context.go(
          '/payment/failed?reason=${Uri.encodeComponent('Could not reach the server')}',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              const SizedBox(height: 24),
              Text(
                'Verifying payment…',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                'Hold tight while we confirm your booking.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
