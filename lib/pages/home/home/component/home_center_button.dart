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
    Color primaryColor = const Color(0xFF2D2D30);
    Color secondaryColor = const Color(0xFF1C1C1E);
    Color glowColor = Colors.white.withOpacity(0.1);
    Color accentColor = Colors.white.withOpacity(0.15);
    Color borderColor = Colors.white.withOpacity(0.15);

    if (isLoading) {
      primaryColor = const Color(0xFFFFD700);
      secondaryColor = const Color(0xFFB8860B);
      glowColor = const Color(0xFFFFE066);
      accentColor = const Color(0xFFFF8C00);
      borderColor = glowColor.withOpacity(0.6);
    } else if (isRunning) {
      primaryColor = const Color(0xFF00E5A0);
      secondaryColor = const Color(0xFF005A3C);
      glowColor = const Color(0xFF66FFC2);
      accentColor = const Color(0xFF00FF88);
      borderColor = glowColor.withOpacity(0.6);
    }

    return GestureDetector(
      onTap: isLoading ? null : () => controller.startVpn(context),
      child: AnimatedBuilder(
        animation: Listenable.merge([orbitController, pulseAnim, sonarController]),
        builder: (context, child) {
          return SizedBox(
            width: 180,
            height: 180,
            child: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                // Core glow
                AnimatedContainer(
                  duration: const Duration(milliseconds: 600),
                  width: 150,
                  height: 150,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: glowColor.withOpacity(
                            isRunning && !isLoading ? 0.35 : isLoading ? 0.4 : 0.15),
                        blurRadius: 40,
                        spreadRadius: 10,
                      ),
                    ],
                  ),
                ),

                // Main circular button
                Transform.scale(
                  scale: (isRunning && !isLoading) ? pulseAnim.value : 1.0,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 500),
                    width: 130,
                    height: 130,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [primaryColor, secondaryColor],
                      ),
                      border: Border.all(
                        color: borderColor,
                        width: 1.5,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: glowColor.withOpacity(0.2),
                          blurRadius: 15,
                          spreadRadius: 1,
                        ),
                        BoxShadow(
                          color: Colors.black.withOpacity(0.3),
                          blurRadius: 8,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: ClipOval(
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
                                  Colors.white.withOpacity(0.15),
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

              ],
            ),
          );
        },
      ),
    );
  }
}
