import 'dart:io';

import 'package:mvmvpn/core/ffi/model.dart';
import 'package:mvmvpn/core/tools/json.dart';
import 'package:mvmvpn/core/pigeon/constants.dart';

extension RunXrayConfigWriter on RunXrayConfig {
  Future<String> writeToFile() async {
    final data = JsonTool.encoderForFile.convert(toJson());
    final filePath = VpnConstants.coreConfigPath;
    await File(filePath).writeAsString(data);

    return filePath;
  }
}
