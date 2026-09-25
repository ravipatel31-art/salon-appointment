import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/brand.dart';
import '../../core/network/api_exception.dart';
import '../../core/utils/format.dart';
import '../../data/models/booking_model.dart';
import '../../data/providers.dart';

/// Upcoming / past bookings (`GET /bookings`) + cancel
/// (`POST /bookings/{id}/cancel`, ≥2h policy).
class BookingsScreen extends ConsumerStatefulWidget {
  const BookingsScreen({super.key});

  @override
  ConsumerState<BookingsScreen> createState() => _BookingsScreenState();
}

class _BookingsScreenState extends ConsumerState<BookingsScreen> {
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// Ticks once a second only while a `pending_payment` hold needs a
  /// countdown — stays settle-friendly otherwise.
  void _syncTimer(bool needsTick) {
    if (needsTick && (_timer == null || !_timer!.isActive)) {
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        setState(() {});
      });
    } else if (!needsTick && (_timer?.isActive ?? false)) {
      _timer!.cancel();
      _timer = null;
    }
  }

  Future<void> _cancel(Booking booking) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Cancel booking?'),
        content: Text(
          'Cancel ${booking.serviceName ?? 'appointment'} on '
          '${AppFormat.dateTimeInKolkata(booking.startAt)}? '
          'Cancelling at least 2 hours ahead refunds the advance.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep it'),
          ),
          FilledButton(
            key: const Key('confirm_cancel'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Cancel booking'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      await ref
          .read(bookingRepositoryProvider)
          .cancelBooking(booking.id);
      ref.invalidate(myBookingsProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Booking cancelled')),
        );
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Cancel failed: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final bookingsAsync = ref.watch(myBookingsProvider);
    final now = DateTime.now().toUtc();

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('My bookings'),
          bottom: const TabBar(
            tabs: [Tab(text: 'Upcoming'), Tab(text: 'Past')],
          ),
        ),
        body: bookingsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => _ErrorView(
            message: '$error',
            onRetry: () => ref.invalidate(myBookingsProvider),
          ),
          data: (all) {
            final upcoming = all
                .where((b) =>
                    BookingStatus.isUpcomingOpen(b.status) &&
                    b.startAt.isAfter(now))
                .toList()
              ..sort((a, b) => a.startAt.compareTo(b.startAt));
            final past = all
                .where((b) =>
                    !BookingStatus.isUpcomingOpen(b.status) ||
                    !b.startAt.isAfter(now))
                .toList()
              ..sort((a, b) => b.startAt.compareTo(a.startAt));

            _syncTimer(
              upcoming.any((b) => b.status == BookingStatus.pendingPayment),
            );

            return TabBarView(
              children: [
                _BookingList(
                  key: const Key('upcoming_list'),
                  bookings: upcoming,
                  emptyMessage:
                      'No upcoming bookings. Pick a service to get started.',
                  iconForEmpty: Icons.event_available_outlined,
                  now: now,
                  onCancel: _cancel,
                  onRefresh: () async =>
                      ref.invalidate(myBookingsProvider),
                ),
                _BookingList(
                  key: const Key('past_list'),
                  bookings: past,
                  emptyMessage: 'Past bookings will appear here.',
                  iconForEmpty: Icons.history_outlined,
                  now: now,
                  onCancel: _cancel,
                  onRefresh: () async =>
                      ref.invalidate(myBookingsProvider),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _BookingList extends StatelessWidget {
  const _BookingList({
    super.key,
    required this.bookings,
    required this.emptyMessage,
    required this.now,
    required this.onCancel,
    required this.onRefresh,
    this.iconForEmpty = Icons.event_busy_outlined,
  });

  final List<Booking> bookings;
  final String emptyMessage;
  final DateTime now;
  final ValueChanged<Booking> onCancel;
  final Future<void> Function() onRefresh;
  final IconData iconForEmpty;

  @override
  Widget build(BuildContext context) {
    if (bookings.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Empty-state illustration: brand gradient medallion + icon.
              Container(
                width: 116,
                height: 116,
                decoration: BoxDecoration(
                  gradient: Brand.creamGold,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Brand.gold.withValues(alpha: 0.45),
                  ),
                  boxShadow: Brand.cardShadow,
                ),
                child: Icon(
                  iconForEmpty,
                  size: 52,
                  color: Brand.wine,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                emptyMessage,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(
                'Times shown in IST (Asia/Kolkata).',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        itemCount: bookings.length,
        itemBuilder: (context, index) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _BookingCard(
            booking: bookings[index],
            now: now,
            onCancel: () => onCancel(bookings[index]),
          ),
        ),
      ),
    );
  }
}

class _BookingCard extends StatelessWidget {
  const _BookingCard({
    required this.booking,
    required this.now,
    required this.onCancel,
  });

  final Booking booking;
  final DateTime now;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final status = booking.status;
    final isOpenPending = status == BookingStatus.pendingPayment;
    final isOpen = BookingStatus.isUpcomingOpen(status);
    final future = booking.startAt.isAfter(now);
    final canCancel =
        isOpen && booking.startAt.difference(now) >= const Duration(hours: 2);
    final colorService = (booking.balanceDue == null) &&
        (booking.finalPriceAtCenter == null) &&
        booking.serviceName?.toLowerCase().contains('color') == true;

    final (statusLabel, statusColor) = switch (status) {
      BookingStatus.pendingPayment => ('Pending payment', scheme.tertiary),
      BookingStatus.confirmed => ('Confirmed', scheme.primary),
      BookingStatus.completed => ('Completed', scheme.outline),
      BookingStatus.cancelled => ('Cancelled', scheme.error),
      BookingStatus.refunded => ('Refunded', scheme.secondary),
      BookingStatus.noShow => ('No show', scheme.error),
      _ => (BookingStatus.label(status), scheme.outline),
    };

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    booking.serviceName ?? 'Service #${booking.serviceId}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    statusLabel,
                    style: TextStyle(
                      color: statusColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '${booking.barberName ?? 'Barber #${booking.barberId}'} · '
              '${AppFormat.dateTimeInKolkata(booking.startAt)} · '
              '${AppFormat.duration(booking.durationMinutes)}',
            ),
            const SizedBox(height: 6),
            Text(
              'Ref ${booking.bookingRef} · '
              'Paid online ${AppFormat.rupees(booking.onlineAmountPaid)} · '
              'Balance ${AppFormat.rupees(booking.balanceAmount)} in-shop',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (colorService) ...[
              const SizedBox(height: 4),
              Text(
                '₹100 advance online — actual price at center',
                style: TextStyle(
                  color: scheme.primary,
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
            ],
            if (isOpenPending && !booking.holdExpired) ...[
              const SizedBox(height: 6),
              Text(
                'Hold expires in '
                '${AppFormat.countdown(booking.holdRemaining())}',
                style: TextStyle(
                  color: scheme.tertiary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
            if (isOpen && future) ...[
              const SizedBox(height: 8),
              if (canCancel)
                Align(
                  alignment: Alignment.centerRight,
                  child: OutlinedButton(
                    key: ValueKey('cancel_${booking.id}'),
                    onPressed: onCancel,
                    child: const Text('Cancel'),
                  ),
                )
              else
                Align(
                  alignment: Alignment.centerRight,
                  child: Text(
                    'Cancel available until 2 hours before',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
            ],
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
            const Icon(Icons.cloud_off_outlined, size: 56),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.tonal(
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

