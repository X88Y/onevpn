import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/core/tools/file.dart';
import 'package:mvmvpn/gen/assets.gen.dart';
import 'package:mvmvpn/pages/main/url.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/core/pigeon/constants.dart';
import 'package:mvmvpn/service/tun_setting/interface.dart';
import 'package:mvmvpn/service/tun_setting/state.dart';
import 'package:mvmvpn/service/xray/setting/enum.dart';
import 'package:mvmvpn/service/xray/setting/simple_state.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/service/subscription/service.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:path/path.dart' as p;

Future<void> initRouter(BuildContext context) async {
  await _initTheme(context);
  final privacyAccepted = await PreferencesKey().readPrivacyAccepted();
  if (context.mounted) {
    if (privacyAccepted) {
      await checkFirstRun(context);
    } else {
      context.go(RouterPath.privacy);
    }
  }
}

Future<void> checkFirstRun(BuildContext context) async {
  await _initApp(context);
  final firstRun = await PreferencesKey().readFirstRun();
  if (context.mounted) {
    if (firstRun) {
      await _performFirstRunInit();
      await PreferencesKey().saveFirstRun(false);
      context.go(RouterPath.home);
    } else {
      context.go(RouterPath.home);
    }
  }
}

Future<void> _performFirstRunInit() async {
  await PreferencesKey().saveXraySettingId(XraySettingSimple.simpleId);
  final simple = XraySettingSimple();
  simple.routing.directSet = SimpleCountry.ru;
  await simple.saveToPreferences();

  final interfaces = await queryInterfaceList();
  if (interfaces.isNotEmpty) {
    final tunSetting = TunSettingState();
    tunSetting.bindInterface = interfaces.first.name;
    await tunSetting.saveToPreferences();
  }
}

Future<void> _initApp(BuildContext context) async {
  if (context.mounted) {
    await _initService(context);
  }
  await _checkSystemDat();
  await _ensureHardcodedSubscription();
}

Future<void> _ensureHardcodedSubscription() async {
  const url = 'https://2.26.112.188:2096/sub/17724a9bf79e414f9dd2b7b86f98be60';
  final db = AppDatabase();
  final exists = await db.subscriptionDao.urlExists(url);
  if (!exists) {
    final count = await SubscriptionService().insertSubscription('Default', url, false);
    if (count > 0) {
      final lastId = await PreferencesKey().readLastConfigId();
      if (lastId == DBConstants.defaultId) {
        final configs = await db.select(db.coreConfig).get();
        if (configs.isNotEmpty) {
          await PreferencesKey().saveLastConfigId(configs.first.id);
        }
      }
    }
  }
}

Future<void> _initTheme(BuildContext context) async {
  final eventBus = context.read<AppEventBus>();
  await eventBus.asyncInitTheme();
}

Future<void> _initService(BuildContext context) async {
  final eventBus = context.read<AppEventBus>();
  await eventBus.asyncInitService(context);
}

Future<void> _checkSystemDat() async {
  final datPath = VpnConstants.datDir;
  await FileTool.checkDir(datPath);

  final dstTimestampPath = p.join(datPath, VpnConstants.systemGeoTimestamp);
  final dstTimestampFile = File(dstTimestampPath);
  final exists = await dstTimestampFile.exists();
  if (exists) {
    var dstTimestamp = await dstTimestampFile.readAsString();
    dstTimestamp = dstTimestamp.trim();
    var srcTimestamp = await rootBundle.loadString(Assets.dat.timestamp);
    srcTimestamp = srcTimestamp.trim();
    if (srcTimestamp.compareTo(dstTimestamp) > 0) {
      await FileTool.copyAssets(Assets.dat.values, datPath);
    }
  } else {
    await FileTool.copyAssets(Assets.dat.values, datPath);
  }
}
