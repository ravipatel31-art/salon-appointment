import 'package:flutter/material.dart';

import '../../app/brand.dart';
import '../../data/models/service_model.dart';

/// Client-owned service art (contract § Imagery: the API has **no**
/// `image_url` — presentation art lives in Flutter, keyed by `service.id` /
/// name). Each catalog service gets a Material icon + a distinct soft
/// gradient so cards and chips read like a premium menu, entirely offline.
class ServiceArt {
  const ServiceArt({
    required this.icon,
    required this.gradient,
    required this.tint,
  });

  /// Material icon representing the service.
  final IconData icon;

  /// Soft brand-family gradient used as the card illustration.
  final LinearGradient gradient;

  /// Accent color for icons / chip tints on light surfaces.
  final Color tint;

  /// Pale tinted fill for icon chips.
  Color get softTint => Brand.soft(tint);

  // ---------------------------------------------------------- catalog arts
  // Ids match the AGENTS.md seed catalog (GET /services).

  static const ServiceArt haircut = ServiceArt(
    icon: Icons.content_cut,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF7A2E4A), Color(0xFFB15C7E)],
    ),
    tint: Color(0xFF7A2E4A),
  );

  static const ServiceArt shaving = ServiceArt(
    icon: Icons.face,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF46586B), Color(0xFF7E93A8)],
    ),
    tint: Color(0xFF46586B),
  );

  static const ServiceArt beardTrim = ServiceArt(
    icon: Icons.brush,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF8A5A2B), Color(0xFFC79A63)],
    ),
    tint: Color(0xFF8A5A2B),
  );

  static const ServiceArt massage = ServiceArt(
    icon: Icons.spa,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF5E6B4F), Color(0xFF94A576)],
    ),
    tint: Color(0xFF5E6B4F),
  );

  static const ServiceArt massageHaircut = ServiceArt(
    icon: Icons.self_improvement,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFFA8577B), Color(0xFFB08D57)],
    ),
    tint: Color(0xFFA8577B),
  );

  static const ServiceArt shaveMassage = ServiceArt(
    icon: Icons.spa_outlined,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF4E6070), Color(0xFF9B8AA6)],
    ),
    tint: Color(0xFF4E6070),
  );

  static const ServiceArt fullCombo = ServiceArt(
    icon: Icons.workspace_premium,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFFB08D57), Color(0xFF7A2E4A)],
    ),
    tint: Color(0xFF9A7440),
  );

  static const ServiceArt hairColor = ServiceArt(
    icon: Icons.palette,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF8E3F73), Color(0xFFE08A5B)],
    ),
    tint: Color(0xFF8E3F73),
  );

  static const ServiceArt haircutShaving = ServiceArt(
    icon: Icons.auto_awesome,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF7A2E4A), Color(0xFF4E6070)],
    ),
    tint: Color(0xFF5F4658),
  );

  static const ServiceArt haircutBeard = ServiceArt(
    icon: Icons.diamond,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF7A2E4A), Color(0xFFC79A63)],
    ),
    tint: Color(0xFF7A2E4A),
  );

  /// Wash add-on (allowed on any service).
  static const ServiceArt wash = ServiceArt(
    icon: Icons.water_drop,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF3E7C8F), Color(0xFF8FC3D4)],
    ),
    tint: Color(0xFF3E7C8F),
  );

  /// Fallback for admin-added / unknown services.
  static const ServiceArt generic = ServiceArt(
    icon: Icons.auto_awesome_outlined,
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF7A2E4A), Color(0xFFB08D57)],
    ),
    tint: Color(0xFF7A2E4A),
  );

  /// Resolves art for a catalog service — seeded ids first (stable AGENTS
  /// catalog), then name keywords so rows added via admin CRUD still get art.
  static ServiceArt of({int? id, String name = ''}) {
    switch (id) {
      case 1:
        return haircut;
      case 2:
        return shaving;
      case 3:
        return beardTrim;
      case 4:
        return massageHaircut;
      case 5:
        return shaveMassage;
      case 6:
        return fullCombo;
      case 7:
        return hairColor;
      case 8:
        return haircutShaving;
      case 9:
        return haircutBeard;
    }
    return fromName(name);
  }

  static ServiceArt forService(ServiceItem service) =>
      of(id: service.id, name: service.name);

  /// Name-keyword fallback (order matters: compound names first).
  static ServiceArt fromName(String raw) {
    final n = raw.toLowerCase();
    if (n.isEmpty) return generic;
    if (n.contains('color')) return hairColor;
    if (n.contains('wash')) return wash;
    if (n.contains('combo')) return fullCombo;
    if (n.contains('mass') && (n.contains('hair') || n.contains('cut'))) {
      return massageHaircut;
    }
    if (n.contains('mass') && n.contains('shav')) return shaveMassage;
    if (n.contains('mass')) return massage;
    if (n.contains('hair') && n.contains('shav')) return haircutShaving;
    if (n.contains('hair') && n.contains('beard')) return haircutBeard;
    if (n.contains('beard')) return beardTrim;
    if (n.contains('shav') || n.contains('shave')) return shaving;
    if (n.contains('hair') || n.contains('cut')) return haircut;
    return generic;
  }
}

/// Image-like illustration strip for service cards: brand gradient + a bold
/// foreground icon and an oversized watermark icon (no assets required).
class ServiceArtBanner extends StatelessWidget {
  const ServiceArtBanner({
    super.key,
    required this.art,
    this.height = 84,
  });

  final ServiceArt art;
  final double height;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
      child: SizedBox(
        width: double.infinity,
        height: height,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned.fill(
              child: DecoratedBox(decoration: BoxDecoration(gradient: art.gradient)),
            ),
            Positioned(
              right: -14,
              bottom: -26,
              child: Icon(
                art.icon,
                size: 108,
                color: Colors.white.withValues(alpha: 0.16),
              ),
            ),
            Positioned(
              left: 18,
              bottom: 16,
              child: Icon(art.icon, size: 34, color: Colors.white),
            ),
            Positioned(
              right: 16,
              top: 16,
              child: Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.55),
                  shape: BoxShape.circle,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Small circular icon chip (service chips, checkout summary header…).
class ServiceArtChip extends StatelessWidget {
  const ServiceArtChip({
    super.key,
    required this.art,
    this.size = 36,
    this.iconSize = 18,
  });

  final ServiceArt art;
  final double size;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: art.gradient,
        borderRadius: BorderRadius.circular(size * 0.3),
        boxShadow: [
          BoxShadow(
            color: art.tint.withValues(alpha: 0.30),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Icon(art.icon, size: iconSize, color: Colors.white),
    );
  }
}
