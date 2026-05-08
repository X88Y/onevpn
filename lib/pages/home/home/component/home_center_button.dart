import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';
import 'package:mvmvpn/pages/home/home/component/home_painters.dart';

class HomeCenterButton extends StatelessWidget {
  final HomeController controller;
  final bool isRunning;
  final bool isLoading;
  final AnimationController orbitController;
  final AnimationController sonarController;
  final Animation<double> pulseAnim;

  const HomeCenterButton({
    super.key,
    required this.controller,
    required this.isRunning,
    required this.isLoading,
    required this.orbitController,
    required this.sonarController,
    required this.pulseAnim,
  });

  @override
  Widget build(BuildContext context) {
    Color primaryColor = const Color(0xFF6C63FF);
    Color secondaryColor = const Color(0xFF3B3AAF);
    Color glowColor = const Color(0xFF6C63FF);

    if (isLoading) {
      primaryColor = const Color(0xFFFFC107);
      secondaryColor = const Color(0xFFFF8F00);
      glowColor = const Color(0xFFFFC107);
    } else if (isRunning) {
      primaryColor = const Color(0xFF00E676);
      secondaryColor = const Color(0xFF00897B);
      glowColor = const Color(0xFF00E676);
    }

    return GestureDetector(
      onTap: () => controller.startVpn(context),
      child: AnimatedBuilder(
        animation: Listenable.merge([orbitController, pulseAnim]),
        builder: (context, child) {
          return SizedBox(
            width: 240,
            height: 240,
            child: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                // Sonar rings
                if (isRunning || isLoading)
                  AnimatedBuilder(
                    animation: sonarController,
                    builder: (_, __) => CustomPaint(
                      size: const Size(240, 240),
                      painter: SonarPainter(
                        progress: sonarController.value,
                        color: (isRunning && !isLoading) ? const Color(0xFF00E676) : const Color(0xFFFFC107),
                      ),
                    ),
                  ),
                // Outer glow
                AnimatedContainer(
                  duration: const Duration(milliseconds: 500),
                  width: 220,
                  height: 220,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: glowColor.withOpacity(isRunning && !isLoading ? 0.35 : isLoading ? 0.4 : 0.2),
                        blurRadius: 80,
                        spreadRadius: 20,
                      ),
                    ],
                  ),
                ),
                // Orbiting ring 1
                Transform.rotate(
                  angle: orbitController.value * 2 * pi,
                  child: CustomPaint(
                    size: const Size(200, 200),
                    painter: OrbitRingPainter(color: glowColor.withOpacity(0.25), dashCount: 12),
                  ),
                ),
                // Orbiting ring 2 (reverse)
                Transform.rotate(
                  angle: -orbitController.value * 2 * pi * 0.7,
                  child: CustomPaint(
                    size: const Size(170, 170),
                    painter: OrbitRingPainter(color: glowColor.withOpacity(0.15), dashCount: 8),
                  ),
                ),
                // Loading spinner
                if (isLoading)
                  SizedBox(
                    width: 148,
                    height: 148,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.5,
                      valueColor: AlwaysStoppedAnimation<Color>(glowColor.withOpacity(0.7)),
                    ),
                  ),
                // Main button with pulse
                Transform.scale(
                  scale: (isRunning && !isLoading) ? pulseAnim.value : 1.0,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 500),
                    width: 136,
                    height: 136,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [primaryColor, secondaryColor],
                        center: const Alignment(-0.3, -0.3),
                      ),
                      boxShadow: [
                        BoxShadow(color: glowColor.withOpacity(0.5), blurRadius: 30, spreadRadius: 5),
                      ],
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(30),
                      child: SvgPicture.asset(
                        'assets/app_icon/app_icon.svg',
                        fit: BoxFit.contain,
                        colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
