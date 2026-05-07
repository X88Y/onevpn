import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
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

class _HomePageState extends State<HomePage> with SingleTickerProviderStateMixin {
  late final TabController _tabController = TabController(length: 2, vsync: this);

  @override
  void dispose() {
    _tabController.dispose();
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
            builder: (context, eventState) => Scaffold(
              backgroundColor: const Color(0xFF0F0F0F),
              body: SafeArea(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                  child: Column(
                    children: [
                      _socialBubbles(context, eventState),
                      const SizedBox(height: 16),
                      _authButtons(context, controller, eventState),
                      const Spacer(),
                      _centerButton(context, controller, eventState),
                      const SizedBox(height: 32),
                      _statusText(eventState),
                      const Spacer(),
                      _subscriptionPill(context, eventState, homeState),
                      const SizedBox(height: 20),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _socialBubbles(BuildContext context, AppEventBusState eventState) {
    final user = eventState.userData;
    final controller = context.read<HomeController>();

    final bubbles = <Widget>[];
    if (user?.isAppleLinked ?? false) {
      bubbles.add(_socialBubble(
        icon: Icons.apple,
        isConnected: true,
        glowColor: Colors.grey[400]!,
        onTap: () => controller.signInWithApple(),
      ));
    }
    if (user?.isTelegramLinked ?? false) {
      bubbles.add(_socialBubble(
        icon: Icons.send,
        isConnected: true,
        glowColor: Colors.blue[400]!,
        onTap: () => controller.connectTelegram(),
      ));
    }
    if (user?.isVkLinked ?? false) {
      bubbles.add(_socialBubble(
        icon: Icons.chat_bubble_outline,
        isConnected: true,
        glowColor: const Color(0xFF4C75A3),
        onTap: () => controller.connectVK(),
      ));
    }

    if (bubbles.isEmpty) return const SizedBox.shrink();

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var i = 0; i < bubbles.length; i++) ...[
          bubbles[i],
          if (i < bubbles.length - 1) const SizedBox(width: 16),
        ],
      ],
    );
  }

  Widget _authButtons(BuildContext context, HomeController controller, AppEventBusState eventState) {
    final user = eventState.userData;
    final buttons = <Widget>[];

    if (!(user?.isAppleLinked ?? false)) {
      buttons.add(_authButton(
        icon: Icons.apple,
        iconBgColor: Colors.grey[800]!,
        title: 'FREE one-click subscription',
        onTap: () => controller.signInWithApple(),
      ));
    }
    if (!(user?.isTelegramLinked ?? false)) {
      buttons.add(_authButton(
        icon: Icons.send,
        iconBgColor: Colors.blue[700]!,
        title: 'Connect Telegram',
        onTap: () => controller.connectTelegram(),
      ));
    }
    if (!(user?.isVkLinked ?? false)) {
      buttons.add(_authButton(
        icon: Icons.chat_bubble_outline,
        iconBgColor: const Color(0xFF4C75A3),
        title: 'Connect VK',
        onTap: () => controller.connectVK(),
      ));
    }

    if (buttons.isEmpty) return const SizedBox.shrink();

    return Column(
      children: [
        for (var i = 0; i < buttons.length; i++) ...[
          buttons[i],
          if (i < buttons.length - 1) const SizedBox(height: 12),
        ],
      ],
    );
  }

  Widget _authButton({
    required IconData icon,
    required Color iconBgColor,
    required String title,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withOpacity(0.05)),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: iconBgColor,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: Colors.white, size: 28),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Icon(
              Icons.chevron_right,
              color: Colors.white.withOpacity(0.3),
              size: 24,
            ),
          ],
        ),
      ),
    );
  }

  Widget _socialBubble({
    required IconData icon,
    required bool isConnected,
    required Color glowColor,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        width: 54,
        height: 54,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isConnected ? Colors.white.withOpacity(0.15) : Colors.white.withOpacity(0.05),
          border: Border.all(
            color: isConnected ? Colors.white.withOpacity(0.2) : Colors.white.withOpacity(0.05),
            width: 1,
          ),
          boxShadow: isConnected
              ? [
                  BoxShadow(
                    color: glowColor.withOpacity(0.4),
                    blurRadius: 15,
                    spreadRadius: 2,
                  ),
                ]
              : [],
        ),
        child: Icon(
          icon,
          color: isConnected ? Colors.white : Colors.white.withOpacity(0.3),
          size: 26,
        ),
      ),
    );
  }

  Widget _centerButton(BuildContext context, HomeController controller, AppEventBusState eventState) {
    final isRunning = eventState.runningId != DBConstants.defaultId;
    return GestureDetector(
      onTap: () => controller.startVpn(context),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: 220,
            height: 220,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF5D5FEF).withOpacity(isRunning ? 0.6 : 0.3),
                  blurRadius: 80,
                  spreadRadius: 20,
                ),
              ],
            ),
          ),
          Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF4C4D9A),
            ),
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: SvgPicture.asset(
                'assets/app_icon/app_icon.svg',
                fit: BoxFit.contain,
                colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusText(AppEventBusState eventState) {
    final isRunning = eventState.runningId != DBConstants.defaultId;
    return Text(
      isRunning ? 'Connected' : 'Tap to connect',
      style: const TextStyle(
        color: Colors.white,
        fontSize: 18,
        fontWeight: FontWeight.w500,
      ),
    );
  }

  Widget _subscriptionPill(
    BuildContext context,
    AppEventBusState eventState,
    HomeState homeState,
  ) {
    final isRunning = eventState.runningId != DBConstants.defaultId;
    final user = eventState.userData;
    final hasActiveSubscription = user?.hasActiveSubscription ?? false;
    final subscriptionEndsAt = user?.subscriptionEndsAt;

    if (isRunning || hasActiveSubscription) {
      final statusText = hasActiveSubscription && subscriptionEndsAt != null
          ? 'Subscription active until ${subscriptionEndsAt.day.toString().padLeft(2, '0')}.${subscriptionEndsAt.month.toString().padLeft(2, '0')}.${subscriptionEndsAt.year}'
          : 'Subscription active';
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        decoration: BoxDecoration(
          color: Colors.green.withOpacity(0.1),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.green.withOpacity(0.2)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_circle, color: Colors.green, size: 20),
            const SizedBox(width: 12),
            Flexible(
              child: Text(
                statusText,
                style: const TextStyle(
                  color: Colors.green,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
                overflow: TextOverflow.visible,
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.info_outline,
            color: Colors.white.withOpacity(0.4),
            size: 20,
          ),
          const SizedBox(width: 12),
          Text(
            'No active subscription',
            style: TextStyle(
              color: Colors.white.withOpacity(0.4),
              fontSize: 16,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
