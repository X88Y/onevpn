import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mvmvpn/core/pigeon/flutter_api.dart';
import 'package:mvmvpn/core/pigeon/host_api.dart';
import 'package:mvmvpn/core/pigeon/messages.g.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:mvmvpn/pages/main/router.dart';
import 'package:window_manager/window_manager.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await _initBridge();

  if (AppPlatform.isDesktop) {
    await windowManager.ensureInitialized();

    const windowSize = Size(400, 600);
    // mac store
    // const windowSize = Size(1168, 688);
    WindowOptions windowOptions = WindowOptions(
      size: windowSize,
      minimumSize: windowSize,
      center: true,
    );
    windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
    });
  }

  runApp(GoRouteApp());
}

Future<void> _initBridge() async {
  BridgeFlutterApi.setUp(AppFlutterApi());
  await AppHostApi().initTunFilesDir();
}
