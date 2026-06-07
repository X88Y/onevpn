import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/core/network/client.dart';
import 'package:mvmvpn/core/network/model.dart';
import 'package:mvmvpn/core/tools/logger.dart';
import 'package:mvmvpn/service/auth/model.dart';
import 'package:mvmvpn/service/event_bus/enum.dart';
import 'package:mvmvpn/service/event_bus/state.dart';
import 'package:mvmvpn/service/manager.dart';
import 'package:mvmvpn/service/subscription/service.dart';

class AppEventBus extends Cubit<AppEventBusState> with WidgetsBindingObserver {
  static late AppEventBus instance;

  AppEventBus() : super(AppEventBusState.initial()) {
    instance = this;
  }

  Future<void> asyncInitTheme() async {
    final themeCode = await PreferencesKey().readThemeCode();
    final languageCode = await PreferencesKey().readLanguageCode();
    emit(
      state.copyWith(
        themeCode: ThemeCode.fromString(themeCode),
        languageCode: LanguageCode.fromString(languageCode),
      ),
    );
  }

  DateTime? _lastUpdateTime;

  Future<void> asyncInitService(BuildContext context) async {
    await _asyncInitState();
    if (context.mounted) {
      await ServiceManager.serviceInit(context);
    }
    WidgetsBinding.instance.addObserver(this);
    // Fetch info, urls, and subscriptions on app open
    _onAppOpen();
  }

  void _onAppOpen() {
    final now = DateTime.now();
    if (_lastUpdateTime != null && now.difference(_lastUpdateTime!).inSeconds < 10) {
      return;
    }
    _lastUpdateTime = now;
    fetchInfoAndUrls();
    _updateSubscriptions();
  }

  Future<void> _updateSubscriptions() async {
    try {
      await SubscriptionService().refreshAllSubscription();
    } catch (e) {
      ygLogger("Failed to refresh subscriptions on app open: $e");
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _onAppOpen();
    }
  }

  Future<void> fetchInfoAndUrls() async {
    try {
      final jsonStr = await NetClient().getText("https://gpy4me9ehp.cdn.twcstorage.ru/info");
      if (jsonStr != null) {
        final Map<String, dynamic> data = json.decode(jsonStr);
        if (data['ok'] == true) {
          final String? tg = data['tg'];
          final String? vk = data['vk'];
          final String? title = data['title'];
          final String? subtitle = data['subTitile'] ?? data['subtitle'];

          emit(state.copyWith(
            infoMessage: title,
            infoSubMessage: subtitle,
            tgUrl: tg ?? state.tgUrl,
            vkUrl: vk ?? state.vkUrl,
          ));
        }
      }
    } catch (e) {
      ygLogger("Failed to fetch info and social URLs: $e");
    }
  }

  Future<void> _asyncInitState() async {
    final xraySettingId = await PreferencesKey().readXraySettingId();
    final runningId = await PreferencesKey().readRunningConfigId();
    final userProfile = await PreferencesKey().readUserProfile();
    UserModel? userData;
    if (userProfile != null) {
      userData = UserModel.fromJson(userProfile);
    }
    emit(state.copyWith(
      xraySettingId: xraySettingId,
      runningId: runningId,
      userData: userData,
    ));
  }

  void updateXraySettingId(int value) {
    emit(state.copyWith(xraySettingId: value));
  }

  void updateVpnLoading(bool value) {
    emit(state.copyWith(vpnLoading: value));
  }

  void updateRunningId(int value) {
    emit(state.copyWith(runningId: value));
  }

  void updatePinging(bool value) {
    emit(state.copyWith(pinging: value));
  }

  void updateLocation(GeoLocation value) {
    emit(state.copyWith(location: value));
  }

  void updateLocationDuration(String duration) {
    final loc = state.location;
    loc.duration = duration;
    emit(
      state.copyWith(location: loc, locationVersion: state.locationVersion + 1),
    );
  }

  void updateDownloading(bool value) {
    emit(state.copyWith(downloading: value));
  }

  void updateWindowClosed(bool value) {
    emit(state.copyWith(windowClosed: value));
  }

  Future<void> updateThemeCode(ThemeCode value) async {
    await PreferencesKey().saveThemeCode(value.name);
    emit(state.copyWith(themeCode: value));
  }

  Future<void> updateLanguageCode(LanguageCode value) async {
    await PreferencesKey().saveLanguageCode(value.name);
    emit(state.copyWith(languageCode: value));
  }
  
  void updateUserData(UserModel? value) {
    emit(state.copyWith(
      userData: value,
      clearUserData: value == null,
    ));
  }

  /// Set [true] while a subscription update/regeneration is in progress so the
  /// UI can suppress the connected/disconnected statuses and show only loading.
  void updateSubscriptionUpdating(bool value) {
    emit(state.copyWith(isUpdatingSubscription: value));
  }

  @override
  Future<void> close() {
    WidgetsBinding.instance.removeObserver(this);
    ServiceManager.serviceDispose();
    return super.close();
  }
}
