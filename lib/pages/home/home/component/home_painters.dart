import 'dart:math';
import 'package:flutter/material.dart';

// ── Dashed orbit ring painter ────────────────────────────────────────────────
class OrbitRingPainter extends CustomPainter {
  final Color color;
  final int dashCount;

  OrbitRingPainter({required this.color, required this.dashCount});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;
    final dashAngle = (2 * pi) / dashCount;
    const gapRatio = 0.4;
    for (var i = 0; i < dashCount; i++) {
      final startAngle = i * dashAngle;
      final sweepAngle = dashAngle * (1 - gapRatio);
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        sweepAngle,
        false,
        paint,
      );
    }
    // Draw dot at the leading edge of first dash
    final dotAngle = dashAngle * (1 - gapRatio);
    final dotPos = Offset(center.dx + radius * cos(dotAngle), center.dy + radius * sin(dotAngle));
    canvas.drawCircle(dotPos, 3, Paint()..color = color..style = PaintingStyle.fill);
  }

  @override
  bool shouldRepaint(OrbitRingPainter old) => old.color != color;
}

// ── Sonar expanding rings ────────────────────────────────────────────────────
class SonarPainter extends CustomPainter {
  final double progress;
  final Color color;
  SonarPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    for (var i = 0; i < 3; i++) {
      final t = ((progress + i / 3) % 1.0);
      final radius = 60 + t * (size.width * 1.2); // Scaled relative to button size
      final opacity = (1.0 - t) * 0.35;
      canvas.drawCircle(
        center,
        radius,
        Paint()
          ..color = color.withOpacity(opacity)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5,
      );
    }
  }

  @override
  bool shouldRepaint(SonarPainter old) => old.progress != progress || old.color != color;
}

// ── Particle model & painter ─────────────────────────────────────────────────
class HomeParticle {
  final double x;
  final double y;
  final double speed;
  final double size;
  final double opacity;
  HomeParticle()
      : x = Random().nextDouble(),
        y = Random().nextDouble(),
        speed = 0.005 + Random().nextDouble() * 0.015,
        size = 1.0 + Random().nextDouble() * 2.0,
        opacity = 0.2 + Random().nextDouble() * 0.5;
}

class HomeParticlePainter extends CustomPainter {
  final List<HomeParticle> particles;
  final double tick;
  HomeParticlePainter(this.particles, this.tick);

  @override
  void paint(Canvas canvas, Size size) {
    for (final p in particles) {
      final y = (p.y + tick * p.speed) % 1.0;
      canvas.drawCircle(
        Offset(p.x * size.width, y * size.height),
        p.size,
        Paint()..color = Colors.white.withOpacity(p.opacity * (0.6 + 0.4 * sin(tick * 2 * pi + p.x * 10))),
      );
    }
  }

  @override
  bool shouldRepaint(HomeParticlePainter old) => old.tick != tick;
}
