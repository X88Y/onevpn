import 'dart:async';

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
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class HomeState {
  final int configId;
  final DateTime? subscriptionEndsAt;

  const HomeState({required this.configId, this.subscriptionEndsAt});

  factory HomeState.initial() =>
      const HomeState(configId: DBConstants.defaultId);

  HomeState copyWith({int? configId, DateTime? subscriptionEndsAt, bool clearSubscriptionEndsAt = false}) {
    return HomeState(
      configId: configId ?? this.configId,
      subscriptionEndsAt: clearSubscriptionEndsAt
          ? null
          : (subscriptionEndsAt ?? this.subscriptionEndsAt),
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
      case IconMenuId.scanQRCode:
        await _scanQrCode(context);
        break;
      case IconMenuId.pickImage:
        await ShareService().pickImage();
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

  Future<void> _scanQrCode(BuildContext context) async {
    final status = await Permission.camera.request();
    if (status.isGranted) {
      if (context.mounted) {
        final result = await context.push<String>(RouterPath.qrcode);
        if (result != null) {
          await ShareService().readShareText(result);
        }
      }
    } else {
      if (context.mounted) {
        await ContextAlert.showPermissionDialog(context);
      }
    }
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

  Future<void> startVpn(BuildContext context) async {
    final eventBus = AppEventBus.instance;
    final isRunning = eventBus.state.runningId != DBConstants.defaultId;
    
    eventBus.updateVpnLoading(true);

    try {
      if (isRunning) {
        await VpnService().startVpn(eventBus.state.runningId);
        return;
      }

      int targetConfigId = state.configId;

      if (AuthService().currentUser != null) {
        var newConfigId = await AuthService().fetchAndSetRandomVpnKey();
        if (newConfigId == null) {
          if (context.mounted) {
            ContextAlert.showToast(context, 'Regenerating subscription key...');
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
    final result = await AuthService().signInWithApple();
    if (result != null) {
      await AuthService().activateTrial();
      final userModel = await AuthService().syncUserWithBackend();
      final subscriptionEndsAt = userModel?.subscriptionEndsAt;
      emit(state.copyWith(
          subscriptionEndsAt: subscriptionEndsAt,
          clearSubscriptionEndsAt: subscriptionEndsAt == null));
      ToastService().showToast('Signed in successfully');
    } else {
      ToastService().showToast('Sign in failed');
    }
  }

  void connectTelegram() {
    launchUrl(Uri.parse('https://t.me/mvmvpnbot'), mode: LaunchMode.externalApplication);
  }

  void connectVK() {
    launchUrl(Uri.parse('https://vk.com/mvmvpn'), mode: LaunchMode.externalApplication);
  }

  Future<void> clearAllData() async {
    final prefs = SharedPreferencesAsync();
    await prefs.clear();
    await AuthService().signOut();
    emit(HomeState.initial());
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
