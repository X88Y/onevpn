import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/event_bus/state.dart';

import 'component/home_painters.dart';
import 'component/ambient_orbs.dart';
import 'component/social_bubble.dart';
import 'component/auth_button.dart';
import 'component/subscription_pill.dart';
import 'component/account_bubble.dart';
import 'component/home_center_button.dart';

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
  late AnimationController _sonarController;
  late AnimationController _particleController;
  late Animation<double> _pulseAnim;
  late Animation<double> _bgAnim;
  late Animation<double> _floatAnim;

  final List<HomeParticle> _particles = List.generate(40, (_) => HomeParticle());

  @override
  void initState() {
    super.initState();
    _orbitController = AnimationController(vsync: this, duration: const Duration(seconds: 8))..repeat();
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
    _bgController = AnimationController(vsync: this, duration: const Duration(seconds: 6))..repeat(reverse: true);
    _floatController = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat(reverse: true);
    _sonarController = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
    _particleController = AnimationController(vsync: this, duration: const Duration(seconds: 20))..repeat();
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
    _sonarController.dispose();
    _particleController.dispose();
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
              final isLoading = eventState.vpnLoading || eventState.isUpdatingSubscription;
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
                          colors: isLoading
                              ? [const Color(0xFF1A1200), const Color(0xFF050814)]
                              : isRunning && !eventState.isUpdatingSubscription
                                  ? [const Color(0xFF003320), const Color(0xFF050814)]
                                  : [const Color(0xFF0D0A2E), const Color(0xFF050814)],
                        ),
                      ),
                      child: child,
                    );
                  },
                  child: SafeArea(
                    child: Stack(
                      children: [
                        // Particle starfield
                        Positioned.fill(
                          child: AnimatedBuilder(
                            animation: _particleController,
                            builder: (_, __) => CustomPaint(
                              painter: HomeParticlePainter(_particles, _particleController.value),
                            ),
                          ),
                        ),
                        // Ambient orbs background
                        AmbientOrbs(floatAnim: _floatAnim, bgAnim: _bgAnim, isRunning: isRunning),
                        // Main content
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                          child: Column(
                            children: [
                              _buildTopBar(context, controller, eventState, homeState, isLoading),
                              const SizedBox(height: 20),
                              _buildAuthButtons(context, controller, eventState, homeState, isLoading),
                              const Spacer(),
                              HomeCenterButton(
                                controller: controller,
                                isRunning: isRunning,
                                isLoading: isLoading || homeState.connectingProvider != null,
                                orbitController: _orbitController,
                                sonarController: _sonarController,
                                pulseAnim: _pulseAnim,
                              ),
                              const SizedBox(height: 28),
                              _buildStatusText(eventState, isRunning, isLoading),
                              const Spacer(),
                              SubscriptionPill(eventState: eventState, shimmerController: _bgController),
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

  Widget _buildTopBar(BuildContext context, HomeController controller, AppEventBusState eventState, HomeState homeState, bool isLoading) {
    final user = eventState.userData;
    final isAppleLinked = user?.isAppleLinked ?? false;
    final isTelegramLinked = user?.isTelegramLinked ?? false;
    final isVkLinked = user?.isVkLinked ?? false;
    final hasSocials = isAppleLinked || isTelegramLinked || isVkLinked;

    return Row(
      children: [
        AccountBubble(controller: controller, isSmall: !hasSocials, isLoading: isLoading || homeState.connectingProvider != null),
        const Spacer(),
        if (isAppleLinked) ...[
          SocialBubble(
            icon: FontAwesomeIcons.apple,
            glowColor: Colors.grey[300]!,
            onTap: () => controller.signInWithApple(),
            isHighlighted: homeState.highlightBubbles,
            isLoading: homeState.connectingProvider == 'apple',
            isEnabled: !isLoading && homeState.connectingProvider == null,
          ),
          const SizedBox(width: 10),
        ],
        if (isTelegramLinked) ...[
          SocialBubble(
            icon: FontAwesomeIcons.telegram,
            glowColor: const Color(0xFF2AABEE),
            onTap: () => controller.connectTelegram(),
            isHighlighted: homeState.highlightBubbles,
            isLoading: homeState.connectingProvider == 'telegram',
            isEnabled: !isLoading && homeState.connectingProvider == null,
          ),
          const SizedBox(width: 10),
        ],
        if (isVkLinked)
          SocialBubble(
            icon: FontAwesomeIcons.vk,
            glowColor: const Color(0xFF4C75A3),
            onTap: () => controller.connectVK(),
            isHighlighted: homeState.highlightBubbles,
            isLoading: homeState.connectingProvider == 'vk',
            isEnabled: !isLoading && homeState.connectingProvider == null,
          ),
      ],
    );
  }

  Widget _buildAuthButtons(BuildContext context, HomeController controller, AppEventBusState eventState, HomeState homeState, bool isLoading) {
    final user = eventState.userData;
    final buttons = <Widget>[];

    if (!(user?.isAppleLinked ?? false)) {
      buttons.add(HomeAuthButton(
        icon: FontAwesomeIcons.apple,
        gradient: const LinearGradient(colors: [Color(0xFF4A4A4A), Color(0xFF2A2A2A)]),
        glowColor: Colors.grey[400]!,
        title: AppLocalizations.of(context)!.homeFreeSubscription,
        onTap: () => controller.signInWithApple(),
        isHighlighted: homeState.highlightSocials,
        isLoading: homeState.connectingProvider == 'apple',
        isEnabled: !isLoading && homeState.connectingProvider == null,
      ));
    }
    if (!(user?.isTelegramLinked ?? false)) {
      buttons.add(HomeAuthButton(
        icon: FontAwesomeIcons.telegram,
        gradient: const LinearGradient(colors: [Color(0xFF1E88E5), Color(0xFF0D47A1)]),
        glowColor: const Color(0xFF2AABEE),
        title: AppLocalizations.of(context)!.homeConnectTelegram,
        onTap: () => controller.connectTelegram(),
        isHighlighted: homeState.highlightSocials || homeState.highlightBubbles,
        isLoading: homeState.connectingProvider == 'telegram',
        isEnabled: !isLoading && homeState.connectingProvider == null,
      ));
    }
    if (!(user?.isVkLinked ?? false)) {
      buttons.add(HomeAuthButton(
        icon: FontAwesomeIcons.vk,
        gradient: const LinearGradient(colors: [Color(0xFF4C75A3), Color(0xFF2D4F7A)]),
        glowColor: const Color(0xFF4C75A3),
        title: AppLocalizations.of(context)!.homeConnectVK,
        onTap: () => controller.connectVK(),
        isHighlighted: homeState.highlightSocials || homeState.highlightBubbles,
        isLoading: homeState.connectingProvider == 'vk',
        isEnabled: !isLoading && homeState.connectingProvider == null,
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

  Widget _buildStatusText(AppEventBusState eventState, bool isRunning, bool isLoading) {
    final isUpdatingSubscription = eventState.isUpdatingSubscription;

    // While a subscription update is in progress, always show the loading
    // status regardless of the actual VPN connected/disconnected state.
    String text;
    Color textColor;

    if (isUpdatingSubscription) {
      text = AppLocalizations.of(context)!.homeConnecting;
      textColor = const Color(0xFFFFC107);
    } else if (eventState.vpnLoading && isRunning) {
      text = AppLocalizations.of(context)!.homeCheckingGoogleConnectivity;
      textColor = const Color(0xFFFFC107);
    } else {
      text = isRunning ? AppLocalizations.of(context)!.homeConnected : AppLocalizations.of(context)!.homeTapToConnect;
      if (isLoading) {
        text = isRunning ? AppLocalizations.of(context)!.homeDisconnecting : AppLocalizations.of(context)!.homeConnecting;
      }

      textColor = Colors.white.withOpacity(0.7);
      if (isRunning) textColor = const Color(0xFF00E676);
      if (isLoading) textColor = const Color(0xFFFFC107);
    }

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
}
