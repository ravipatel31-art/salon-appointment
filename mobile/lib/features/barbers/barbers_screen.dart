import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/brand.dart';
import '../../core/widgets/barber_photo.dart';
import '../../data/models/barber_model.dart';
import '../../data/providers.dart';

/// `GET /barbers` — 5 seeded barbers; optional `service_id` carries the
/// chosen service into the barber detail booking flow.
///
/// Phase 12 polish: branded header + hero-quality portrait cards with the
/// offline-safe [BarberAvatar] (network `photo_url` → `errorBuilder` →
/// gradient + initials).
class BarbersScreen extends ConsumerWidget {
  const BarbersScreen({super.key, this.serviceId});

  final int? serviceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final barbers = ref.watch(barbersProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Barbers')),
      body: barbers.when(
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
                  onPressed: () => ref.invalidate(barbersProvider),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
        data: (items) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(barbersProvider),
          child: ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            // Index 0 renders the branded intro header above the cards.
            itemCount: items.length + 1,
            itemBuilder: (context, index) {
              if (index == 0) return const _BarbersHeader();
              final barber = items[index - 1];
              final suffix = serviceId != null ? '?service_id=$serviceId' : '';
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _BarberCard(
                  barber: barber,
                  onTap: () => context.push('/barbers/${barber.id}$suffix'),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// Gradient intro strip above the barber list (brand tagline).
class _BarbersHeader extends StatelessWidget {
  const _BarbersHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 4, bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: Brand.primary,
        borderRadius: BorderRadius.circular(18),
        boxShadow: Brand.cardShadow,
      ),
      child: Row(
        children: [
          Brand.logoMark(size: 46, radius: 14, iconSize: 24),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Master barbers, one tap away',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Pick your stylist, choose a slot, pay just the advance '
                  'online.',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: Colors.white70),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BarberCard extends StatelessWidget {
  const _BarberCard({required this.barber, required this.onTap});

  final Barber barber;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final subtitle = barber.bio.isNotEmpty
        ? barber.bio
        : (barber.specialties.isEmpty
            ? 'Available for booking'
            : barber.specialties.join(' · '));

    return Card(
      elevation: 1.5,
      shadowColor: Brand.wine.withValues(alpha: 0.14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              BarberAvatar(barber: barber, radius: 34, hero: true),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      barber.name,
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    if (barber.specialties.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          for (final s in barber.specialties)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: Brand.soft(scheme.primary, alpha: 0.08),
                                borderRadius: BorderRadius.circular(999),
                                border: Border.all(
                                  color:
                                      scheme.primary.withValues(alpha: 0.18),
                                ),
                              ),
                              child: Text(
                                s,
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: scheme.primary,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                    const SizedBox(height: 6),
                    Text(
                      subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: const Color(0xFF6B6360)),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: Brand.soft(Brand.gold, alpha: 0.18),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.chevron_right, size: 22, color: Brand.wine),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
