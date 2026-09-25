import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/brand.dart';
import '../../core/utils/format.dart';
import '../../core/utils/pricing.dart';
import '../../core/widgets/service_art.dart';
import '../../data/models/service_model.dart';
import '../../data/providers.dart';

/// Secondary tab — service catalog from `GET /services` with duration / ₹
/// pricing and client-owned illustration art (icon + brand gradient per
/// service — contract § Imagery: no `image_url` in the API).
///
/// Primary flow is barber-first; picking a service here switches to the
/// barbers tab with `?service_id=` preselected on each barber's selection
/// page.
class ServicesScreen extends ConsumerWidget {
  const ServicesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final services = ref.watch(servicesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Services')),
      body: services.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => _ErrorView(
          message: error.toString(),
          onRetry: () => ref.invalidate(servicesProvider),
        ),
        data: (items) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(servicesProvider),
          child: ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.all(16),
            itemCount: items.length + 1,
            itemBuilder: (context, index) {
              if (index == 0) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    'Pick a service, then choose your barber and slot.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                );
              }
              final service = items[index - 1];
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _ServiceCard(
                  service: service,
                  // Barber list is shell tab 0 — switch tabs with the
                  // preselect instead of pushing a duplicate stack entry.
                  onTap: () => context.go('/barbers?service_id=${service.id}'),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ServiceCard extends StatelessWidget {
  const _ServiceCard({required this.service, required this.onTap});

  final ServiceItem service;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colorService = service.isHairColor;
    final art = ServiceArt.forService(service);
    return Card(
      elevation: 1.5,
      shadowColor: Brand.wine.withValues(alpha: 0.12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Image-like illustration strip (offline-safe icon + gradient).
            ServiceArtBanner(art: art),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          service.name,
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: Brand.soft(scheme.primary, alpha: 0.08),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          colorService
                              ? '${AppFormat.rupees(service.price)} advance'
                              : AppFormat.rupees(service.price),
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: scheme.primary,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (service.description.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      service.description,
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(color: const Color(0xFF6B6360)),
                    ),
                  ],
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Icon(Icons.schedule,
                          size: 16, color: art.tint),
                      const SizedBox(width: 4),
                      Text(AppFormat.duration(service.durationMinutes)),
                      const SizedBox(width: 12),
                      const Icon(Icons.water_drop_outlined, size: 16),
                      const SizedBox(width: 4),
                      Text(
                        'Wash +${AppFormat.rupees(Pricing.washAddonPrice)} · '
                        '+${Pricing.washAddonMinutes}m',
                      ),
                    ],
                  ),
                  if (colorService) ...[
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Icon(Icons.info_outline,
                            size: 15, color: scheme.primary),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            '${AppFormat.rupees(Pricing.hairColorAdvance)} '
                            'advance online — actual price at center',
                            style: TextStyle(
                              color: scheme.primary,
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
