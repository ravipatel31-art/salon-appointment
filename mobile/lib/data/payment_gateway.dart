import 'dart:async';

import 'package:flutter/material.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';

/// Result of a Razorpay checkout attempt.
sealed class PaymentOutcome {
  const PaymentOutcome();
}

class PaymentSuccess extends PaymentOutcome {
  const PaymentSuccess({
    required this.orderId,
    required this.paymentId,
    required this.signature,
  });

  final String orderId;
  final String paymentId;
  final String signature;
}

class PaymentCancelled extends PaymentOutcome {
  const PaymentCancelled();
}

class PaymentFailure extends PaymentOutcome {
  const PaymentFailure(this.message);

  final String message;
}

/// Opens the payment UI for a Razorpay order created by `POST /bookings`.
///
/// Two interchangeable implementations:
/// * [RazorpayPaymentGateway] — real `razorpay_flutter` checkout.
/// * [MockPaymentGateway] — simulation sheet used while `USE_MOCK_API=true`
///   (and by widget tests).
abstract interface class PaymentGateway {
  Future<PaymentOutcome> pay({
    required BuildContext context,
    required String keyId,
    required String orderId,
    required int amountPaise,
    required String currency,
    String? title,
    String? description,
    String? contact,
    String? email,
  });
}

/// Production gateway: contract `payment` object → Razorpay SDK checkout.
class RazorpayPaymentGateway implements PaymentGateway {
  const RazorpayPaymentGateway();

  @override
  Future<PaymentOutcome> pay({
    required BuildContext context,
    required String keyId,
    required String orderId,
    required int amountPaise,
    required String currency,
    String? title,
    String? description,
    String? contact,
    String? email,
  }) {
    final razorpay = Razorpay();
    final completer = Completer<PaymentOutcome>();

    void complete(PaymentOutcome outcome) {
      if (!completer.isCompleted) completer.complete(outcome);
    }

    razorpay.on(Razorpay.EVENT_PAYMENT_SUCCESS, (response) {
      final r = response as PaymentSuccessResponse;
      final paymentId = r.paymentId;
      final signature = r.signature;
      if (paymentId == null || signature == null) {
        complete(const PaymentFailure('Missing payment verification details'));
        return;
      }
      complete(
        PaymentSuccess(
          orderId: r.orderId ?? orderId,
          paymentId: paymentId,
          signature: signature,
        ),
      );
    });

    razorpay.on(Razorpay.EVENT_PAYMENT_ERROR, (response) {
      final r = response as PaymentFailureResponse;
      if (r.code == Razorpay.PAYMENT_CANCELLED) {
        complete(const PaymentCancelled());
      } else {
        complete(PaymentFailure(r.message ?? 'Payment failed'));
      }
    });

    razorpay.on(Razorpay.EVENT_EXTERNAL_WALLET, (_) {
      complete(const PaymentFailure('External wallet payments are not supported'));
    });

    try {
      razorpay.open({
        'key': keyId,
        'amount': amountPaise, // paise (contract)
        'currency': currency,
        'order_id': orderId,
        if (title != null && title.isNotEmpty) 'name': title,
        if (description != null && description.isNotEmpty)
          'description': description,
        'prefill': {
          if (contact != null && contact.isNotEmpty) 'contact': contact,
          if (email != null && email.isNotEmpty) 'email': email,
        },
        'theme': {'color': '#7A2E4A'},
      });
    } catch (e) {
      complete(PaymentFailure('Could not open checkout: $e'));
    }

    return completer.future.whenComplete(razorpay.clear);
  }
}

/// Simulated checkout for mock mode / tests: success · failure · dismiss.
class MockPaymentGateway implements PaymentGateway {
  const MockPaymentGateway();

  @override
  Future<PaymentOutcome> pay({
    required BuildContext context,
    required String keyId,
    required String orderId,
    required int amountPaise,
    required String currency,
    String? title,
    String? description,
    String? contact,
    String? email,
  }) {
    final completer = Completer<PaymentOutcome>();

    void finish(PaymentOutcome outcome) {
      if (!completer.isCompleted) completer.complete(outcome);
      Navigator.of(context, rootNavigator: true).pop();
    }

    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Simulate Razorpay',
                style: Theme.of(sheetContext).textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 4),
              Text(
                '${(amountPaise / 100).toStringAsFixed(0)} $currency · $orderId',
                textAlign: TextAlign.center,
                style: Theme.of(sheetContext).textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              FilledButton(
                key: const Key('simulate_payment_success'),
                onPressed: () => finish(
                  PaymentSuccess(
                    orderId: orderId,
                    paymentId: 'pay_MOCK${orderId.hashCode.toUnsigned(32)}',
                    signature: 'sig_MOCK${orderId.hashCode.toUnsigned(32)}',
                  ),
                ),
                child: const Text('Simulate payment success'),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                key: const Key('simulate_payment_failure'),
                onPressed: () =>
                    finish(const PaymentFailure('Simulated payment error')),
                child: const Text('Simulate payment failure'),
              ),
              const SizedBox(height: 8),
              TextButton(
                key: const Key('simulate_payment_dismiss'),
                onPressed: () => finish(const PaymentCancelled()),
                child: const Text('Dismiss (user cancelled)'),
              ),
            ],
          ),
        ),
      ),
    ).then((_) {
      // Sheet closed by back gesture → treat as cancellation.
      if (!completer.isCompleted) completer.complete(const PaymentCancelled());
    });

    return completer.future;
  }
}
