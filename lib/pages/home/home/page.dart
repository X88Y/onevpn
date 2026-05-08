import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/event_bus/state.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with TickerProviderStateMixin {
  late final TabController _tabController = TabController(length: 2, vsync: this);
  late AnimationController _orbitController;
  late AnimationController _pulseController;
  late AnimationController _bgController;
  late AnimationController _floatController;
  late Animation<double> _pulseAnim;
  late Animation<double> _bgAnim;
  late Animation<double> _floatAnim;

  @override
  void initState() {
    super.initState();
    _orbitController = AnimationController(vsync: this, duration: const Duration(seconds: 8))..repeat();
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
    _bgController = AnimationController(vsync: this, duration: const Duration(seconds: 6))..repeat(reverse: true);
    _floatController = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.92, end: 1.08).animate(CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut));
    _bgAnim = Tween<double>(begin: 0.0, end: 1.0).animate(CurvedAnimation(parent: _bgController, curve: Curves.easeInOut));
    _floatAnim = Tween<double>(begin: -8.0, end: 8.0).animate(CurvedAnimation(parent: _floatController, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _tabController.dispose();
    _orbitController.dispose();
    _pulseController.dispose();
    _bgController.dispose();
    _floatController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => HomeController(context, _tabController),
      child: BlocBuilder<HomeController, HomeState>(
        builder: (context, homeState) {
          final controller = context.read<HomeController>();
          return BlocBuilder<AppEventBus, AppEventBusState>(
            builder: (context, eventState) {
              final isRunning = eventState.runningId != DBConstants.defaultId;
              final isLoading = eventState.vpnLoading;
              return Scaffold(
                backgroundColor: const Color(0xFF050814),
                body: AnimatedBuilder(
                  animation: _bgAnim,
                  builder: (context, child) {
                    return Container(
                      decoration: BoxDecoration(
                        gradient: RadialGradient(
                          center: Alignment(
                            -0.3 + _bgAnim.value * 0.6,
                            -0.5 + _bgAnim.value * 0.3,
                          ),
                          radius: 1.4,
                          colors: isRunning
                              ? [
                                  const Color(0xFF003320),
                                  const Color(0xFF050814),
                                ]
                              : isLoading
                                  ? [
                                      const Color(0xFF1A1200),
                                      const Color(0xFF050814),
                                    ]
                                  : [
                                      const Color(0xFF0D0A2E),
                                      const Color(0xFF050814),
                                    ],
                        ),
                      ),
                      child: child,
                    );
                  },
                  child: SafeArea(
                    child: Stack(
                      children: [
                        // Ambient orbs background
                        _AmbientOrbs(floatAnim: _floatAnim, bgAnim: _bgAnim, isRunning: isRunning),
                        // Main content
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                          child: Column(
                            children: [
                              _topBar(context, controller, eventState, homeState),
                              const SizedBox(height: 20),
                              _authButtons(context, controller, eventState, homeState),
                              const Spacer(),
                              _centerButton(context, controller, eventState, isRunning, isLoading),
                              const SizedBox(height: 28),
                              _statusText(eventState, isRunning, isLoading),
                              const Spacer(),
                              _subscriptionPill(context, eventState, homeState),
                              const SizedBox(height: 16),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _topBar(BuildContext context, HomeController controller, AppEventBusState eventState, HomeState homeState) {
    final user = eventState.userData;
    final isAppleLinked = user?.isAppleLinked ?? false;
    final isTelegramLinked = user?.isTelegramLinked ?? false;
    final isVkLinked = user?.isVkLinked ?? false;
    final hasSocials = isAppleLinked || isTelegramLinked || isVkLinked;

    return Row(
      children: [
        // Account bubble
        _accountBubble(context, controller, isSmall: !hasSocials),
        const Spacer(),
        // Connected social bubbles on the right
        if (isAppleLinked) ...[
          _socialBubble(
            icon: FontAwesomeIcons.apple,
            glowColor: Colors.grey[300]!,
            onTap: () => controller.signInWithApple(),
            isHighlighted: homeState.highlightBubbles,
            isLoading: homeState.connectingProvider == 'apple',
          ),
          const SizedBox(width: 10),
        ],
        if (isTelegramLinked) ...[
          _socialBubble(
            icon: FontAwesomeIcons.telegram,
            glowColor: const Color(0xFF2AABEE),
            onTap: () => controller.connectTelegram(),
            isHighlighted: homeState.highlightBubbles,
            isLoading: homeState.connectingProvider == 'telegram',
          ),
          const SizedBox(width: 10),
        ],
        if (isVkLinked)
          _socialBubble(
            icon: FontAwesomeIcons.vk,
            glowColor: const Color(0xFF4C75A3),
            onTap: () => controller.connectVK(),
            isHighlighted: homeState.highlightBubbles,
            isLoading: homeState.connectingProvider == 'vk',
          ),
      ],
    );
  }

  Widget _socialBubble({
    required dynamic icon,
    required Color glowColor,
    required VoidCallback onTap,
    bool isHighlighted = false,
    bool isLoading = false,
  }) {
    return GestureDetector(
      onTap: isLoading ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 600),
        curve: Curves.easeInOut,
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isHighlighted ? glowColor.withOpacity(0.2) : Colors.white.withOpacity(0.08),
          border: Border.all(
            color: isHighlighted ? glowColor.withOpacity(0.8) : Colors.white.withOpacity(0.15),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: glowColor.withOpacity(isHighlighted ? 0.5 : 0.2),
              blurRadius: isHighlighted ? 20 : 10,
              spreadRadius: isHighlighted ? 3 : 0,
            ),
          ],
        ),
        alignment: Alignment.center,
        child: isLoading
            ? SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(glowColor),
                ),
              )
            : FaIcon(icon, color: Colors.white, size: 20),
      ),
    );
  }

  Widget _authButtons(BuildContext context, HomeController controller, AppEventBusState eventState, HomeState homeState) {
    final user = eventState.userData;
    final buttons = <Widget>[];

    if (!(user?.isAppleLinked ?? false)) {
      buttons.add(_authButton(
        icon: FontAwesomeIcons.apple,
        gradient: const LinearGradient(colors: [Color(0xFF4A4A4A), Color(0xFF2A2A2A)]),
        glowColor: Colors.grey[400]!,
        title: AppLocalizations.of(context)!.homeFreeSubscription,
        onTap: () => controller.signInWithApple(),
        isHighlighted: homeState.highlightSocials,
        isLoading: homeState.connectingProvider == 'apple',
      ));
    }
    if (!(user?.isTelegramLinked ?? false)) {
      buttons.add(_authButton(
        icon: FontAwesomeIcons.telegram,
        gradient: const LinearGradient(colors: [Color(0xFF1E88E5), Color(0xFF0D47A1)]),
        glowColor: const Color(0xFF2AABEE),
        title: AppLocalizations.of(context)!.homeConnectTelegram,
        onTap: () => controller.connectTelegram(),
        isHighlighted: homeState.highlightSocials || homeState.highlightBubbles,
        isLoading: homeState.connectingProvider == 'telegram',
      ));
    }
    if (!(user?.isVkLinked ?? false)) {
      buttons.add(_authButton(
        icon: FontAwesomeIcons.vk,
        gradient: const LinearGradient(colors: [Color(0xFF4C75A3), Color(0xFF2D4F7A)]),
        glowColor: const Color(0xFF4C75A3),
        title: AppLocalizations.of(context)!.homeConnectVK,
        onTap: () => controller.connectVK(),
        isHighlighted: homeState.highlightSocials || homeState.highlightBubbles,
        isLoading: homeState.connectingProvider == 'vk',
      ));
    }

    if (buttons.isEmpty) return const SizedBox.shrink();

    return Column(
      children: [
        for (var i = 0; i < buttons.length; i++) ...[
          buttons[i],
          if (i < buttons.length - 1) const SizedBox(height: 10),
        ],
      ],
    );
  }

  Widget _authButton({
    required dynamic icon,
    required LinearGradient gradient,
    required Color glowColor,
    required String title,
    required VoidCallback onTap,
    required bool isHighlighted,
    bool isLoading = false,
  }) {
    return GestureDetector(
      onTap: isLoading ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 600),
        curve: Curves.easeInOut,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          color: Colors.white.withOpacity(0.04),
          border: Border.all(
            color: isHighlighted ? glowColor.withOpacity(0.7) : Colors.white.withOpacity(0.08),
            width: 1.5,
          ),
          boxShadow: isHighlighted
              ? [BoxShadow(color: glowColor.withOpacity(0.4), blurRadius: 24, spreadRadius: 4)]
              : [BoxShadow(color: Colors.black.withOpacity(0.3), blurRadius: 8)],
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: gradient,
                borderRadius: BorderRadius.circular(12),
                boxShadow: [BoxShadow(color: glowColor.withOpacity(0.3), blurRadius: 8)],
              ),
              alignment: Alignment.center,
              child: FaIcon(icon, color: Colors.white, size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: 0.2),
              ),
            ),
            isLoading
                ? SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation<Color>(glowColor)),
                  )
                : Icon(Icons.arrow_forward_ios_rounded, color: Colors.white.withOpacity(0.3), size: 16),
          ],
        ),
      ),
    );
  }

  Widget _centerButton(BuildContext context, HomeController controller, AppEventBusState eventState, bool isRunning, bool isLoading) {
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
        animation: Listenable.merge([_orbitController, _pulseAnim]),
        builder: (context, child) {
          return SizedBox(
            width: 240,
            height: 240,
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Outer glow
                AnimatedContainer(
                  duration: const Duration(milliseconds: 500),
                  width: 220,
                  height: 220,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: glowColor.withOpacity(isRunning ? 0.35 : isLoading ? 0.4 : 0.2),
                        blurRadius: 80,
                        spreadRadius: 20,
                      ),
                    ],
                  ),
                ),
                // Orbiting ring 1
                Transform.rotate(
                  angle: _orbitController.value * 2 * pi,
                  child: CustomPaint(
                    size: const Size(200, 200),
                    painter: _OrbitRingPainter(color: glowColor.withOpacity(0.25), dashCount: 12),
                  ),
                ),
                // Orbiting ring 2 (reverse)
                Transform.rotate(
                  angle: -_orbitController.value * 2 * pi * 0.7,
                  child: CustomPaint(
                    size: const Size(170, 170),
                    painter: _OrbitRingPainter(color: glowColor.withOpacity(0.15), dashCount: 8),
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
                  scale: isRunning ? _pulseAnim.value : 1.0,
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

  Widget _statusText(AppEventBusState eventState, bool isRunning, bool isLoading) {
    String text = isRunning ? AppLocalizations.of(context)!.homeConnected : AppLocalizations.of(context)!.homeTapToConnect;
    if (isLoading) {
      text = isRunning ? AppLocalizations.of(context)!.homeDisconnecting : AppLocalizations.of(context)!.homeConnecting;
    }

    Color textColor = Colors.white.withOpacity(0.7);
    if (isRunning) textColor = const Color(0xFF00E676);
    if (isLoading) textColor = const Color(0xFFFFC107);

    return AnimatedDefaultTextStyle(
      duration: const Duration(milliseconds: 400),
      style: TextStyle(
        color: textColor,
        fontSize: 17,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.5,
      ),
      child: Text(text),
    );
  }

  Widget _subscriptionPill(BuildContext context, AppEventBusState eventState, HomeState homeState) {
    final isRunning = eventState.runningId != DBConstants.defaultId;
    final user = eventState.userData;
    final hasActiveSubscription = user?.hasActiveSubscription ?? false;
    final subscriptionEndsAt = user?.subscriptionEndsAt;

    if (isRunning || hasActiveSubscription) {
      final statusText = hasActiveSubscription && subscriptionEndsAt != null
          ? AppLocalizations.of(context)!.homeSubscriptionActiveUntil(
              '${subscriptionEndsAt.day.toString().padLeft(2, '0')}.${subscriptionEndsAt.month.toString().padLeft(2, '0')}.${subscriptionEndsAt.year}')
          : AppLocalizations.of(context)!.homeSubscriptionActive;
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            colors: [Colors.green.withOpacity(0.15), Colors.teal.withOpacity(0.1)],
          ),
          border: Border.all(color: Colors.green.withOpacity(0.3)),
          boxShadow: [BoxShadow(color: Colors.green.withOpacity(0.15), blurRadius: 16)],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.verified_rounded, color: Colors.green, size: 18),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                statusText,
                style: const TextStyle(color: Colors.green, fontSize: 14, fontWeight: FontWeight.w600),
                overflow: TextOverflow.visible,
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        color: Colors.white.withOpacity(0.04),
        border: Border.all(color: Colors.white.withOpacity(0.07)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.lock_outline_rounded, color: Colors.white.withOpacity(0.35), size: 18),
          const SizedBox(width: 10),
          Text(
            AppLocalizations.of(context)!.homeNoActiveSubscription,
            style: TextStyle(color: Colors.white.withOpacity(0.35), fontSize: 14, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  Widget _accountBubble(BuildContext context, HomeController controller, {bool isSmall = false}) {
    final size = isSmall ? 36.0 : 46.0;
    final iconSize = isSmall ? 16.0 : 20.0;
    return GestureDetector(
      onTap: () => _showAccountModal(context, controller, showDelete: !isSmall),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.white.withOpacity(0.07),
          border: Border.all(color: Colors.white.withOpacity(0.12), width: 1.5),
        ),
        alignment: Alignment.center,
        child: Icon(Icons.person_outline_rounded, color: Colors.white.withOpacity(0.8), size: iconSize),
      ),
    );
  }

  void _showAccountModal(BuildContext context, HomeController controller, {required bool showDelete}) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF0F1120),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(width: 36, height: 4, decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2))),
                const SizedBox(height: 16),
                if (showDelete) ...[
                  ListTile(
                    leading: const Icon(Icons.delete_forever_rounded, color: Colors.redAccent),
                    title: Text(AppLocalizations.of(context)!.homeDeleteAccount,
                        style: const TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600)),
                    onTap: () {
                      Navigator.pop(context);
                      controller.clearAllData();
                    },
                  ),
                  Divider(color: Colors.white.withOpacity(0.08)),
                ],
                ListTile(
                  leading: Icon(Icons.description_outlined, color: Colors.white.withOpacity(0.7)),
                  title: Text(AppLocalizations.of(context)!.homeThirdPartyLicense,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500)),
                  onTap: () {
                    Navigator.pop(context);
                    controller.openUrl('https://front-redirect.vercel.app/license');
                  },
                ),
                ListTile(
                  leading: Icon(Icons.privacy_tip_outlined, color: Colors.white.withOpacity(0.7)),
                  title: Text(AppLocalizations.of(context)!.homeTerms, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500)),
                  onTap: () {
                    Navigator.pop(context);
                    controller.openUrl('https://www.aiverge.net/terms');
                  },
                ),
                ListTile(
                  leading: Icon(Icons.shield_outlined, color: Colors.white.withOpacity(0.7)),
                  title: Text(AppLocalizations.of(context)!.homePrivacy, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500)),
                  onTap: () {
                    Navigator.pop(context);
                    controller.openUrl('https://www.aiverge.net/privacy');
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ── Ambient floating orbs ────────────────────────────────────────────────────
class _AmbientOrbs extends StatelessWidget {
  final Animation<double> floatAnim;
  final Animation<double> bgAnim;
  final bool isRunning;

  const _AmbientOrbs({required this.floatAnim, required this.bgAnim, required this.isRunning});

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final c1 = isRunning ? const Color(0xFF00E676) : const Color(0xFF6C63FF);
    final c2 = isRunning ? const Color(0xFF00897B) : const Color(0xFF3B3AAF);
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
        boxShadow: [BoxShadow(color: color, blurRadius: size * 0.8, spreadRadius: size * 0.1)],
      ),
    );
  }
}

// ── Dashed orbit ring painter ────────────────────────────────────────────────
class _OrbitRingPainter extends CustomPainter {
  final Color color;
  final int dashCount;

  _OrbitRingPainter({required this.color, required this.dashCount});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;
    final dashAngle = (2 * pi) / dashCount;
    final gapRatio = 0.4;
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
  bool shouldRepaint(_OrbitRingPainter old) => old.color != color;
}
