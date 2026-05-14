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
  final double drift;

  HomeParticle()
      : x = Random().nextDouble(),
        y = Random().nextDouble(),
        speed = 0.005 + Random().nextDouble() * 0.015,
        size = 1.0 + Random().nextDouble() * 2.0,
        opacity = 0.2 + Random().nextDouble() * 0.5,
        drift = Random().nextDouble() * 2 * pi;
}

class HomeParticlePainter extends CustomPainter {
  final List<HomeParticle> particles;
  final double tick;
  final bool isRunning;

  HomeParticlePainter(this.particles, this.tick, {this.isRunning = false});

  @override
  void paint(Canvas canvas, Size size) {
    // Draw constellation lines between nearby particles
    if (isRunning) {
      final linePaint = Paint()
        ..strokeWidth = 0.8;

      for (var i = 0; i < particles.length; i++) {
        for (var j = i + 1; j < particles.length; j++) {
          final p1 = particles[i];
          final p2 = particles[j];
          final y1 = (p1.y + tick * p1.speed) % 1.0;
          final y2 = (p2.y + tick * p2.speed) % 1.0;
          final x1 = p1.x * size.width + sin(tick * 2 * pi + p1.drift) * 10;
          final x2 = p2.x * size.width + sin(tick * 2 * pi + p2.drift) * 10;
          final dx = x1 - x2;
          final dy = y1 * size.height - y2 * size.height;
          final dist = sqrt(dx * dx + dy * dy);

          if (dist < 80) {
            linePaint.color = const Color(0xFF00E5A0).withOpacity(0.08 * (1 - dist / 80));
            canvas.drawLine(
              Offset(x1, y1 * size.height),
              Offset(x2, y2 * size.height),
              linePaint,
            );
          }
        }
      }
    }

    // Draw particles
    for (final p in particles) {
      final y = (p.y + tick * p.speed) % 1.0;
      final x = p.x * size.width + sin(tick * 2 * pi + p.drift) * 10;
      canvas.drawCircle(
        Offset(x, y * size.height),
        p.size,
        Paint()
          ..color = Colors.white
              .withOpacity(p.opacity * (0.6 + 0.4 * sin(tick * 2 * pi + p.x * 10))),
      );
    }
  }

  @override
  bool shouldRepaint(HomeParticlePainter old) =>
      old.tick != tick || old.isRunning != isRunning;
}

// ── Mesh grid background ─────────────────────────────────────────────────────
class MeshGridPainter extends CustomPainter {
  final double tick;
  final Color color;

  MeshGridPainter({required this.tick, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withOpacity(0.03)
      ..strokeWidth = 0.5;

    const spacing = 40.0;
    final offset = tick % spacing;

    for (var x = offset; x < size.width; x += spacing) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (var y = offset; y < size.height; y += spacing) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }

    // Perspective lines from center
    final center = Offset(size.width / 2, size.height / 2);
    final perspectivePaint = Paint()
      ..color = color.withOpacity(0.02)
      ..strokeWidth = 0.5;

    for (var angle = 0.0; angle < 2 * pi; angle += pi / 6) {
      canvas.drawLine(
        center,
        Offset(
          center.dx + cos(angle) * size.width,
          center.dy + sin(angle) * size.height,
        ),
        perspectivePaint,
      );
    }
  }

  @override
  bool shouldRepaint(MeshGridPainter old) =>
      old.tick != tick || old.color != color;
}

// ── Hexagonal sonar waves ────────────────────────────────────────────────────
class HexSonarPainter extends CustomPainter {
  final double progress;
  final Color color;

  HexSonarPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    for (var i = 0; i < 3; i++) {
      final t = ((progress + i / 3) % 1.0);
      final radius = 50 + t * 130;
      final opacity = (1.0 - t) * 0.4;
      paint.color = color.withOpacity(opacity);

      final path = Path();
      const sides = 6;
      for (var j = 0; j <= sides; j++) {
        final angle = (j * 2 * pi / sides) - pi / 2;
        final x = center.dx + radius * cos(angle);
        final y = center.dy + radius * sin(angle);
        if (j == 0) {
          path.moveTo(x, y);
        } else {
          path.lineTo(x, y);
        }
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant HexSonarPainter old) =>
      old.progress != progress || old.color != color;
}

// ── Gyroscope ring painter ───────────────────────────────────────────────────
class GyroRingPainter extends CustomPainter {
  final Color color;
  final double radius;
  final int segments;
  final double segmentWidth;
  final double gapWidth;
  final bool drawNodes;

  GyroRingPainter({
    required this.color,
    required this.radius,
    required this.segments,
    required this.segmentWidth,
    required this.gapWidth,
    this.drawNodes = false,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final totalAngle = 2 * pi;
    final segmentAngle = totalAngle / segments * 0.6;
    final gapAngle = totalAngle / segments * 0.4;
    final unitAngle = segmentAngle + gapAngle;

    final paint = Paint()
      ..color = color
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;

    for (var i = 0; i < segments; i++) {
      final startAngle = i * unitAngle - pi / 2;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        segmentAngle,
        false,
        paint,
      );

      if (drawNodes) {
        final nodeAngle = startAngle + segmentAngle / 2;
        final nodePos = Offset(
          center.dx + radius * cos(nodeAngle),
          center.dy + radius * sin(nodeAngle),
        );
        canvas.drawCircle(
          nodePos,
          3,
          Paint()..color = color..style = PaintingStyle.fill,
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant GyroRingPainter old) =>
      old.color != color || old.radius != radius || old.segments != segments;
}
