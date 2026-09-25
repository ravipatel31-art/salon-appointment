import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/brand.dart';
import '../auth/auth_controller.dart';

/// Profile tab — session from `GET /auth/me`, logout, auth entry points.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final user = auth.user;

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Center(
            child: Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                gradient: user == null ? Brand.goldWine : Brand.seed(user.id),
                shape: BoxShape.circle,
                boxShadow: Brand.cardShadow,
              ),
              child: user == null
                  ? const Icon(Icons.person_outline, size: 42, color: Colors.white)
                  : Center(
                      child: Text(
                        Brand.initialsOf(user.name),
                        style: const TextStyle(
                          fontSize: 30,
                          fontWeight: FontWeight.w800,
                          color: Colors.white,
                        ),
                      ),
                    ),
            ),
          ),
          const SizedBox(height: 14),
          if (user == null)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Not signed in',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'Log in to manage your account. '
                      'You can also book as a guest at checkout.',
                    ),
                  ],
                ),
              ),
            )
          else
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user.name,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 8),
                    if (user.phone.isNotEmpty)
                      Text('Phone: ${user.phone}'),
                    if (user.email.isNotEmpty)
                      Text('Email: ${user.email}'),
                    Text('Role: ${user.role}'),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 16),
          if (user == null) ...[
            FilledButton.tonal(
              onPressed: () => context.push('/login'),
              child: const Text('Log in'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => context.push('/register'),
              child: const Text('Create account'),
            ),
          ] else ...[
            OutlinedButton(
              key: const Key('logout_button'),
              onPressed: () {
                ref.read(authControllerProvider.notifier).logout();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Logged out')),
                );
              },
              child: const Text('Log out'),
            ),
          ],
          const SizedBox(height: 24),
          Text(
            'Asia/Kolkata · prices in ₹ · 15-minute slots',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
