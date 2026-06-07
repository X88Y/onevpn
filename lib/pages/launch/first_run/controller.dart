import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/network/client.dart';
import 'package:mvmvpn/pages/main/url.dart';
import 'package:mvmvpn/service/subscription/service.dart';
import 'package:mvmvpn/service/tun_setting/interface.dart';
import 'package:mvmvpn/service/tun_setting/state.dart';
import 'package:mvmvpn/service/xray/setting/enum.dart';
import 'package:mvmvpn/service/xray/setting/simple_state.dart';

class FirstRunState {
  final SimpleCountry country;
  final List<NetworkInterface> interfaces;
  final String interface;

  const FirstRunState({
    this.country = SimpleCountry.ru,
    this.interfaces = const [],
    this.interface = "",
  });

  FirstRunState copyWith({
    SimpleCountry? country,
    List<NetworkInterface>? interfaces,
    String? interface,
  }) {
    return FirstRunState(
      country: country ?? this.country,
      interfaces: interfaces ?? this.interfaces,
      interface: interface ?? this.interface,
    );
  }
}

class FirstRunController extends Cubit<FirstRunState> {
  FirstRunController() : super(const FirstRunState()) {
    _readNetworkInterfaces();
  }

  Future<void> _readNetworkInterfaces() async {
    final interfaces = await queryInterfaceList();
    String interfaceName = "";
    if (interfaces.isNotEmpty) {
      interfaceName = interfaces.first.name;
    }
    emit(state.copyWith(interfaces: interfaces, interface: interfaceName));
  }

  void updateCountry(SimpleCountry? value) {
    if (value != null) {
      emit(state.copyWith(country: value));
    }
  }

  void updateInterface(String? value) {
    if (value != null) {
      emit(state.copyWith(interface: value));
    }
  }

  Future<bool> submitAccessKey(BuildContext context, String key) async {
    final trimmedKey = key.trim();
    if (trimmedKey.isEmpty) {
      return false;
    }

    final uri = Uri.tryParse(trimmedKey);
    final isUrl = uri != null && (uri.scheme == 'http' || uri.scheme == 'https');

    String url;
    if (isUrl) {
      final checkUri = Uri(
        scheme: uri.scheme,
        host: uri.host,
        port: uri.port != 0 && uri.port != 80 && uri.port != 443 ? uri.port : null,
        path: '/config',
      );
      // log checkUri
      debugPrint(checkUri.toString());
      final checkUrl = checkUri.toString();
      try {
        final responseText = await NetClient().getText(checkUrl);
        if (responseText == null || responseText.trim() != 'REMNAWAVE') {
          return false;
        }
      } catch (e) {
        return false;
      }
      url = trimmedKey;
    } else {
      url = "https://jl1x2z77a9.cdn.twcstorage.ru/$trimmedKey";
    }

    try {
      final db = AppDatabase();
      
      // 1. Clear database completely to enforce single subscription
      await db.subscriptionDao.clear();
      await db.coreConfigDao.clear();

      // 2. Reset last config selection
      await PreferencesKey().saveLastConfigId(DBConstants.defaultId);
      await PreferencesKey().saveRunningConfigId(DBConstants.defaultId);

      // 3. Try inserting new subscription
      final count = await SubscriptionService().insertSubscription(
        "Основная подписка",
        url,
        false,
      );

      if (count > 0) {
        // 4. Initialize basic routing settings
        await _initSimpleSetting();
        await _initTunSetting();

        // 5. Save accessKey and mark firstRun as false
        await PreferencesKey().saveAccessKey(trimmedKey);
        await PreferencesKey().saveFirstRun(false);

        // 6. Go to home page
        if (context.mounted) {
          context.go(RouterPath.home);
        }
        return true;
      }
    } catch (e) {
      // Handled by returning false
    }
    return false;
  }

  Future<void> _initSimpleSetting() async {
    await PreferencesKey().saveXraySettingId(XraySettingSimple.simpleId);
    final simple = XraySettingSimple();
    simple.routing.directSet = state.country;
    await simple.saveToPreferences();
  }

  Future<void> _initTunSetting() async {
    if (state.interface.isNotEmpty) {
      final tunSetting = TunSettingState();
      tunSetting.bindInterface = state.interface;
      await tunSetting.saveToPreferences();
    }
  }
}
