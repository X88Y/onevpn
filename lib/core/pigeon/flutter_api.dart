import 'dart:async';

import 'package:mvmvpn/core/pigeon/messages.g.dart';
import 'package:mvmvpn/core/tools/logger.dart';

class AppFlutterApi extends BridgeFlutterApi {
  static final AppFlutterApi _singleton = AppFlutterApi._internal();

  factory AppFlutterApi() => _singleton;

  AppFlutterApi._internal();

  final vpnStatusController = StreamController<VpnStatus>.broadcast();

  @override
  Future<void> vpnStatusChanged(VpnStatus status) async {
    ygLogger("vpnStatusChanged ${status.name}");
    vpnStatusController.add(status);
  }
}
