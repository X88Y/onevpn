import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/pages/main/url.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/db/dao/config_query.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/event_bus/state.dart';
import 'package:mvmvpn/service/ping/service.dart';

import 'package:mvmvpn/pages/home/home/component/home_painters.dart';
import 'package:mvmvpn/pages/home/home/component/ambient_orbs.dart';
import 'package:mvmvpn/pages/home/home/component/home_center_button.dart';
import 'package:mvmvpn/pages/home/home/component/account_bubble.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with TickerProviderStateMixin {
  String _activeTab = 'all';
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
                    bottom: false,
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
                        Column(
                          children: [
                            Padding(
                              padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
                              child: _buildTopBar(context, controller, eventState, homeState, isLoading),
                            ),
                            const Spacer(flex: 1),
                            HomeCenterButton(
                              controller: controller,
                              isRunning: isRunning,
                              isLoading: isLoading || homeState.connectingProvider != null,
                              orbitController: _orbitController,
                              sonarController: _sonarController,
                              pulseAnim: _pulseAnim,
                            ),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 24),
                              child: _buildStatusText(eventState, isRunning, isLoading),
                            ),
                            const Spacer(flex: 1),
                            Expanded(
                              flex: 18,
                              child: Container(
                                decoration: BoxDecoration(
                                  color: const Color(0xFF0F0F12),
                                  borderRadius: const BorderRadius.only(
                                    topLeft: Radius.circular(30),
                                    topRight: Radius.circular(30),
                                  ),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withOpacity(0.4),
                                      blurRadius: 20,
                                      offset: const Offset(0, -6),
                                    ),
                                  ],
                                ),
                                child: ClipRRect(
                                  borderRadius: const BorderRadius.only(
                                    topLeft: Radius.circular(30),
                                    topRight: Radius.circular(30),
                                  ),
                                  child: Column(
                                    children: [
                                      Padding(
                                        padding: const EdgeInsets.fromLTRB(24, 20, 24, 12),
                                        child: _buildListHeader(context, controller, eventState, homeState),
                                      ),
                                      Divider(color: Colors.white.withOpacity(0.05), height: 1),
                                      Expanded(
                                        child: _buildServerList(context, controller, homeState),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ],
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
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        const Text(
          "🇷🇺 Freedom",
          style: TextStyle(
            color: Colors.white,
            fontSize: 24,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.5,
          ),
        ),
        AccountBubble(
          controller: controller,
          isLoading: isLoading,
        ),
      ],
    );
  }

  String _getServersTitle(BuildContext context) {
    final locale = Localizations.localeOf(context).languageCode;
    if (locale == 'ru') return 'Серверы';
    if (locale == 'zh') return '服务器';
    if (locale == 'fa') return 'سرورها';
    return 'Servers';
  }

  List<ConfigQueryRow> _getFilteredConfigs(List<ConfigQueryRow> configs) {
    final results = <ConfigQueryRow>[];
    final isAllTab = _activeTab == 'all';

    bool matchesTab(String name) {
      if (isAllTab) return true;
      final nameLower = name.toLowerCase();
      final hasLte = nameLower.contains('lte');
      return hasLte;
    }

    final subItems = <int, SubscriptionItem>{};
    final allConfigItems = <int, List<ConfigItem>>{};

    for (final row in configs) {
      if (row is SubscriptionItem) {
        subItems[row.subscription.id] = row;
        allConfigItems[row.subscription.id] = [];
      } else if (row is ConfigItem) {
        final subId = row.config.subId;
        allConfigItems.putIfAbsent(subId, () => []).add(row);
      }
    }

    for (final subId in subItems.keys) {
      final subRow = subItems[subId]!;
      final configsInSub = allConfigItems[subId] ?? [];
      final matchingConfigs = configsInSub.where((c) => matchesTab(c.config.name)).toList();

      if (matchingConfigs.isEmpty && subId != DBConstants.defaultId) {
        continue;
      }

      final newSubItem = SubscriptionItem(
        subRow.subscription.copyWith(count: matchingConfigs.length),
        ConfigQueryRowType.subscription,
      )..count = matchingConfigs.length;

      if (subRow.subscription.name == "Основная подписка") {
        results.addAll(matchingConfigs);
      } else {
        results.add(newSubItem);
        if (subRow.subscription.expanded) {
          results.addAll(matchingConfigs);
        }
      }
    }
    return results;
  }

  String _getTabAllTitle(BuildContext context) {
    final locale = Localizations.localeOf(context).languageCode;
    if (locale == 'ru') return 'Все';
    if (locale == 'zh') return '全部';
    if (locale == 'fa') return 'همه';
    return 'All';
  }

  Widget _buildListHeader(BuildContext context, HomeController controller, AppEventBusState eventState, HomeState homeState) {
    final title = _getServersTitle(context);
    final isAll = _activeTab == 'all';

    return Padding(
      padding: const EdgeInsets.only(bottom: 0),
      child: Row(
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: 16),
          GestureDetector(
            onTap: () {
              setState(() {
                _activeTab = 'all';
              });
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                color: isAll ? const Color(0xFF00B4A2) : Colors.white.withOpacity(0.06),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                _getTabAllTitle(context),
                style: TextStyle(
                  color: isAll ? Colors.white : Colors.white.withOpacity(0.4),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () {
              setState(() {
                _activeTab = 'lte';
              });
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                color: !isAll ? const Color(0xFF00B4A2) : Colors.white.withOpacity(0.06),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                "LTE",
                style: TextStyle(
                  color: !isAll ? Colors.white : Colors.white.withOpacity(0.4),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          const Spacer(),
          _circularIconButton(
            icon: Icons.report_problem_rounded,
            color: Colors.redAccent.withOpacity(0.12),
            iconColor: Colors.redAccent,
            onPressed: () {
              context.push(RouterPath.log);
            },
          ),
          const SizedBox(width: 8),
          _circularIconButton(
            icon: Icons.sync_rounded,
            color: Colors.white.withOpacity(0.06),
            iconColor: Colors.white.withOpacity(0.6),
            isLoading: eventState.downloading,
            onPressed: () => controller.updateSubscription(),
          ),
          const SizedBox(width: 8),
          _circularIconButton(
            icon: Icons.access_time_rounded,
            color: Colors.white.withOpacity(0.06),
            iconColor: Colors.white.withOpacity(0.6),
            isLoading: eventState.pinging,
            onPressed: () => controller.pingAll(),
          ),
        ],
      ),
    );
  }

  Widget _circularIconButton({
    required IconData icon,
    required Color color,
    required Color iconColor,
    required VoidCallback onPressed,
    bool isLoading = false,
  }) {
    return Container(
      width: 38,
      height: 38,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: isLoading ? null : onPressed,
          borderRadius: BorderRadius.circular(10),
          child: Center(
            child: isLoading
                ? SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(iconColor),
                    ),
                  )
                : Icon(
                    icon,
                    color: iconColor,
                    size: 18,
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

    final filteredConfigs = _getFilteredConfigs(homeState.configs);

    if (filteredConfigs.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.dns_outlined, size: 40, color: Colors.white.withOpacity(0.15)),
            const SizedBox(height: 12),
            Text(
              _activeTab == 'all' ? "No servers found." : "No LTE servers found.",
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white.withOpacity(0.35), fontSize: 13, height: 1.4),
            ),
          ],
        ),
      );
    }

    return ListView.separated(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).padding.bottom + 24,
      ),
      itemCount: filteredConfigs.length,
      separatorBuilder: (_, __) => Divider(color: Colors.white.withOpacity(0.04), height: 1),
      itemBuilder: (ctx, index) {
        final row = filteredConfigs[index];
        if (row is SubscriptionItem) {
          return _buildSubscriptionRow(ctx, controller, row);
        } else if (row is ConfigItem) {
          return _buildConfigRow(ctx, controller, row, homeState.configId);
        }
        return const SizedBox.shrink();
      },
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
              Icon(expandIcon, color: Colors.white30, size: 18),
            ],
          ),
        ),
      ),
    );
  }

  _EmojiParseResult _parseConfigEmojiAndName(String name) {
    if (name.isEmpty) {
      return _EmojiParseResult(getFlagEmoji(name), name);
    }

    final runes = name.runes.toList();
    final firstRune = runes.first;

    // Check if it's a regional indicator (flag)
    if (firstRune >= 0x1F1E6 && firstRune <= 0x1F1FF) {
      if (runes.length >= 2 && runes[1] >= 0x1F1E6 && runes[1] <= 0x1F1FF) {
        final emoji = String.fromCharCodes([firstRune, runes[1]]);
        final parsedName = String.fromCharCodes(runes.sublist(2)).trim().replaceFirst(RegExp(r'^[-_\s]+'), '');
        return _EmojiParseResult(emoji, parsedName);
      }
    }

    // Check if it's a standard emoji
    if ((firstRune >= 0x1F300 && firstRune <= 0x1F9FF) ||
        (firstRune >= 0x1F600 && firstRune <= 0x1F64F) ||
        (firstRune >= 0x1F680 && firstRune <= 0x1F6FF) ||
        (firstRune >= 0x2600 && firstRune <= 0x27BF) ||
        (firstRune >= 0x1F900 && firstRune <= 0x1F9FF) ||
        (firstRune >= 0x1FA70 && firstRune <= 0x1FAFF)) {
      int endIdx = 1;
      while (endIdx < runes.length) {
        final nextRune = runes[endIdx];
        if (nextRune == 0xFE0F || nextRune == 0x200D || (nextRune >= 0x1F3FB && nextRune <= 0x1F3FF)) {
          endIdx++;
          if (nextRune == 0x200D && endIdx < runes.length) {
            endIdx++;
          }
        } else {
          break;
        }
      }
      final emoji = String.fromCharCodes(runes.sublist(0, endIdx));
      final parsedName = String.fromCharCodes(runes.sublist(endIdx)).trim().replaceFirst(RegExp(r'^[-_\s]+'), '');
      return _EmojiParseResult(emoji, parsedName);
    }

    return _EmojiParseResult(getFlagEmoji(name), name);
  }

  String getFlagEmoji(String name) {
    final nameLower = name.toLowerCase();
    if (nameLower.contains('германия') || nameLower.contains('germany')) {
      return '🇩🇪';
    }
    if (nameLower.contains('швеция') || nameLower.contains('sweden')) {
      return '🇸🇪';
    }
    if (nameLower.contains('финляндия') || nameLower.contains('finland') || nameLower.contains('lte авто') || nameLower.contains('lte auto')) {
      return '🇫🇮';
    }
    if (nameLower.contains('эстония') || nameLower.contains('estonia')) {
      return '🇪🇪';
    }
    if (nameLower.contains('польша') || nameLower.contains('poland')) {
      return '🇵🇱';
    }
    return '🌐';
  }

  String getProtocolAndNetworkText(String tags, String defaultType) {
    if (tags.isEmpty) {
      return "${defaultType.toUpperCase()} | TCP";
    }
    final parts = tags.split(',');
    if (parts.length >= 2) {
      return "${parts[0].toUpperCase()} | ${parts[1].toUpperCase()}";
    }
    return "${parts[0].toUpperCase()} | TCP";
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
    if (isRunning) {
      statusBg = const Color(0xFF00E5A0).withOpacity(0.08);
    } else if (isSelected) {
      statusBg = Colors.white.withOpacity(0.04);
    }

    final delayText = (data.delay != PingDelayConstants.unknown) ? PingService().parsePingResponse(data.delay) : "";
    final parsed = _parseConfigEmojiAndName(data.name);

    return Material(
      color: statusBg,
      child: InkWell(
        onTap: () => controller.updateConfigId(context, data.id),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          child: Row(
            children: [
              Text(
                parsed.emoji,
                style: const TextStyle(fontSize: 24),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      parsed.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: isRunning
                            ? const Color(0xFF00E5A0)
                            : isSelected
                                ? Colors.white
                                : Colors.white.withOpacity(0.85),
                        fontSize: 14,
                        fontWeight: isSelected || isRunning ? FontWeight.w600 : FontWeight.normal,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      getProtocolAndNetworkText(data.tags, data.type),
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.4),
                        fontSize: 11,
                      ),
                    ),
                  ],
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

class _EmojiParseResult {
  final String emoji;
  final String name;

  _EmojiParseResult(this.emoji, this.name);
}
