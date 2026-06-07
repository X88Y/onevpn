import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/db/dao/config_query.dart';
import 'package:mvmvpn/core/db/database/enum.dart';
import 'package:mvmvpn/core/network/model.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/xray/outbound/params.dart';
import 'package:mvmvpn/pages/home/xray/raw/params.dart';
import 'package:mvmvpn/pages/main/url.dart';
import 'package:mvmvpn/pages/mixin/alert.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/service/background_task/service.dart';
import 'package:mvmvpn/service/share/service.dart';
import 'package:mvmvpn/service/toast/service.dart';
import 'package:mvmvpn/service/auth/service.dart';
import 'package:mvmvpn/service/vpn/service.dart';
import 'package:mvmvpn/service/xray/outbound/state.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/ping/service.dart';
import 'package:mvmvpn/service/subscription/service.dart';
import 'package:mvmvpn/core/pigeon/constants.dart';
import 'package:mvmvpn/core/tools/file.dart';
import 'package:mvmvpn/gen/assets.gen.dart';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class HomeState {
  final int configId;
  final DateTime? subscriptionEndsAt;
  final bool highlightSocials;
  final bool highlightBubbles;
  final String? connectingProvider;
  final List<ConfigQueryRow> configs;

  const HomeState({
    required this.configId,
    this.subscriptionEndsAt,
    this.highlightSocials = false,
    this.highlightBubbles = false,
    this.connectingProvider,
    this.configs = const [],
  });

  factory HomeState.initial() =>
      const HomeState(configId: DBConstants.defaultId);

  HomeState copyWith({
    int? configId,
    DateTime? subscriptionEndsAt,
    bool clearSubscriptionEndsAt = false,
    bool? highlightSocials,
    bool? highlightBubbles,
    String? connectingProvider,
    bool clearConnectingProvider = false,
    List<ConfigQueryRow>? configs,
  }) {
    return HomeState(
      configId: configId ?? this.configId,
      subscriptionEndsAt: clearSubscriptionEndsAt
          ? null
          : (subscriptionEndsAt ?? this.subscriptionEndsAt),
      highlightSocials: highlightSocials ?? this.highlightSocials,
      highlightBubbles: highlightBubbles ?? this.highlightBubbles,
      connectingProvider: clearConnectingProvider
          ? null
          : (connectingProvider ?? this.connectingProvider),
      configs: configs ?? this.configs,
    );
  }
}

class HomeController extends Cubit<HomeState> {
  final BuildContext context;
  final TabController tabController;

  HomeController(this.context, this.tabController) : super(HomeState.initial()) {
    _asyncInit();
  }

  late final StreamSubscription<void> _toastSubscription;
  StreamSubscription<List<ConfigQueryRow>>? _configsSubscription;

  Future<void> _asyncInit() async {
    _initToastStream();
    final id = await PreferencesKey().readLastConfigId();
    emit(state.copyWith(configId: id));

    final db = AppDatabase();
    _configsSubscription = db.coreConfigDao.allConfigsStream().listen((data) {
      emit(state.copyWith(configs: data));
    });

    await BackgroundTaskService().checkSubscriptionUpdate();
  }

  void _initToastStream() {
    _toastSubscription = ToastService().toastBroadcast.stream.listen(
      (message) => _showToast(message),
    );
  }

  void _showToast(String message) {
    if (context.mounted) {
      ContextAlert.showToast(context, message);
    }
  }

  void gotoSettings(BuildContext context) {
    context.push(RouterPath.setting);
  }

  Future<void> addMenuAction(BuildContext context, String menuId) async {
    final id = IconMenuId.fromString(menuId);
    if (id == null) {
      return;
    }
    switch (id) {
      case IconMenuId.manualInput:
        _addConfig(context);
        break;
      case IconMenuId.subscribeLink:
        _addSubscription(context);
        break;
      case IconMenuId.pickFile:
        await ShareService().pickFile();
        break;
      case IconMenuId.readPasteboard:
        await ShareService().readPasteboard();
        break;
      default:
        break;
    }
  }

  void _addConfig(BuildContext context) {
    switch (tabController.index) {
      case 0:
        final params = OutboundUIParams(
          DBConstants.defaultId,
          OutboundState(),
          [],
        );
        context.push(RouterPath.outboundUI, extra: params);
        break;
      case 1:
        final params = XrayRawParams(DBConstants.defaultId);
        context.push(RouterPath.xrayRaw, extra: params);
        break;
    }
  }

  void _addSubscription(BuildContext context) {
    context.push(RouterPath.subscriptionAdd);
  }

  String formatGeoLocation(BuildContext context, GeoLocation location) {
    var text = "";
    text += AppLocalizations.of(context)!.nodeInfoScreenDuration;
    if (location.duration == null) {
      text += ": ${AppLocalizations.of(context)!.nodeInfoScreenFetching} ";
    } else {
      text += ": ${location.duration} ";
    }
    text += AppLocalizations.of(context)!.nodeInfoScreenDelay;
    if (location.delay == null) {
      text += ": ${AppLocalizations.of(context)!.nodeInfoScreenFetching} ";
    } else {
      text += ": ${location.delay}ms ";
    }
    text += AppLocalizations.of(context)!.nodeInfoScreenLocation;
    if (location.country == null) {
      text += ": ${AppLocalizations.of(context)!.nodeInfoScreenFetching} ";
    } else {
      text += ": ${location.country} ";
    }
    return text;
  }

  void gotoNodeInfo(BuildContext context) {
    context.push(RouterPath.nodeInfo);
  }

  void updateConfigId(BuildContext context, int value) {
    _updateConfigIdOnly(value);
  }

  void _updateConfigIdOnly(int value) {
    PreferencesKey().saveLastConfigId(value);
    emit(state.copyWith(configId: value));
  }

  Future<void> importFromClipboard() async {
    await ShareService().readPasteboard();
  }

  Future<void> pingAll(String activeTab) async {
    final db = AppDatabase();
    final subscriptions = await db.subscriptionDao.allRows;
    final allSubIds = [DBConstants.defaultId, ...subscriptions.map((s) => s.id)];
    
    final allRowsWithData = <CoreConfigData>[];
    for (final subId in allSubIds) {
      final outboundRows = await db.coreConfigDao.allOutboundRowsWithDataBySubId(subId);
      final rawRows = await db.coreConfigDao.allRawRowsWithDataBySubId(subId);
      allRowsWithData.addAll(outboundRows);
      allRowsWithData.addAll(rawRows);
    }

    final isWifiTab = activeTab == 'wifi';
    bool matchesTab(String name) {
      final nameLower = name.toLowerCase();
      final hasLte = nameLower.contains('lte');
      if (isWifiTab) {
        return !hasLte;
      }
      return hasLte;
    }

    final configsToPing = allRowsWithData
        .where((config) => matchesTab(config.name))
        .toList();

    if (configsToPing.isNotEmpty) {
      await PingService().pingConfigs(
        configsToPing,
        pingCount: activeTab == 'lte' ? 10 : 1,
      );
    }
  }

  Future<void> updateSubscription() async {
    await SubscriptionService().refreshAllSubscription();
  }

  Future<void> startVpn(BuildContext context) async {
    final eventBus = AppEventBus.instance;
    final isRunning = eventBus.state.runningId != DBConstants.defaultId;
    if (eventBus.state.isUpdatingSubscription) return;
    if (eventBus.state.vpnLoading && !isRunning) return;

    eventBus.updateVpnLoading(true);

    try {
      if (isRunning) {
        await VpnService().startVpn(eventBus.state.runningId);
        return;
      }

      int targetConfigId = state.configId;
      final db = AppDatabase();

      if (targetConfigId != DBConstants.defaultId) {
        final configExists = await db.coreConfigDao.searchRow(targetConfigId);
        if (configExists == null) {
          targetConfigId = DBConstants.defaultId;
          _updateConfigIdOnly(DBConstants.defaultId);
        }
      }

      if (targetConfigId == DBConstants.defaultId) {
        final configs = await db.select(db.coreConfig).get();
        final serverConfigs = configs.where((c) => c.type == CoreConfigType.outbound.name || c.type == CoreConfigType.raw.name).toList();

        if (serverConfigs.isEmpty) {
          eventBus.updateVpnLoading(false);
          if (context.mounted) {
            ContextAlert.showToast(
              context,
              AppLocalizations.of(context)!.appVpnSelectOneConfig,
            );
          }
          return;
        }

        // 1. Wifi servers (name does not contain 'lte' case-insensitively)
        final wifiServers = serverConfigs
            .where((c) => !c.name.toLowerCase().contains('lte'))
            .toList();

        CoreConfigData? bestWifiServer;
        if (wifiServers.isNotEmpty) {
          await PingService().pingConfigs(wifiServers);

          final updatedConfigs = await db.select(db.coreConfig).get();
          final updatedWifiServers = updatedConfigs
              .where((c) => (c.type == CoreConfigType.outbound.name || c.type == CoreConfigType.raw.name) &&
                            !c.name.toLowerCase().contains('lte'))
              .toList();

          final availableWifi = updatedWifiServers
              .where((c) => c.delay < PingDelayConstants.unknown)
              .toList()
            ..sort((a, b) => a.delay.compareTo(b.delay));

          if (availableWifi.isNotEmpty) {
            bestWifiServer = availableWifi.first;
          }
        }

        if (bestWifiServer != null) {
          targetConfigId = bestWifiServer.id;
          _updateConfigIdOnly(targetConfigId);
        } else {
          // 2. LTE servers (name contains 'lte' case-insensitively)
          final lteServers = serverConfigs
              .where((c) => c.name.toLowerCase().contains('lte'))
              .toList();

          CoreConfigData? bestLteServer;
          if (lteServers.isNotEmpty) {
            await PingService().pingConfigs(lteServers);

            final updatedConfigs = await db.select(db.coreConfig).get();
            final updatedLteServers = updatedConfigs
                .where((c) => (c.type == CoreConfigType.outbound.name || c.type == CoreConfigType.raw.name) &&
                              c.name.toLowerCase().contains('lte'))
                .toList();

            final availableLte = updatedLteServers
                .where((c) => c.delay < PingDelayConstants.unknown)
                .toList()
              ..sort((a, b) => a.delay.compareTo(b.delay));

            if (availableLte.isNotEmpty) {
              bestLteServer = availableLte.first;
            }
          }

          if (bestLteServer != null) {
            targetConfigId = bestLteServer.id;
            _updateConfigIdOnly(targetConfigId);
          } else {
            // 3. If no match server show error
            eventBus.updateVpnLoading(false);
            if (context.mounted) {
              ContextAlert.showToast(
                context,
                AppLocalizations.of(context)!.appVpnSelectOneConfig,
              );
            }
            return;
          }
        }
      }

      final permission = await VpnService().checkPermission();
      if (!permission) {
        eventBus.updateVpnLoading(false);
        if (context.mounted) {
          ContextAlert.showPermissionDialog(context);
        }
        return;
      }
      await VpnService().startVpn(targetConfigId);
    } catch (e) {
      eventBus.updateVpnLoading(false);
      rethrow;
    }
  }

  Future<void> clearAllData({String redirectTo = RouterPath.privacy}) async {
    final prefs = SharedPreferencesAsync();
    await prefs.clear();
    await AuthService().signOut();

    // Clear databases
    final db = AppDatabase();
    await db.geoDataDao.clear();
    await db.coreConfigDao.clear();
    await db.subscriptionDao.clear();

    // Re-copy default assets
    final datPath = VpnConstants.datDir;
    await FileTool.deleteDirIfExists(datPath);
    await FileTool.checkDir(datPath);
    await FileTool.copyAssets(Assets.dat.values, datPath);

    emit(HomeState.initial());
    if (context.mounted) {
      context.go(redirectTo);
    }
  }

  Future<void> regenerateTokenForce() async {
    final newId = await VpnService().regenerateTokenForce();
    if (newId != null) {
      _updateConfigIdOnly(newId);
    }
  }

  void openUrl(String url) {
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }

  @override
  Future<void> close() {
    _toastSubscription.cancel();
    _configsSubscription?.cancel();
    return super.close();
  }
}
