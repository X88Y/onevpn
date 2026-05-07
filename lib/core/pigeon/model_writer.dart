import 'dart:io';

import 'package:mvmvpn/core/pigeon/model.dart';
import 'package:mvmvpn/core/tools/json.dart';
import 'package:mvmvpn/core/pigeon/constants.dart';

extension StartVpnRequestWriter on StartVpnRequest {
  Future<void> writeToStartFile() async {
    final data = JsonTool.encoderForFile.convert(toJson());
    final filePath = VpnConstants.startPath;
    await File(filePath).writeAsString(data);
  }
}
