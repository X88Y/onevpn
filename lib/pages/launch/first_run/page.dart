import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/gen/assets.gen.dart';
import 'package:mvmvpn/pages/launch/first_run/controller.dart';

class FirstRunPage extends StatefulWidget {
  const FirstRunPage({super.key});

  @override
  State<FirstRunPage> createState() => _FirstRunPageState();
}

class _FirstRunPageState extends State<FirstRunPage> with TickerProviderStateMixin {
  final TextEditingController _keyController = TextEditingController();
  late AnimationController _animationController;
  final List<_LoginParticle> _particles = List.generate(25, (_) => _LoginParticle());
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 15),
    )..repeat();
  }

  @override
  void dispose() {
    _keyController.dispose();
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _handleContinue(BuildContext context, FirstRunController controller) async {
    final key = _keyController.text.trim();
    if (key.isEmpty) {
      setState(() {
        _errorMessage = AppLocalizations.of(context)!.loginErrorEmptyKey;
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final success = await controller.submitAccessKey(context, key);

    if (mounted) {
      setState(() {
        _isLoading = false;
        if (!success) {
          _errorMessage = AppLocalizations.of(context)!.loginErrorInvalidKey;
        }
      });
    }
  }

  Future<void> _openUrl(String urlString) async {
    final uri = Uri.parse(urlString);
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      // ignore
    }
  }

  Widget _buildAmbientOrbs(Size size) {
    return AnimatedBuilder(
      animation: _animationController,
      builder: (context, _) {
        final floatValue = math.sin(_animationController.value * 2 * math.pi) * 12.0;
        return Stack(
          children: [
            // Brand Purple Glow (Top Right)
            Positioned(
              top: size.height * 0.05 + floatValue,
              right: -100,
              child: _orb(240, const Color(0xFF7B61FF).withValues(alpha: 0.14)),
            ),
            // Brand Cyan Glow (Center Left)
            Positioned(
              top: size.height * 0.35 - floatValue * 0.8,
              left: -120,
              child: _orb(220, const Color(0xFF00B8D4).withValues(alpha: 0.12)),
            ),
            // Brand Purple Glow (Bottom Right)
            Positioned(
              bottom: size.height * 0.08 + floatValue * 1.2,
              right: -80,
              child: _orb(180, const Color(0xFF7B61FF).withValues(alpha: 0.09)),
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

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final size = MediaQuery.of(context).size;
    
    return BlocProvider(
      create: (_) => FirstRunController(),
      child: BlocBuilder<FirstRunController, FirstRunState>(
        builder: (context, state) {
          final controller = context.read<FirstRunController>();
          return Scaffold(
            backgroundColor: const Color(0xFF050814),
            resizeToAvoidBottomInset: true,
            body: Stack(
              children: [
                // 1. Ambient Glow Orbs
                Positioned.fill(child: _buildAmbientOrbs(size)),
                
                // 2. Custom Mesh Grid background
                Positioned.fill(
                  child: CustomPaint(
                    painter: _LoginMeshGridPainter(
                      color: const Color(0xFF7B61FF),
                    ),
                  ),
                ),

                // 3. Floating constellation particles
                Positioned.fill(
                  child: AnimatedBuilder(
                    animation: _animationController,
                    builder: (context, _) {
                      return CustomPaint(
                        painter: _LoginParticlePainter(
                          _particles,
                          _animationController.value,
                        ),
                      );
                    },
                  ),
                ),

                // 4. Main content scrollable view
                SafeArea(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: 50),
                        // Brand Logo Container with Ambient Glow
                        Center(
                          child: Container(
                            padding: const EdgeInsets.all(16),
                            child: SvgPicture.asset(
                              Assets.appIcon.appIconSvg,
                              width: 140,
                              height: 140,
                              fit: BoxFit.contain,
                              colorFilter: const ColorFilter.mode(
                                Colors.white,
                                BlendMode.srcIn,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 28),
                        // Title "Войдите для подключения"
                        Text(
                          l10n.loginTitle,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const SizedBox(height: 24),
                        // Access Key Input field
                        TextField(
                          controller: _keyController,
                          style: const TextStyle(color: Colors.white),
                          decoration: InputDecoration(
                            hintText: l10n.loginAccessKeyHint,
                            hintStyle: const TextStyle(color: Colors.white30),
                            filled: true,
                            fillColor: Colors.white.withValues(alpha: 0.03),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(16),
                              borderSide: BorderSide(
                                color: const Color(0xFF7B61FF).withValues(alpha: 0.25),
                              ),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(16),
                              borderSide: const BorderSide(
                                color: Color(0xFF00F0FF),
                                width: 1.5,
                              ),
                            ),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
                          ),
                          onChanged: (_) {
                            if (_errorMessage != null) {
                              setState(() {
                                _errorMessage = null;
                              });
                            }
                          },
                        ),
                        if (_errorMessage != null) ...[
                          const SizedBox(height: 8),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 4),
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(color: Colors.redAccent, fontSize: 13, fontWeight: FontWeight.w500),
                            ),
                          ),
                        ],
                        const SizedBox(height: 24),
                        // Continue Button (Premium Brand Gradient)
                        Container(
                          height: 56,
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [
                                Color(0xFF7B61FF), // Purple
                                Color(0xFF00B8D4), // Cyan
                              ],
                            ),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF7B61FF).withValues(alpha: 0.35),
                                blurRadius: 20,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: ElevatedButton(
                            onPressed: _isLoading ? null : () => _handleContinue(context, controller),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.transparent,
                              foregroundColor: Colors.white,
                              shadowColor: Colors.transparent,
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: _isLoading
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  )
                                : Text(
                                    l10n.btnContinue,
                                    style: const TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 1.5,
                                    ),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 28),
                        // Telegram Button (Official Telegram Blue)
                        Container(
                          height: 56,
                          decoration: BoxDecoration(
                            color: const Color(0xFF24A1DE),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF24A1DE).withValues(alpha: 0.2),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: ElevatedButton.icon(
                            onPressed: _isLoading ? null : () => _openUrl("https://t.me/mvmvpnbot"),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.transparent,
                              foregroundColor: Colors.white,
                              shadowColor: Colors.transparent,
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            icon: const FaIcon(FontAwesomeIcons.telegram, size: 20),
                            label: Text(
                              l10n.btnTelegram,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        const SizedBox(height: 16),
                        // VK Button (Official VK Blue)
                        Container(
                          height: 56,
                          decoration: BoxDecoration(
                            color: const Color(0xFF0077FF),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF0077FF).withValues(alpha: 0.2),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: ElevatedButton.icon(
                            onPressed: _isLoading ? null : () => _openUrl("https://m.vk.com/write-130898973"),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.transparent,
                              foregroundColor: Colors.white,
                              shadowColor: Colors.transparent,
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            icon: const FaIcon(FontAwesomeIcons.vk, size: 20),
                            label: Text(
                              l10n.btnVK,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 24),
                      ],
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

// ── Background Particle System ────────────────────────────────────────────────
class _LoginParticle {
  final double x;
  final double y;
  final double speed;
  final double size;
  final double opacity;
  final double drift;

  _LoginParticle()
      : x = math.Random().nextDouble(),
        y = math.Random().nextDouble(),
        speed = 0.002 + math.Random().nextDouble() * 0.005,
        size = 1.0 + math.Random().nextDouble() * 1.8,
        opacity = 0.12 + math.Random().nextDouble() * 0.3,
        drift = math.Random().nextDouble() * 2 * math.pi;
}

class _LoginParticlePainter extends CustomPainter {
  final List<_LoginParticle> particles;
  final double tick;

  _LoginParticlePainter(this.particles, this.tick);

  @override
  void paint(Canvas canvas, Size size) {
    for (final p in particles) {
      final y = (p.y - tick * p.speed) % 1.0; // Float upwards
      final x = p.x * size.width + math.sin(tick * 2 * math.pi + p.drift) * 8;
      canvas.drawCircle(
        Offset(x, y * size.height),
        p.size,
        Paint()
          ..color = Colors.white.withValues(
            alpha: p.opacity * (0.6 + 0.4 * math.sin(tick * 2 * math.pi + p.x * 10)),
          ),
      );
    }
  }

  @override
  bool shouldRepaint(_LoginParticlePainter old) => old.tick != tick;
}

// ── Background Mesh Grid ─────────────────────────────────────────────────────
class _LoginMeshGridPainter extends CustomPainter {
  final Color color;

  _LoginMeshGridPainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withValues(alpha: 0.02)
      ..strokeWidth = 0.5;

    const spacing = 48.0;
    for (var x = 0.0; x < size.width; x += spacing) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (var y = 0.0; y < size.height; y += spacing) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
