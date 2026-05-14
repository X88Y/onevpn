import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/core/tools/extensions.dart';
import 'package:mvmvpn/service/localizations/service.dart';
import 'package:mvmvpn/service/xray/json_writer.dart';
import 'package:mvmvpn/service/xray/setting/state.dart';
import 'package:mvmvpn/service/xray/setting/state_writer.dart';
import 'package:tuple/tuple.dart';

extension XraySettingStateValidator on XraySettingState {
  Future<Tuple2<bool, String>> validate() async {
    if (!EmptyTool.checkString(name)) {
      return Tuple2(false, appLocalizationsNoContext().appValidationNameRequired);
    }
    final xrayJson = this.xrayJson;
    removeTunInbound(xrayJson);
    final res = await xrayJson.test();
    if (res.isNotEmpty) {
      return Tuple2(false, res);
    }
    return const Tuple2(true, "");
  }

  void removeWhitespace() {
    name = name.removeWhitespace;
    dns.removeWhitespace();
    routing.removeWhitespace();
    inbounds.removeWhitespace();
    outbounds.removeWhitespace();
  }
}
