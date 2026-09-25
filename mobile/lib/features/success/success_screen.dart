import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/brand.dart';
import '../../core/utils/format.dart';
import '../booking/booking_state.dart';

/// Post-verification confirmation — shows the contract booking details.
///
/// Phase 12 polish: celebration mark (brand gradient + icon) instead of a
/// flat check circle.
class SuccessScreen extends ConsumerWidget {
  const SuccessScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final booking = ref.watch(lastConfirmedProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Confirmed')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Celebration mark: wine gradient disc + gold ring + icon.
                Center(
                  child: Container(
                    width: 132,
                    height: 132,
                    decoration: BoxDecoration(
                      gradient: Brand.primary,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Brand.wine.withValues(alpha: 0.35),
                          blurRadius: 26,
                          offset: const Offset(0, 10),
                        ),
                      ],
                    ),
                    child: Center(
                      child: Container(
                        width: 108,
                        height: 108,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: Brand.goldSoft.withValues(alpha: 0.9),
                            width: 2,
                          ),
                        ),
                        child: const Icon(
                          Icons.celebration,
                          size: 54,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 22),
                Text(
                  'Booking confirmed!',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                Text(
                  booking == null
                      ? 'Your slot is held. Show your booking ref at the center.'
                      : '${booking.bookingRef} · ${booking.serviceName ?? ''}'
                          '${booking.barberName == null ? '' : ' with ${booking.barberName}'}',
                  textAlign: TextAlign.center,
                ),
                if (booking != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    AppFormat.dateTimeInKolkata(booking.startAt),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Paid online ${AppFormat.rupees(booking.onlineAmountPaid)} · '
                    'Balance ${AppFormat.rupees(booking.balanceAmount)} in-shop',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 32),
                FilledButton(
                  key: const Key('view_bookings'),
                  onPressed: () => context.go('/bookings'),
                  child: const Text('View my bookings'),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => context.go('/barbers'),
                  child: const Text('Book another'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
