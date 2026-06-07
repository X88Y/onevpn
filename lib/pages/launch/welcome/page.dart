import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/gen/assets.gen.dart';
import 'package:mvmvpn/pages/main/url.dart';

class WelcomePage extends StatefulWidget {
  const WelcomePage({super.key});

  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _onNextPage() {
    if (_currentPage < 3) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOut,
      );
    } else {
      _finishOnboarding();
    }
  }

  Future<void> _finishOnboarding() async {
    await PreferencesKey().saveFirstRun(false);
    if (mounted) {
      context.go(RouterPath.firstRun);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    final List<OnboardingSlideData> slides = [
      OnboardingSlideData(
        title: l10n.welcomeSecurityTitle,
        subtitle: l10n.welcomeSecuritySubtitle,
        illustration: FAIllustration(icon: FontAwesomeIcons.shield),
      ),
      OnboardingSlideData(
        title: l10n.welcomePrivacyTitle,
        subtitle: l10n.welcomePrivacySubtitle,
        illustration: FAIllustration(icon: FontAwesomeIcons.handshake),
      ),
      OnboardingSlideData(
        title: l10n.welcomeConnectionTitle,
        subtitle: l10n.welcomeConnectionSubtitle,
        illustration: FAIllustration(icon: FontAwesomeIcons.thumbsUp),
      ),
      OnboardingSlideData(
        title: l10n.welcomeTitle,
        subtitle: l10n.welcomeSubtitle,
        illustration: const ShieldLogoWidget(),
      ),
    ];

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            colors: [
              Color(0xFF0B213F), // Ambient blue glow at the top center
              Color(0xFF050814), // Main app dark background below
            ],
            center: Alignment(0, -0.6),
            radius: 1.2,
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              Expanded(
                child: PageView.builder(
                  controller: _pageController,
                  itemCount: slides.length,
                  onPageChanged: (index) {
                    setState(() {
                      _currentPage = index;
                    });
                  },
                  itemBuilder: (context, index) {
                    final slide = slides[index];
                    return Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 32),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Spacer(flex: 3),
                          // Breathing float animation on the illustration
                          FloatingIllustration(child: slide.illustration),
                          const Spacer(flex: 2),
                          Text(
                            slide.title,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 22,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.5,
                            ),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            slide.subtitle,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.5),
                              fontSize: 14,
                              height: 1.5,
                            ),
                          ),
                          const Spacer(flex: 3),
                        ],
                      ),
                    );
                  },
                ),
              ),
              // Dots and next/start button
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Dot indicators
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: List.generate(slides.length, (index) {
                        final isActive = index == _currentPage;
                        return AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          margin: const EdgeInsets.symmetric(horizontal: 4),
                          width: isActive ? 24 : 8,
                          height: 6,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(3),
                            color: isActive
                                ? const Color(0xFF2196F3) // Brand active blue
                                : Colors.white.withValues(alpha: 0.1),
                          ),
                        );
                      }),
                    ),
                    const SizedBox(height: 32),
                    // Action Button
                    Container(
                      width: double.infinity,
                      height: 56,
                      decoration: BoxDecoration(
                        color: const Color(0xFF2196F3), // Brand blue button
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF2196F3).withValues(alpha: 0.25),
                            blurRadius: 16,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: ElevatedButton(
                        onPressed: _onNextPage,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          foregroundColor: Colors.white,
                          shadowColor: Colors.transparent,
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                        child: Text(
                          _currentPage == 3
                              ? l10n.btnOnboardingStart
                              : l10n.btnOnboardingNext,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.2,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class OnboardingSlideData {
  final String title;
  final String subtitle;
  final Widget illustration;

  const OnboardingSlideData({
    required this.title,
    required this.subtitle,
    required this.illustration,
  });
}

// Floating/Breathing wrapper widget for illustrations
class FloatingIllustration extends StatefulWidget {
  final Widget child;
  const FloatingIllustration({super.key, required this.child});

  @override
  State<FloatingIllustration> createState() => _FloatingIllustrationState();
}

class _FloatingIllustrationState extends State<FloatingIllustration>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat(reverse: true);
    _animation = Tween<double>(begin: -8.0, end: 8.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(0, _animation.value),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

class FAIllustration extends StatelessWidget {
  final FaIconData icon;
  const FAIllustration({super.key, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 150,
      height: 150,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const LinearGradient(
          colors: [
            Color(0xFF003E7E), // Gradient match with shield logo
            Color(0xFF001F3F),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(
          color: const Color(0xFF2196F3).withValues(alpha: 0.6),
          width: 3.5,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF2196F3).withValues(alpha: 0.25),
            blurRadius: 20,
            spreadRadius: 2,
          ),
        ],
      ),
      child: Center(
        child: FaIcon(
          icon,
          size: 64,
          color: Colors.white,
        ),
      ),
    );
  }
}

// Shield logo with app icon in white inside
class ShieldLogoWidget extends StatelessWidget {
  final double size;
  const ShieldLogoWidget({super.key, this.size = 150});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _ShieldLogoPainter(),
      child: SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(size * 0.22),
            child: SvgPicture.asset(
              Assets.appIcon.appIconSvg,
              colorFilter: const ColorFilter.mode(
                Colors.white,
                BlendMode.srcIn,
              ),
              fit: BoxFit.contain,
            ),
          ),
        ),
      ),
    );
  }
}

class _ShieldLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final path = Path();
    path.moveTo(size.width * 0.12, size.height * 0.15);
    path.quadraticBezierTo(size.width * 0.5, size.height * 0.08, size.width * 0.88, size.height * 0.15);
    path.quadraticBezierTo(size.width * 0.9, size.height * 0.6, size.width * 0.5, size.height * 0.93);
    path.quadraticBezierTo(size.width * 0.1, size.height * 0.6, size.width * 0.12, size.height * 0.15);
    path.close();

    final rect = Offset.zero & size;
    final gradient = LinearGradient(
      colors: [
        const Color(0xFF003E7E), // Darker blue shield top
        const Color(0xFF001F3F), // Even darker bottom
      ],
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
    );

    final fillPaint = Paint()
      ..shader = gradient.createShader(rect)
      ..style = PaintingStyle.fill;

    final strokePaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.85)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.5;

    canvas.drawPath(path, fillPaint);
    canvas.drawPath(path, strokePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
