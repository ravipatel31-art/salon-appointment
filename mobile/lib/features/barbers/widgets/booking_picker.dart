import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/format.dart';
import '../../../core/utils/pricing.dart';
import '../../../core/widgets/service_art.dart';
import '../../../data/models/barber_model.dart';
import '../../../data/models/service_model.dart';
import '../../../data/providers.dart';

/// Date (next 14 days) + slot chips + wash add-on toggle with live pricing.
///
/// Shared by barber detail (full booking) and the standalone availability
/// route. The availability family is `autoDispose`, so every screen open
/// refetches `GET /barbers/{id}/availability` from the API.
class BookingPicker extends ConsumerStatefulWidget {
  const BookingPicker({
    super.key,
    required this.barber,
    this.initialServiceId,
    this.initialAddons = const [],
    this.showServiceSelector = true,
    this.onContinue,
    this.continueLabel = 'Continue to checkout',
  });

  final Barber barber;
  final int? initialServiceId;
  final List<String> initialAddons;
  final bool showServiceSelector;

  /// Called when a slot is chosen and the user proceeds; the parent sets the
  /// booking draft and navigates to `/checkout`.
  final void Function(ServiceItem service, List<String> addons, DateTime startAt)?
      onContinue;
  final String continueLabel;

  @override
  ConsumerState<BookingPicker> createState() => _BookingPickerState();
}

class _BookingPickerState extends ConsumerState<BookingPicker> {
  int? _serviceId;
  bool _wash = false;
  int _dayIndex = 0;
  DateTime? _selectedStart;

  @override
  void initState() {
    super.initState();
    _wash = widget.initialAddons.any((a) => a.toLowerCase() == 'wash');
    _serviceId = widget.initialServiceId;
  }

  List<String> get _addons => _wash ? const ['wash'] : const [];

  ServiceItem? _resolveService(List<ServiceItem> items) {
    if (items.isEmpty) return null;
    final wanted = _serviceId ?? widget.initialServiceId;
    if (wanted != null) {
      for (final s in items) {
        if (s.id == wanted) return s;
      }
    }
    return items.first;
  }

  AvailabilityQuery? _queryFor(int? serviceId) {
    if (serviceId == null) return null;
    return AvailabilityQuery(
      barberId: widget.barber.id,
      date: AppFormat.isoDateFromIstDay(AppFormat.istDay(_dayIndex)),
      serviceId: serviceId,
      addons: _addons,
    );
  }

  @override
  Widget build(BuildContext context) {
    final servicesAsync = ref.watch(servicesProvider);
    final scheme = Theme.of(context).colorScheme;

    return servicesAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(24),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(16),
        child: Text('Could not load services: $e'),
      ),
      data: (services) {
        final service = _resolveService(services);
        if (service == null) {
          return const Padding(
            padding: EdgeInsets.all(16),
            child: Text('No services available yet.'),
          );
        }
        final wash = _wash;
        final duration = Pricing.durationMinutes(service, wash: wash);
        final total = Pricing.onlineTotal(service, wash: wash);
        final advance = Pricing.advance(service, wash: wash);
        final balance = Pricing.balance(service, wash: wash);
        final query = _queryFor(service.id);
        final selected = _selectedStart;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ------------------------------------------------ service picker
            if (widget.showServiceSelector && services.isNotEmpty) ...[
              Text('Service', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              SizedBox(
                height: 40,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: services.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (context, i) {
                    final s = services[i];
                    final art = ServiceArt.forService(s);
                    return ChoiceChip(
                      key: ValueKey('service_chip_${s.id}'),
                      // Client-owned service art (contract § Imagery): a small
                      // tinted icon chip leads each service chip.
                      avatar: CircleAvatar(
                        radius: 11,
                        backgroundColor: art.softTint,
                        child: Icon(art.icon, size: 13, color: art.tint),
                      ),
                      label: Text(s.name),
                      selected: s.id == service.id,
                      onSelected: (_) {
                        setState(() {
                          _serviceId = s.id;
                          _selectedStart = null;
                        });
                      },
                    );
                  },
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.schedule, size: 16),
                  const SizedBox(width: 4),
                  Text(AppFormat.duration(duration)),
                  const SizedBox(width: 16),
                  const Icon(Icons.currency_rupee, size: 16),
                  const SizedBox(width: 2),
                  Text(
                    total == null
                        ? '${AppFormat.rupees(advance)} advance'
                        : AppFormat.rupees(total),
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ],
              ),
              if (service.isHairColor) ...[
                const SizedBox(height: 6),
                Text(
                  '${AppFormat.rupees(Pricing.hairColorAdvance)} advance online '
                  '— actual price at center',
                  style: TextStyle(
                    color: scheme.primary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              const SizedBox(height: 4),
              SwitchListTile(
                key: const Key('wash_toggle'),
                contentPadding: EdgeInsets.zero,
                secondary: Icon(
                  ServiceArt.wash.icon,
                  color: ServiceArt.wash.tint,
                ),
                title: const Text('Add wash'),
                subtitle: Text(
                  '+${AppFormat.rupees(Pricing.washAddonPrice)} · '
                  '+${Pricing.washAddonMinutes} min',
                ),
                value: wash,
                onChanged: (v) => setState(() {
                  _wash = v;
                  _selectedStart = null;
                }),
              ),
            ],

            // -------------------------------------------------- date picker
            Text('Date', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SizedBox(
              height: 44,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: 14,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, i) {
                  final day = AppFormat.istDay(i);
                  final label = AppFormat.isToday(day)
                      ? 'Today'
                      : AppFormat.dayChipLabel(day);
                  return ChoiceChip(
                    key: ValueKey('date_chip_$i'),
                    label: Text(label),
                    selected: i == _dayIndex,
                    onSelected: (_) => setState(() {
                      _dayIndex = i;
                      _selectedStart = null;
                    }),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),

            // -------------------------------------------------- slot chips
            Text('Time', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (query == null)
              const Text('Select a service to see slots.')
            else
              _SlotGrid(
                query: query,
                selected: selected,
                onSelect: (start) => setState(() => _selectedStart = start),
              ),
            const SizedBox(height: 16),

            // ----------------------------------------------- live summary
            if (service.isHairColor)
              Text(
                'Advance online: '
                '${AppFormat.rupees(Pricing.advance(service, wash: wash))} · '
                'Duration: ${AppFormat.duration(duration)}',
                style: Theme.of(context).textTheme.bodySmall,
              )
            else ...[
              _SummaryRow(label: 'Total', value: AppFormat.rupees(total!)),
              _SummaryRow(
                label: 'Advance online now',
                value: AppFormat.rupees(advance),
                emphasized: true,
              ),
              _SummaryRow(
                label: 'Balance in-shop',
                value: AppFormat.rupees(balance!),
              ),
            ],

            if (widget.onContinue != null) ...[
              const SizedBox(height: 16),
              FilledButton.icon(
                key: const Key('continue_to_checkout'),
                onPressed: selected == null
                    ? null
                    : () =>
                        widget.onContinue!(service, _addons, selected),
                icon: const Icon(Icons.arrow_forward),
                label: Text(widget.continueLabel),
              ),
            ],
          ],
        );
      },
    );
  }
}

/// Fetches `GET /barbers/{id}/availability` for the current query and renders
/// 15-minute slot chips (Asia/Kolkata labels).
class _SlotGrid extends ConsumerWidget {
  const _SlotGrid({
    required this.query,
    required this.selected,
    required this.onSelect,
  });

  final AvailabilityQuery query;
  final DateTime? selected;
  final ValueChanged<DateTime> onSelect;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final availability = ref.watch(availabilityProvider(query));
    return availability.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 20),
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      ),
      error: (error, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$error', style: Theme.of(context).textTheme.bodySmall),
          TextButton(
            onPressed: () => ref.invalidate(availabilityProvider(query)),
            child: const Text('Retry'),
          ),
        ],
      ),
      data: (data) {
        if (data.slots.isEmpty) {
          return const Text('No working hours for this day.');
        }
        if (data.slots.every((s) => !s.available)) {
          return const Text('Fully booked — try another day.');
        }
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final slot in data.slots)
              ChoiceChip(
                key: ValueKey('slot_${slot.startAt.toIso8601String()}'),
                label: Text(AppFormat.timeInKolkata(slot.startAt)),
                selected: selected?.isAtSameMomentAs(slot.startAt) ?? false,
                onSelected:
                    slot.available ? (_) => onSelect(slot.startAt) : null,
              ),
          ],
        );
      },
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({
    required this.label,
    required this.value,
    this.emphasized = false,
  });

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final style = emphasized
        ? TextStyle(
            fontWeight: FontWeight.w700,
            color: Theme.of(context).colorScheme.primary,
          )
        : const TextStyle(fontWeight: FontWeight.w600);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(value, style: style),
        ],
      ),
    );
  }
}
