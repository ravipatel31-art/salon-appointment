import 'package:flutter/material.dart';

import '../../app/brand.dart';
import '../../data/models/barber_model.dart';

/// Shared hero tag for a barber's portrait (list avatar ↔ detail header).
String barberPhotoHeroTag(int barberId) => 'barber_photo_$barberId';

/// Circular barber portrait with an offline-safe fallback: the network photo
/// (`photo_url`) renders through `Image.network` + `errorBuilder` → brand
/// gradient circle + initials, exactly as required by the contract's
/// **Imagery** section. A `null`/empty `photo_url` skips the network entirely.
class BarberAvatar extends StatelessWidget {
  const BarberAvatar({
    super.key,
    required this.barber,
    this.radius = 28,
    this.hero = false,
  });

  final Barber barber;

  /// Circle radius (diameter = `radius * 2`).
  final double radius;

  /// Wraps the avatar in a [Hero] shared with [BarberHeroImage].
  final bool hero;

  @override
  Widget build(BuildContext context) {
    final size = radius * 2;
    final fallback = _FallbackPortrait(
      barber: barber,
      width: size,
      height: size,
      fontSize: radius * 0.66,
      showWatermark: false,
    );

    final Widget content;
    final url = _photoUrl(barber);
    if (url == null) {
      content = fallback;
    } else {
      content = Image.network(
        url,
        fit: BoxFit.cover,
        width: size,
        height: size,
        // Contract Imagery: every remote image degrades to gradient +
        // initials so the UI stays attractive offline / on HTTP failures.
        errorBuilder: (_, __, ___) => fallback,
      );
    }

    final Widget child = ClipOval(
      child: SizedBox(width: size, height: size, child: content),
    );

    if (!hero) return child;
    return Hero(tag: barberPhotoHeroTag(barber.id), child: child);
  }
}

/// Wide portrait header for the barber detail (selection page) — large image
/// with an optional gradient scrim + overlay (name / specialties), falling
/// back to the brand gradient + initials when `photo_url` is null or the
/// network image fails.
class BarberHeroImage extends StatelessWidget {
  const BarberHeroImage({
    super.key,
    required this.barber,
    this.height = 216,
    this.hero = false,
    this.overlay,
  });

  final Barber barber;
  final double height;
  final bool hero;

  /// Typically a bottom-aligned name/specialty column, drawn over a scrim.
  final Widget? overlay;

  @override
  Widget build(BuildContext context) {
    final fallback = _FallbackPortrait(
      barber: barber,
      width: double.infinity,
      height: height,
      fontSize: 44,
      showWatermark: true,
    );

    final Widget image;
    final url = _photoUrl(barber);
    if (url == null) {
      image = fallback;
    } else {
      image = Image.network(
        url,
        fit: BoxFit.cover,
        width: double.infinity,
        height: height,
        errorBuilder: (_, __, ___) => fallback,
      );
    }

    final Widget body = Stack(
      fit: StackFit.expand,
      children: [
        SizedBox(width: double.infinity, height: height, child: image),
        if (overlay != null)
          // Scrim keeps overlaid text readable on any portrait.
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.08),
                    Colors.black.withValues(alpha: 0.55),
                  ],
                  stops: const [0.45, 0.7, 1],
                ),
              ),
              child: Align(alignment: Alignment.bottomLeft, child: overlay),
            ),
          ),
      ],
    );

    final Widget clipped = ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: SizedBox(width: double.infinity, height: height, child: body),
    );

    final Widget framed = Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        boxShadow: Brand.cardShadow,
      ),
      child: clipped,
    );

    if (!hero) return framed;
    return Hero(tag: barberPhotoHeroTag(barber.id), child: framed);
  }
}

String? _photoUrl(Barber barber) {
  final url = barber.photoUrl?.trim();
  if (url == null || url.isEmpty || !url.startsWith('http')) return null;
  return url;
}

/// Gradient + monogram placeholder used for `photo_url == null` **and** as the
/// `errorBuilder` target when a remote portrait fails to load.
class _FallbackPortrait extends StatelessWidget {
  const _FallbackPortrait({
    required this.barber,
    required this.width,
    required this.height,
    required this.fontSize,
    required this.showWatermark,
  });

  final Barber barber;
  final double width;
  final double height;
  final double fontSize;
  final bool showWatermark;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        gradient: Brand.seed(barber.id),
        borderRadius:
            showWatermark ? BorderRadius.circular(20) : BorderRadius.zero,
      ),
      child: showWatermark
          ? Stack(
              children: [
                // Decorative scissors watermark for the large header.
                Positioned(
                  right: -12,
                  bottom: -18,
                  child: Icon(
                    Icons.content_cut,
                    size: 132,
                    color: Colors.white.withValues(alpha: 0.14),
                  ),
                ),
                Center(
                  child: Text(
                    barber.initials,
                    style: TextStyle(
                      fontSize: fontSize,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                      letterSpacing: 2,
                    ),
                  ),
                ),
              ],
            )
          : Center(
              child: Text(
                barber.initials,
                style: TextStyle(
                  fontSize: fontSize,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
            ),
    );
  }
}
