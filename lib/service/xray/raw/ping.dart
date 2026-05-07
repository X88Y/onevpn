import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/network/constants.dart';
import 'package:mvmvpn/core/pigeon/host_api.dart';
import 'package:mvmvpn/core/tools/file.dart';
import 'package:mvmvpn/core/tools/json.dart';
import 'package:mvmvpn/service/ping/state.dart';
import 'package:mvmvpn/core/pigeon/constants.dart';
import 'package:mvmvpn/service/xray/raw/fix.dart';
import 'package:mvmvpn/service/xray/raw/writer.dart';
import 'package:mvmvpn/service/xray/setting/inbounds_state.dart';

class XrayRawPing {
  static Future<int> ping(String rawText, PingState pingState) async {
    final ports = await XrayPorts.getPorts();
    if (ports == null) {
      return PingDelayConstants.unknown;
    }
    final jsonMap = JsonTool.decoder.convert(rawText);
    //remove metrics
    XrayRawFix.fixMetrics(jsonMap);
    XrayRawFix.fixInboundsTun(jsonMap);
    XrayRawFix.fixInboundsPort(jsonMap, ports);
    XrayRawFix.fixLog(jsonMap);
    final text = JsonTool.encoderForDb.convert(jsonMap);

    final configPath = await XrayRawWriter.writeConfig(text);

    final res = await AppHostApi().ping(
      VpnConstants.datDir,
      configPath,
      pingState.timeout.toInt(),
      pingState.realUrl,
      "http://${NetConstants.proxyHost}:${ports.pingPort}",
    );
    await FileTool.deleteFileIfExists(configPath);

    return res;
  }
}
