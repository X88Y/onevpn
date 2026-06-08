import 'dart:async';
import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/main/url.dart';

Future<void> showAnimatedSuccessDialog({String? message}) async {
  final context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) return;

  await showGeneralDialog(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'SuccessDialog',
    barrierColor: Colors.black.withOpacity(0.6),
    transitionDuration: const Duration(milliseconds: 300),
    pageBuilder: (context, anim1, anim2) {
      return AnimatedSuccessDialog(message: message);
    },
    transitionBuilder: (context, anim1, anim2, child) {
      return ScaleTransition(
        scale: CurvedAnimation(
          parent: anim1,
          curve: Curves.easeOutBack,
        ),
        child: FadeTransition(
          opacity: anim1,
          child: child,
        ),
      );
    },
  );
}

class AnimatedSuccessDialog extends StatefulWidget {
  final String? message;

  const AnimatedSuccessDialog({super.key, this.message});

  @override
  State<AnimatedSuccessDialog> createState() => _AnimatedSuccessDialogState();
}

class _AnimatedSuccessDialogState extends State<AnimatedSuccessDialog> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  Timer? _autoCloseTimer;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _controller.forward();

    _autoCloseTimer = Timer(const Duration(milliseconds: 2500), () {
      if (mounted) {
        Navigator.of(context).pop();
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _autoCloseTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.message ?? AppLocalizations.of(context)!.mainOutboundViewImportSuccess;
    
    return Center(
      child: Material(
        color: Colors.transparent,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
            child: Container(
              width: 280,
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: const Color(0xFF0F0F12).withOpacity(0.85),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(
                  color: Colors.white.withOpacity(0.08),
                  width: 1.0,
                ),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 12),
                  SizedBox(
                    width: 72,
                    height: 72,
                    child: AnimatedBuilder(
                      animation: _controller,
                      builder: (context, child) {
                        return CustomPaint(
                          painter: AnimatedCheckmarkPainter(_controller.value),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    AppLocalizations.of(context)?.importSuccessDesc ?? 'Added to your servers list.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF00E5A0).withOpacity(0.12),
                      foregroundColor: const Color(0xFF00E5A0),
                      shadowColor: Colors.transparent,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(
                          color: const Color(0xFF00E5A0).withOpacity(0.3),
                          width: 1.0,
                        ),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 12),
                    ),
                    child: Text(
                      AppLocalizations.of(context)?.btnOK ?? 'OK',
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AnimatedCheckmarkPainter extends CustomPainter {
  final double value;

  AnimatedCheckmarkPainter(this.value);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF00E5A0)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4.5
      ..strokeCap = StrokeCap.round;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 2;

    // Draw circle (first 50% of animation)
    final circlePercent = value < 0.5 ? value / 0.5 : 1.0;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi / 2,
      2 * pi * circlePercent,
      false,
      paint,
    );

    // Draw checkmark (last 50% of animation)
    if (value > 0.5) {
      final checkPercent = (value - 0.5) / 0.5;
      final path = Path();
      
      final start = Offset(size.width * 0.28, size.height * 0.5);
      final mid = Offset(size.width * 0.45, size.height * 0.66);
      final end = Offset(size.width * 0.72, size.height * 0.34);

      path.moveTo(start.dx, start.dy);
      
      if (checkPercent < 0.4) {
        final segmentPercent = checkPercent / 0.4;
        final currentX = start.dx + (mid.dx - start.dx) * segmentPercent;
        final currentY = start.dy + (mid.dy - start.dy) * segmentPercent;
        path.lineTo(currentX, currentY);
      } else {
        path.lineTo(mid.dx, mid.dy);
        final segmentPercent = (checkPercent - 0.4) / 0.6;
        final currentX = mid.dx + (end.dx - mid.dx) * segmentPercent;
        final currentY = mid.dy + (end.dy - mid.dy) * segmentPercent;
        path.lineTo(currentX, currentY);
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant AnimatedCheckmarkPainter oldDelegate) {
    return oldDelegate.value != value;
  }
}
