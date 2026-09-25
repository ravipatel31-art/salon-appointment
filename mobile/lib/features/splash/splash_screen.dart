import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../app/brand.dart';

/// Splash: brief brand screen, then into the barber-first flow (`/barbers`).
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(const Duration(milliseconds: 1200), () {
      if (mounted) context.go('/barbers');
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(gradient: Brand.deep),
        child: SafeArea(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Logo mark: gold chip + scissors, soft glow on the wine field.
                Container(
                  width: 104,
                  height: 104,
                  decoration: BoxDecoration(
                    gradient: Brand.goldWine,
                    borderRadius: BorderRadius.circular(30),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.30),
                        blurRadius: 24,
                        offset: const Offset(0, 10),
                      ),
                    ],
                  ),
                  child: const Icon(Icons.content_cut,
                      size: 52, color: Colors.white),
                ),
                const SizedBox(height: 24),
                Text(
                  'Salon',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.5,
                      ),
                ),
                const SizedBox(height: 12),
                Container(
                  width: 56,
                  height: 3,
                  decoration: BoxDecoration(
                    gradient: Brand.goldWine,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
                const SizedBox(height: 14),
                const Text(
                  'Book your chair in seconds',
                  style: TextStyle(color: Colors.white70, letterSpacing: 0.4),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
