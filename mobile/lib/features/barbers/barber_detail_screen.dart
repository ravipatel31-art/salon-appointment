import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/brand.dart';
import '../../core/widgets/barber_photo.dart';
import '../../data/providers.dart';
import '../../features/booking/booking_state.dart';
import 'widgets/booking_picker.dart';

/// Barber profile + **selection page**: service + wash add-on + date + slot
/// (the primary booking flow step after choosing a barber).
///
/// Phase 12 polish: large hero portrait header (network `photo_url` with a
/// gradient+initials `errorBuilder` fallback) above the booking picker.
class BarberDetailScreen extends ConsumerWidget {
  const BarberDetailScreen({
    super.key,
    required this.barberId,
    this.initialServiceId,
    this.initialAddons = const [],
  });

  final int barberId;
  final int? initialServiceId;
  final List<String> initialAddons;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final barberAsync = ref.watch(barberProvider(barberId));
    return Scaffold(
      appBar: AppBar(
        title: barberAsync.maybeWhen(
          data: (b) => Text(b.name),
          orElse: () => Text('Barber #$barberId'),
        ),
      ),
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
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            BarberHeroImage(
              barber: barber,
              height: 216,
              hero: true,
              overlay: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      barber.name,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    if (barber.specialties.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          for (final s in barber.specialties)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 4,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.18),
                                borderRadius: BorderRadius.circular(999),
                                border: Border.all(
                                  color: Brand.goldSoft.withValues(alpha: 0.7),
                                ),
                              ),
                              child: Text(
                                s,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
            if (barber.bio.isNotEmpty) ...[
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.auto_awesome, size: 18, color: Brand.gold),
                      const SizedBox(width: 10),
                      Expanded(child: Text(barber.bio)),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Brand.logoMark(size: 34, radius: 10, iconSize: 17),
                        const SizedBox(width: 10),
                        Text(
                          'Select service, date & time',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    BookingPicker(
                      barber: barber,
                      initialServiceId: initialServiceId,
                      initialAddons: initialAddons,
                      onContinue: (service, addons, startAt) {
                        ref.read(bookingDraftProvider.notifier).select(
                              service: service,
                              addons: addons,
                              barber: barber,
                              startAt: startAt,
                            );
                        context.push('/checkout');
                      },
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
