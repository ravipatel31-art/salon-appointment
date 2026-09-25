import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/availability/availability_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/barbers/barber_detail_screen.dart';
import '../features/barbers/barbers_screen.dart';
import '../features/bookings/bookings_screen.dart';
import '../features/checkout/checkout_screen.dart';
import '../features/checkout/payment_failed_screen.dart';
import '../features/checkout/processing_screen.dart';
import '../features/home/home_shell.dart';
import '../features/profile/profile_screen.dart';
import '../features/services/services_screen.dart';
import '../features/splash/splash_screen.dart';
import '../features/success/success_screen.dart';

/// App-level routing (go_router). Barber-first primary flow (contract
/// 2026-09-24): splash → `/barbers` (shell tab) → barber detail selection
/// page → checkout. Shell tabs: Barbers · Services · Bookings · Profile —
/// `/services` stays as a secondary entry (with `?service_id=` preselect).
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    errorBuilder: (context, state) => _NotFoundScreen(location: state.uri.toString()),
    routes: [
      GoRoute(path: '/', builder: (context, state) => const SplashScreen()),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/register', builder: (context, state) => const RegisterScreen()),
      // Barber detail = selection page (service + wash + date + slot) and the
      // standalone availability route — pushed full-screen on top of the shell.
      GoRoute(
        path: '/barbers/:id',
        builder: (context, state) => BarberDetailScreen(
          barberId: int.tryParse(state.pathParameters['id'] ?? '') ?? 0,
          initialServiceId:
              int.tryParse(state.uri.queryParameters['service_id'] ?? ''),
          initialAddons: _splitAddons(state.uri.queryParameters['addons']),
        ),
        routes: [
          GoRoute(
            path: 'availability',
            builder: (context, state) {
              return AvailabilityScreen(
                barberId: int.tryParse(state.pathParameters['id'] ?? '') ?? 0,
                serviceId: int.tryParse(state.uri.queryParameters['service_id'] ?? ''),
                addons: _splitAddons(state.uri.queryParameters['addons']),
              );
            },
          ),
        ],
      ),
      GoRoute(path: '/checkout', builder: (context, state) => const CheckoutScreen()),
      GoRoute(path: '/payment/processing', builder: (context, state) => const ProcessingScreen()),
      GoRoute(
        path: '/payment/failed',
        builder: (context, state) => PaymentFailedScreen(
          reason: state.uri.queryParameters['reason'],
        ),
      ),
      GoRoute(path: '/success', builder: (context, state) => const SuccessScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            HomeShell(navigationShell: navigationShell),
        branches: [
          // Tab 0 — barber list: default landing after splash.
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/barbers',
              builder: (context, state) => BarbersScreen(
                serviceId: int.tryParse(state.uri.queryParameters['service_id'] ?? ''),
              ),
            ),
          ]),
          // Tab 1 — secondary service catalog entry.
          StatefulShellBranch(routes: [
            GoRoute(path: '/services', builder: (context, state) => const ServicesScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/bookings', builder: (context, state) => const BookingsScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/profile', builder: (context, state) => const ProfileScreen()),
          ]),
        ],
      ),
    ],
  );
});

class _NotFoundScreen extends StatelessWidget {
  const _NotFoundScreen({required this.location});

  final String location;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Not found')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text('No route for $location'),
        ),
      ),
    );
  }
}

List<String> _splitAddons(String? raw) => (raw ?? '')
    .split(',')
    .map((a) => a.trim())
    .where((a) => a.isNotEmpty)
    .toList();
