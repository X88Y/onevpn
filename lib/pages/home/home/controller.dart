import 'dart:async';
import 'package:mvmvpn/core/tools/logger.dart';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
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
import 'package:mvmvpn/service/auth/model.dart';
import 'package:mvmvpn/service/auth/service.dart';
import 'package:mvmvpn/service/vpn/service.dart';
import 'package:mvmvpn/service/xray/outbound/state.dart';
import 'package:mvmvpn/service/event_bus/service.dart';

import 'package:mvmvpn/core/network/client.dart';
import 'package:mvmvpn/core/pigeon/flutter_api.dart';
import 'package:mvmvpn/core/pigeon/messages.g.dart';
import 'package:mvmvpn/core/pigeon/model_reader.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class HomeState {
  final int configId;
  final DateTime? subscriptionEndsAt;
  final bool highlightSocials;
  final bool highlightBubbles;
  final String? connectingProvider;

  const HomeState({
    required this.configId,
    this.subscriptionEndsAt,
    this.highlightSocials = false,
    this.highlightBubbles = false,
    this.connectingProvider,
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
  Timer? _userUpdateTimer;

  Future<void> _asyncInit() async {
    _initToastStream();
    final id = await PreferencesKey().readLastConfigId();
    emit(state.copyWith(configId: id));
    await BackgroundTaskService().checkSubscriptionUpdate();

    _startUserUpdateTimer();
  }

  void _startUserUpdateTimer() {
    _userUpdateTimer = Timer.periodic(const Duration(seconds: 3), (timer) {
      _updateUserData();
    });
  }

  Future<void> _updateUserData() async {
    if (AuthService().currentUser != null) {
      final userModel = await AuthService().syncUserWithBackend();
      final subscriptionEndsAt = userModel?.subscriptionEndsAt;
      if (subscriptionEndsAt != state.subscriptionEndsAt) {
        emit(state.copyWith(
          subscriptionEndsAt: subscriptionEndsAt,
          clearSubscriptionEndsAt: subscriptionEndsAt == null,
        ));
      }
    }
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
    text += AppLocalizations.of(context)!.nodeInfoPageDuration;
    if (location.duration == null) {
      text += ": ${AppLocalizations.of(context)!.nodeInfoPageFetching} ";
    } else {
      text += ": ${location.duration} ";
    }
    text += AppLocalizations.of(context)!.nodeInfoPageDelay;
    if (location.delay == null) {
      text += ": ${AppLocalizations.of(context)!.nodeInfoPageFetching} ";
    } else {
      text += ": ${location.delay}ms ";
    }
    text += AppLocalizations.of(context)!.nodeInfoPageLocation;
    if (location.country == null) {
      text += ": ${AppLocalizations.of(context)!.nodeInfoPageFetching} ";
    } else {
      text += ": ${location.country} ";
    }
    return text;
  }

  void gotoNodeInfo(BuildContext context) {
    context.push(RouterPath.nodeInfo);
  }

  void updateConfigId(BuildContext context, int value) {
    emit(state.copyWith(configId: value));
  }

  void triggerSocialHighlight() {
    emit(state.copyWith(highlightSocials: true));
    Future.delayed(const Duration(milliseconds: 5000), () {
      if (!isClosed) {
        emit(state.copyWith(highlightSocials: false));
      }
    });
  }

  void triggerBubbleHighlight() {
    emit(state.copyWith(highlightBubbles: true));
    Future.delayed(const Duration(milliseconds: 5000), () {
      if (!isClosed) {
        emit(state.copyWith(highlightBubbles: false));
      }
    });
  }

  Future<void> startVpn(BuildContext context) async {
    final eventBus = AppEventBus.instance;
    if (eventBus.state.vpnLoading || eventBus.state.isUpdatingSubscription) return;

    final isRunning = eventBus.state.runningId != DBConstants.defaultId;
    
    eventBus.updateVpnLoading(true);

    try {
      if (isRunning) {
        await VpnService().startVpn(eventBus.state.runningId);
        return;
      }

      if (AuthService().currentUser == null) {
        eventBus.updateVpnLoading(false);
        triggerSocialHighlight();
        return;
      }

      final user = eventBus.state.userData;
      if (user != null && !user.hasActiveSubscription) {
        eventBus.updateVpnLoading(false);
        triggerBubbleHighlight();
        return;
      }

      int targetConfigId = state.configId;

      if (AuthService().currentUser != null) {
        var newConfigId = await AuthService().fetchAndSetRandomVpnKey();
        if (newConfigId == null) {
          if (context.mounted) {
            ContextAlert.showToast(context, AppLocalizations.of(context)!.homeRegeneratingKey);
          }
          newConfigId = await AuthService().fetchAndSetRandomVpnKey(forceRegenerate: true);
        }

        if (newConfigId != null) {
          targetConfigId = newConfigId;
          updateConfigId(context, newConfigId);
        }
      }

      if (targetConfigId == DBConstants.defaultId) {
        eventBus.updateVpnLoading(false);
        if (context.mounted) {
          ContextAlert.showToast(
            context,
            AppLocalizations.of(context)!.vpnSelectOneConfig,
          );
        }
        return;
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

  Future<void> signInWithApple() async {
    emit(state.copyWith(connectingProvider: 'apple'));
    try {
      final result = await AuthService().signInWithApple();
      if (result != null) {
        await AuthService().syncUserWithBackend();
        await AuthService().activateTrial();
        final userModel = await AuthService().syncUserWithBackend();
        final subscriptionEndsAt = userModel?.subscriptionEndsAt;
        emit(state.copyWith(
            subscriptionEndsAt: subscriptionEndsAt,
            clearSubscriptionEndsAt: subscriptionEndsAt == null,
            clearConnectingProvider: true));
        ToastService().showToast(AppLocalizations.of(context)!.homeSignInSuccess);
      } else {
        emit(state.copyWith(clearConnectingProvider: true));
        ToastService().showToast(AppLocalizations.of(context)!.homeSignInFailed);
      }
    } catch (e) {
      emit(state.copyWith(clearConnectingProvider: true));
      ToastService().showToast(AppLocalizations.of(context)!.homeSignInFailed);
    }
  }

  void connectTelegram() {
    final url = AppEventBus.instance.state.userData?.telegramUrl ?? 'https://t.me/mvmvpnbot';
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }

  void connectVK() {
    final url = AppEventBus.instance.state.userData?.vkUrl ?? 'https://vk.com/mvmvpn';
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }

  Future<void> clearAllData() async {
    final prefs = SharedPreferencesAsync();
    await prefs.clear();
    await AuthService().signOut();
    emit(HomeState.initial());
  }

  Future<void> regenerateTokenForce() async {
    final newId = await VpnService().regenerateTokenForce();
    if (newId != null) {
      updateConfigId(context, newId);
    }
  }

  void openUrl(String url) {
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }

  @override
  Future<void> close() {
    _toastSubscription.cancel();
    _userUpdateTimer?.cancel();
    return super.close();
  }
}
