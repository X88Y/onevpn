import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/db/dao/config_query.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/event_bus/state.dart';
import 'package:mvmvpn/service/ping/service.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/pages/home/component/subscription_row/controller.dart';
import 'package:mvmvpn/pages/home/component/config_row/controller.dart';

import 'package:mvmvpn/pages/home/home/component/home_painters.dart';
import 'package:mvmvpn/pages/home/home/component/ambient_orbs.dart';
import 'package:mvmvpn/pages/home/home/component/home_center_button.dart';

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
              final isLoading = eventState.vpnLoading || eventState.isUpdatingSubscription || eventState.downloading;
              final accentColor = isLoading
                  ? const Color(0xFFFFD700)
                  : isRunning
                      ? const Color(0xFF00E5A0)
                      : const Color(0xFF7B61FF);
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
                                  ? [const Color(0xFF002211), const Color(0xFF050814)]
                                  : [const Color(0xFF0D0A2E), const Color(0xFF050814)],
                        ),
                      ),
                      child: child,
                    );
                  },
                  child: SafeArea(
                    child: Stack(
                      children: [
                        // Mesh grid background
                        Positioned.fill(
                          child: AnimatedBuilder(
                            animation: _particleController,
                            builder: (_, __) => CustomPaint(
                              painter: MeshGridPainter(
                                tick: _particleController.value * 100,
                                color: accentColor,
                              ),
                            ),
                          ),
                        ),
                        // Particle starfield with constellation
                        Positioned.fill(
                          child: AnimatedBuilder(
                            animation: _particleController,
                            builder: (_, __) => CustomPaint(
                              painter: HomeParticlePainter(
                                _particles,
                                _particleController.value,
                                isRunning: isRunning,
                              ),
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
                              const SizedBox(height: 10),
                              HomeCenterButton(
                                controller: controller,
                                isRunning: isRunning,
                                isLoading: isLoading || homeState.connectingProvider != null,
                                orbitController: _orbitController,
                                sonarController: _sonarController,
                                pulseAnim: _pulseAnim,
                              ),
                              const SizedBox(height: 15),
                              _buildStatusText(eventState, isRunning, isLoading),
                              const SizedBox(height: 12),
                              _buildSelectedServerInfo(context, controller, homeState),
                              const SizedBox(height: 16),
                              _buildActionButtonsRow(context, controller, eventState),
                              const SizedBox(height: 16),
                              Expanded(
                                child: _buildServerList(context, controller, homeState),
                              ),
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
    return Row(
      children: [
        IconButton(
          icon: const Icon(Icons.info_outline_rounded, color: Colors.white70),
          onPressed: () => controller.gotoNodeInfo(context),
        ),
        const Spacer(),
        IconButton(
          icon: const Icon(Icons.settings_outlined, color: Colors.white70),
          onPressed: () => controller.gotoSettings(context),
        ),
      ],
    );
  }

  Widget _buildSelectedServerInfo(BuildContext context, HomeController controller, HomeState homeState) {
    CoreConfigData? selectedConfig;
    for (final row in homeState.configs) {
      if (row is ConfigItem && row.config.id == homeState.configId) {
        selectedConfig = row.config;
        break;
      }
    }

    final name = selectedConfig?.name ?? "No Server Selected";
    final delay = (selectedConfig?.delay != null && selectedConfig!.delay != PingDelayConstants.unknown)
        ? PingService().parsePingResponse(selectedConfig.delay)
        : "";

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.04),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.dns_rounded, size: 14, color: Colors.white.withOpacity(0.5)),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500),
            ),
          ),
          if (delay.isNotEmpty) ...[
            const SizedBox(width: 8),
            Container(
              width: 4,
              height: 4,
              decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.white.withOpacity(0.3)),
            ),
            const SizedBox(width: 8),
            Text(
              delay,
              style: TextStyle(
                color: (selectedConfig!.delay > 0 && selectedConfig.delay < 300)
                    ? const Color(0xFF00E5A0)
                    : selectedConfig.delay >= 300
                        ? const Color(0xFFFFD700)
                        : Colors.redAccent,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildActionButtonsRow(BuildContext context, HomeController controller, AppEventBusState eventState) {
    return Row(
      children: [
        Expanded(
          child: Container(
            height: 46,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  const Color(0xFF7B61FF).withOpacity(0.25),
                  const Color(0xFF00B8D4).withOpacity(0.15),
                ],
              ),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFF7B61FF).withOpacity(0.35)),
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () => controller.importFromClipboard(),
                borderRadius: BorderRadius.circular(14),
                child: Center(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.content_paste_rounded, size: 16, color: Color(0xFF9E8CFF)),
                      const SizedBox(width: 8),
                      Text(
                        AppLocalizations.of(context)!.navReadPasteboard,
                        style: const TextStyle(
                          color: Color(0xFFD4CCFF),
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                          letterSpacing: 0.3,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        _iconActionButton(
          icon: Icons.speed_rounded,
          tooltip: "Ping All",
          isLoading: eventState.pinging,
          onPressed: () => controller.pingAll(),
        ),
        const SizedBox(width: 10),
        _iconActionButton(
          icon: Icons.sync_rounded,
          tooltip: "Update Subscriptions",
          isLoading: eventState.downloading,
          onPressed: () => controller.updateSubscription(),
        ),
      ],
    );
  }

  Widget _iconActionButton({
    required IconData icon,
    required String tooltip,
    required bool isLoading,
    required VoidCallback onPressed,
  }) {
    return Tooltip(
      message: tooltip,
      child: Container(
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.04),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.white.withOpacity(0.08)),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: isLoading ? null : onPressed,
            borderRadius: BorderRadius.circular(14),
            child: Center(
              child: isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                    )
                  : Icon(icon, color: Colors.white70, size: 18),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildServerList(BuildContext context, HomeController controller, HomeState homeState) {
    if (homeState.configs.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.dns_outlined, size: 40, color: Colors.white.withOpacity(0.15)),
            const SizedBox(height: 12),
            Text(
              "No servers found.\nImport a subscription URL or server configuration.",
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white.withOpacity(0.35), fontSize: 13, height: 1.4),
            ),
          ],
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF0A0C16).withOpacity(0.6),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.06)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: ListView.separated(
          padding: EdgeInsets.zero,
          itemCount: homeState.configs.length,
          separatorBuilder: (_, __) => Divider(color: Colors.white.withOpacity(0.03), height: 1),
          itemBuilder: (ctx, index) {
            final row = homeState.configs[index];
            if (row is SubscriptionItem) {
              return _buildSubscriptionRow(ctx, controller, row);
            } else if (row is ConfigItem) {
              return _buildConfigRow(ctx, controller, row, homeState.configId);
            }
            return const SizedBox.shrink();
          },
        ),
      ),
    );
  }

  Widget _buildSubscriptionRow(
    BuildContext context,
    HomeController controller,
    SubscriptionItem item,
  ) {
    final expandIcon = item.subscription.expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () async {
          final db = AppDatabase();
          if (item.subscription.id == DBConstants.defaultId) {
            await PreferencesKey().saveLocalSubscriptionExpanded(!item.subscription.expanded);
          } else {
            final row = item.subscription.copyWith(expanded: !item.subscription.expanded);
            await db.subscriptionDao.updateRow(row);
          }
          await controller.pingAll(); // Keep state refreshed
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              Icon(Icons.folder_open_rounded, size: 16, color: Colors.blueAccent.withOpacity(0.7)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  "${item.subscription.name} (${item.count})",
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                ),
              ),
              if (item.subscription.id > DBConstants.defaultId)
                IconMenuPicker(
                  icon: Icons.more_vert_rounded,
                  menus: const [
                    IconMenuId.refresh,
                    IconMenuId.share,
                    IconMenuId.edit,
                    IconMenuId.delete,
                    IconMenuId.clean,
                  ],
                  callback: (menuId) => SubscriptionRowController().moreAction(context, item.subscription, menuId),
                )
              else
                IconMenuPicker(
                  icon: Icons.more_vert_rounded,
                  menus: const [IconMenuId.clean],
                  callback: (menuId) => SubscriptionRowController().moreAction(context, item.subscription, menuId),
                ),
              Icon(expandIcon, color: Colors.white30, size: 18),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildConfigRow(
    BuildContext context,
    HomeController controller,
    ConfigItem item,
    int selectedConfigId,
  ) {
    final data = item.config;
    final isSelected = data.id == selectedConfigId;
    final runningId = AppEventBus.instance.state.runningId;
    final isRunning = data.id == runningId;

    Color statusBg = Colors.transparent;
    Color nameColor = Colors.white70;
    if (isRunning) {
      statusBg = const Color(0xFF00E5A0).withOpacity(0.12);
      nameColor = const Color(0xFF00E5A0);
    } else if (isSelected) {
      statusBg = const Color(0xFF7B61FF).withOpacity(0.08);
      nameColor = const Color(0xFF9E8CFF);
    }

    final delayText = (data.delay != PingDelayConstants.unknown) ? PingService().parsePingResponse(data.delay) : "";

    return Material(
      color: statusBg,
      child: InkWell(
        onTap: () => controller.updateConfigId(context, data.id),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
          child: Row(
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isRunning
                      ? const Color(0xFF00E5A0)
                      : isSelected
                          ? const Color(0xFF7B61FF)
                          : Colors.transparent,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  data.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: nameColor,
                    fontSize: 12.5,
                    fontWeight: isSelected || isRunning ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
              ),
              if (delayText.isNotEmpty) ...[
                const SizedBox(width: 8),
                Text(
                  delayText,
                  style: TextStyle(
                    color: (data.delay > 0 && data.delay < 300)
                        ? const Color(0xFF00E5A0)
                        : data.delay >= 300
                            ? const Color(0xFFFFD700)
                            : Colors.redAccent,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              const SizedBox(width: 8),
              IconMenuPicker(
                icon: Icons.more_vert_rounded,
                menus: const [
                  IconMenuId.edit,
                  IconMenuId.share,
                  IconMenuId.copy,
                  IconMenuId.delete,
                ],
                callback: (menuId) => ConfigRowController().moreAction(context, data, menuId),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatusText(AppEventBusState eventState, bool isRunning, bool isLoading) {
    final isUpdatingSubscription = eventState.isUpdatingSubscription;

    String text;
    Color textColor;

    if (isUpdatingSubscription) {
      text = AppLocalizations.of(context)!.mainConnecting;
      textColor = const Color(0xFFFFD700);
    } else if (eventState.vpnLoading && isRunning) {
      text = AppLocalizations.of(context)!.mainCheckingGoogleConnectivity;
      textColor = const Color(0xFFFFD700);
    } else {
      text = isRunning ? AppLocalizations.of(context)!.mainConnected : AppLocalizations.of(context)!.mainTapToConnect;
      if (isLoading) {
        text = isRunning ? AppLocalizations.of(context)!.mainDisconnecting : AppLocalizations.of(context)!.mainConnecting;
      }

      textColor = Colors.white.withOpacity(0.7);
      if (isRunning) textColor = const Color(0xFF00E5A0);
      if (isLoading) textColor = const Color(0xFFFFD700);
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 40,
          height: 2,
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [Colors.transparent, textColor.withOpacity(0.5), Colors.transparent],
            ),
            borderRadius: BorderRadius.circular(1),
          ),
        ),
        AnimatedDefaultTextStyle(
          duration: const Duration(milliseconds: 400),
          style: TextStyle(
            color: textColor,
            fontSize: 15,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.5,
            shadows: [
              Shadow(
                color: textColor.withOpacity(0.4),
                blurRadius: 12,
              ),
            ],
          ),
          child: Text(text.toUpperCase()),
        ),
      ],
    );
  }
}
