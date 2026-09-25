import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/widgets/barber_photo.dart';
import '../../data/providers.dart';
import '../../features/booking/booking_state.dart';
import '../barbers/widgets/booking_picker.dart';

/// Standalone availability route: `GET /barbers/{id}/availability` with date
/// + slot chips for a pre-selected service/add-ons.
class AvailabilityScreen extends ConsumerWidget {
  const AvailabilityScreen({
    super.key,
    required this.barberId,
    this.serviceId,
    this.addons = const [],
  });

  final int barberId;
  final int? serviceId;
  final List<String> addons;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final barberAsync = ref.watch(barberProvider(barberId));
    return Scaffold(
      appBar: AppBar(title: const Text('Availability')),
      body: barberAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('$error', textAlign: TextAlign.center),
                const SizedBox(height: 12),
                FilledButton.tonal(
                  onPressed: () => ref.invalidate(barberProvider(barberId)),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
        data: (barber) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: ListTile(
                leading: BarberAvatar(barber: barber, radius: 24),
                title: Text(barber.name),
                subtitle: const Text('Pick a date and 15-minute slot'),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: BookingPicker(
                  barber: barber,
                  initialServiceId: serviceId,
                  initialAddons: addons,
                  onContinue: (service, selectedAddons, startAt) {
                    ref.read(bookingDraftProvider.notifier).select(
                          service: service,
                          addons: selectedAddons,
                          barber: barber,
                          startAt: startAt,
                        );
                    context.push('/checkout');
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
