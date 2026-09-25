import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_exception.dart';
import '../../core/utils/format.dart';
import '../../data/providers.dart';
import '../booking/booking_state.dart';

/// Payment did not complete (dismiss / error / verify failure).
/// Offers the contract-aligned retry and cancel paths.
class PaymentFailedScreen extends ConsumerStatefulWidget {
  const PaymentFailedScreen({super.key, this.reason});

  /// Optional `?reason=` detail (verify error detail or gateway message).
  final String? reason;

  @override
  ConsumerState<PaymentFailedScreen> createState() =>
      _PaymentFailedScreenState();
}

class _PaymentFailedScreenState extends ConsumerState<PaymentFailedScreen> {
  bool _busy = false;

  String get _message {
    final reason = widget.reason;
    if (reason == null || reason.isEmpty) {
      return 'Payment was cancelled. Your slot hold is still active while '
          'the 12-minute timer runs.';
    }
    return reason;
  }

  Future<void> _retry() async {
    final pending = ref.read(pendingPaymentProvider);
    if (pending == null) {
      context.go('/barbers');
      return;
    }
    // Checkout resumes the same hold/order unless it expired.
    context.go('/checkout');
  }

  Future<void> _cancelBooking() async {
    final pending = ref.read(pendingPaymentProvider);
    if (pending == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Cancel booking?'),
        content: Text(
          'Release ${pending.booking.bookingRef} '
          '(${pending.booking.serviceName ?? 'appointment'} on '
          '${AppFormat.dateTimeInKolkata(pending.booking.startAt)})?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep it'),
          ),
          FilledButton(
            key: const Key('confirm_cancel_booking'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Cancel booking'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busy = true);
    try {
      await ref
          .read(bookingRepositoryProvider)
          .cancelBooking(pending.booking.id);
      ref.read(pendingPaymentProvider.notifier).clear();
      ref.read(bookingDraftProvider.notifier).clear();
      if (mounted) context.go('/bookings');
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
      setState(() => _busy = false);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Cancel failed: $e')));
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pending = ref.watch(pendingPaymentProvider);
    final expired = pending?.holdExpired ?? false;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Payment not completed')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 116,
                height: 116,
                decoration: BoxDecoration(
                  color: scheme.error.withValues(alpha: 0.10),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: scheme.error.withValues(alpha: 0.35),
                  ),
                ),
                child: Icon(
                  Icons.error_outline,
                  size: 56,
                  color: scheme.error,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Payment not completed',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Text(_message, textAlign: TextAlign.center),
            if (pending != null) ...[
              const SizedBox(height: 12),
              Text(
                expired
                    ? 'Hold expired — retrying creates a fresh hold.'
                    : 'Hold expires in '
                        '${AppFormat.countdown(pending.booking.holdRemaining())}'
                        ' · ${pending.payment.razorpayOrderId}',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 32),
            if (pending != null)
              FilledButton(
                key: const Key('retry_payment'),
                onPressed: _busy ? null : _retry,
                child: const Text('Retry payment'),
              ),
            if (pending != null) ...[
              const SizedBox(height: 8),
              OutlinedButton(
                key: const Key('cancel_booking'),
                onPressed: _busy ? null : _cancelBooking,
                child: _busy
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Cancel booking'),
              ),
            ],
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => context.go('/barbers'),
              child: const Text('Back to barbers'),
            ),
          ],
        ),
      ),
    );
  }
}
