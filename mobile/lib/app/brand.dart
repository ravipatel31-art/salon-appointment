import 'package:flutter/material.dart';

import 'theme.dart';

/// Brand palette + reusable gradients for the phase-12 visual polish.
///
/// All visuals here are **offline-safe** (Material icons + gradients); the only
/// network images in the app are barber portraits, which always render through
/// an `errorBuilder` fallback (contract § Imagery).
abstract final class Brand {
  /// Deep wine rose — matches `AppTheme` seed (`#7A2E4A`).
  static const Color wine = Color(0xFF7A2E4A);

  /// Darker wine for gradient depth / splash backgrounds.
  static const Color wineDeep = Color(0xFF54203A);

  /// Soft rose mid-tone used inside gradients.
  static const Color rose = Color(0xFFB15C7E);

  /// Pale blush for gentle fills.
  static const Color blush = Color(0xFFF6E7EE);

  /// Soft gold accent (matches `AppTheme.accent` `#B08D57`).
  static const Color gold = AppTheme.accent;

  /// Light gold for on-dark text and rings.
  static const Color goldSoft = Color(0xFFE7CFA6);

  /// Warm cream page background (matches `AppTheme.background`).
  static const Color cream = AppTheme.background;

  /// Primary brand gradient (wine → rose).
  static const LinearGradient primary = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [wine, Color(0xFF9A4468), rose],
  );

  /// Inverse brand gradient (gold → wine) — logo marks, rings, accents.
  static const LinearGradient goldWine = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFFC9A571), gold, wine],
  );

  /// Warm cream → gold — soft illustration fills.
  static const LinearGradient creamGold = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFFF7E9DA), goldSoft],
  );

  /// Splash / hero background gradient.
  static const LinearGradient deep = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF43172C), wineDeep, wine],
  );

  /// Deterministic accent gradient for a seed (e.g. barber id) so fallback
  /// avatars stay visually distinct without any network round-trip.
  static LinearGradient seed(int seed) {
    const options = [
      primary,
      goldWine,
      LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF8A4B63), Color(0xFFC08A5A)],
      ),
      LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF6B2E4F), Color(0xFFB15C7E)],
      ),
    ];
    return options[seed.abs() % options.length];
  }

  static LinearGradient linear(List<Color> colors) => LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: colors,
      );

  /// Soft tinted fill for chips / icon backgrounds.
  static Color soft(Color tint, {double alpha = 0.12}) =>
      tint.withValues(alpha: alpha);

  /// Subtle wine-tinted card shadow (used sparingly — premium, not heavy).
  static List<BoxShadow> get cardShadow => [
        BoxShadow(
          color: wine.withValues(alpha: 0.10),
          blurRadius: 14,
          offset: const Offset(0, 5),
        ),
      ];

  /// Small `content_cut` logo mark on a gold chip — used on splash/headers.
  static Widget logoMark({double size = 44, double radius = 13, double iconSize = 24}) =>
      Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          gradient: goldWine,
          borderRadius: BorderRadius.circular(radius),
          boxShadow: [
            BoxShadow(
              color: wine.withValues(alpha: 0.25),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Icon(Icons.content_cut, size: iconSize, color: Colors.white),
      );

  /// Up-to-2-letter monogram from a person's name (profile header etc).
  static String initialsOf(String name) {
    final parts =
        name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    final first = parts.first.substring(0, 1).toUpperCase();
    if (parts.length == 1) return first;
    return '$first${parts.last.substring(0, 1).toUpperCase()}';
  }
}
