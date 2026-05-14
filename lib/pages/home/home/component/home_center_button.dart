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
    Color primaryColor = const Color(0xFF7B61FF);
    Color secondaryColor = const Color(0xFF2D1B69);
    Color glowColor = const Color(0xFF9D8CFF);
    Color accentColor = const Color(0xFF00F0FF);

    if (isLoading) {
      primaryColor = const Color(0xFFFFD700);
      secondaryColor = const Color(0xFFB8860B);
      glowColor = const Color(0xFFFFE066);
      accentColor = const Color(0xFFFF8C00);
    } else if (isRunning) {
      primaryColor = const Color(0xFF00E5A0);
      secondaryColor = const Color(0xFF005A3C);
      glowColor = const Color(0xFF66FFC2);
      accentColor = const Color(0xFF00FF88);
    }

    return GestureDetector(
      onTap: isLoading ? null : () => controller.startVpn(context),
      child: AnimatedBuilder(
        animation: Listenable.merge([orbitController, pulseAnim, sonarController]),
        builder: (context, child) {
          return SizedBox(
            width: 260,
            height: 260,
            child: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                // Hex sonar waves
                if (isRunning || isLoading)
                  CustomPaint(
                    size: const Size(260, 260),
                    painter: HexSonarPainter(
                      progress: sonarController.value,
                      color: accentColor,
                    ),
                  ),

                // Outer gyroscope ring 1 (large, slow, dotted)
                Transform.rotate(
                  angle: orbitController.value * 2 * pi * 0.3,
                  child: CustomPaint(
                    size: const Size(240, 240),
                    painter: GyroRingPainter(
                      color: glowColor.withOpacity(0.25),
                      radius: 115,
                      segments: 24,
                      segmentWidth: 6,
                      gapWidth: 4,
                    ),
                  ),
                ),

                // Middle gyroscope ring 2 (medium, reverse, dash-dot)
                Transform.rotate(
                  angle: -orbitController.value * 2 * pi * 0.5,
                  child: CustomPaint(
                    size: const Size(200, 200),
                    painter: GyroRingPainter(
                      color: accentColor.withOpacity(0.3),
                      radius: 90,
                      segments: 12,
                      segmentWidth: 12,
                      gapWidth: 8,
                    ),
                  ),
                ),

                // Inner energy ring (fast, thin with nodes)
                Transform.rotate(
                  angle: orbitController.value * 2 * pi * 0.8,
                  child: CustomPaint(
                    size: const Size(170, 170),
                    painter: GyroRingPainter(
                      color: glowColor.withOpacity(0.4),
                      radius: 72,
                      segments: 8,
                      segmentWidth: 2,
                      gapWidth: 2,
                      drawNodes: true,
                    ),
                  ),
                ),

                // Core glow
                AnimatedContainer(
                  duration: const Duration(milliseconds: 600),
                  width: 150,
                  height: 150,
                  decoration: BoxDecoration(
                    shape: BoxShape.rectangle,
                    borderRadius: BorderRadius.circular(40),
                    boxShadow: [
                      BoxShadow(
                        color: glowColor.withOpacity(
                            isRunning && !isLoading ? 0.45 : isLoading ? 0.5 : 0.25),
                        blurRadius: 60,
                        spreadRadius: 15,
                      ),
                      BoxShadow(
                        color: accentColor.withOpacity(0.15),
                        blurRadius: 100,
                        spreadRadius: 30,
                      ),
                    ],
                  ),
                ),

                // Main squircle button
                Transform.scale(
                  scale: (isRunning && !isLoading) ? pulseAnim.value : 1.0,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 500),
                    width: 140,
                    height: 140,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(36),
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [primaryColor, secondaryColor],
                      ),
                      border: Border.all(
                        color: glowColor.withOpacity(0.6),
                        width: 1.5,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: glowColor.withOpacity(0.4),
                          blurRadius: 20,
                          spreadRadius: 2,
                        ),
                        BoxShadow(
                          color: Colors.black.withOpacity(0.4),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(36),
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          // Inner gradient overlay
                          Container(
                            decoration: BoxDecoration(
                              gradient: RadialGradient(
                                center: const Alignment(-0.2, -0.2),
                                radius: 0.8,
                                colors: [
                                  Colors.white.withOpacity(0.2),
                                  Colors.transparent,
                                ],
                              ),
                            ),
                          ),
                          // SVG Icon
                          Padding(
                            padding: const EdgeInsets.all(32),
                            child: SvgPicture.asset(
                              'assets/app_icon/app_icon.svg',
                              fit: BoxFit.contain,
                              colorFilter:
                                  const ColorFilter.mode(Colors.white, BlendMode.srcIn),
                            ),
                          ),
                          // Scan line effect
                          if (isRunning)
                            Positioned(
                              top: 0,
                              left: 0,
                              right: 0,
                              child: AnimatedContainer(
                                duration: const Duration(seconds: 2),
                                height: 2,
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    colors: [
                                      Colors.transparent,
                                      accentColor.withOpacity(0.8),
                                      Colors.transparent,
                                    ],
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),

                // Corner accents
                ..._buildCornerAccents(glowColor, accentColor),
              ],
            ),
          );
        },
      ),
    );
  }

  List<Widget> _buildCornerAccents(Color glowColor, Color accentColor) {
    const offset = 55.0;
    return [
      _cornerAccent(const Offset(-offset, -offset), glowColor),
      _cornerAccent(const Offset(offset, -offset), glowColor),
      _cornerAccent(const Offset(-offset, offset), glowColor),
      _cornerAccent(const Offset(offset, offset), glowColor),
    ];
  }

  Widget _cornerAccent(Offset position, Color color) {
    return Positioned(
      left: 130 + position.dx - 4,
      top: 130 + position.dy - 4,
      child: Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color.withOpacity(0.6),
          boxShadow: [
            BoxShadow(
              color: color.withOpacity(0.8),
              blurRadius: 8,
              spreadRadius: 2,
            ),
          ],
        ),
      ),
    );
  }
}
