import 'package:flutter/material.dart';

class AmbientOrbs extends StatelessWidget {
  final Animation<double> floatAnim;
  final Animation<double> bgAnim;
  final bool isRunning;

  const AmbientOrbs({
    super.key,
    required this.floatAnim,
    required this.bgAnim,
    required this.isRunning,
  });

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final c1 = isRunning ? const Color(0xFF00E5A0) : const Color(0xFF7B61FF);
    final c2 = isRunning ? const Color(0xFF005A3C) : const Color(0xFF2D1B69);
    
    return AnimatedBuilder(
      animation: floatAnim,
      builder: (context, _) {
        return Stack(
          children: [
            Positioned(
              top: size.height * 0.08 + floatAnim.value,
              right: -40,
              child: _orb(120, c1.withOpacity(0.12)),
            ),
            Positioned(
              top: size.height * 0.15 - floatAnim.value * 0.5,
              left: -30,
              child: _orb(90, c2.withOpacity(0.10)),
            ),
            Positioned(
              bottom: size.height * 0.12 + floatAnim.value * 0.7,
              right: 20,
              child: _orb(70, c1.withOpacity(0.08)),
            ),
          ],
        );
      },
    );
  }

  Widget _orb(double size, Color color) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color,
        boxShadow: [
          BoxShadow(
            color: color,
            blurRadius: size * 0.8,
            spreadRadius: size * 0.1,
          )
        ],
      ),
    );
  }
}
