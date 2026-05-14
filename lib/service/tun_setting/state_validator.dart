import 'dart:io';

import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/core/tools/extensions.dart';
import 'package:mvmvpn/service/localizations/service.dart';
import 'package:mvmvpn/service/tun_setting/state.dart';
import 'package:tuple/tuple.dart';

extension TunSettingStateValidator on TunSettingState {
  Future<Tuple2<bool, String>> validate() async {
    if (!EmptyTool.checkString(tunPriority)) {
      return Tuple2(
        false,
        appLocalizationsNoContext().appValidationPriorityRequired,
      );
    }
    if (!EmptyTool.checkString(tunDnsIPv4)) {
      return Tuple2(false, appLocalizationsNoContext().appValidationDnsRequired);
    }

    final ipv4 = InternetAddress.tryParse(tunDnsIPv4);
    if (ipv4 == null) {
      return Tuple2(false, appLocalizationsNoContext().appValidationIPv4Invalid);
    }

    if (ipv4.type != InternetAddressType.IPv4) {
      return Tuple2(false, appLocalizationsNoContext().appValidationIPv4Invalid);
    }

    if (!EmptyTool.checkString(tunDnsIPv6)) {
      return Tuple2(false, appLocalizationsNoContext().appValidationDnsRequired);
    }

    final ipv6 = InternetAddress.tryParse(tunDnsIPv6);
    if (ipv6 == null) {
      return Tuple2(false, appLocalizationsNoContext().appValidationIPv6Invalid);
    }

    if (ipv6.type != InternetAddressType.IPv6) {
      return Tuple2(false, appLocalizationsNoContext().appValidationIPv6Invalid);
    }

    if (enableDot) {
      if (!EmptyTool.checkString(dnsServerName)) {
        return Tuple2(false, appLocalizationsNoContext().appValidationDnsRequired);
      }
    }

    return const Tuple2(true, "");
  }

  void removeWhitespace() {
    tunPriority = tunPriority.removeWhitespace;
    tunDnsIPv4 = tunDnsIPv4.removeWhitespace;
    tunDnsIPv6 = tunDnsIPv6.removeWhitespace;
    dnsServerName = dnsServerName.removeWhitespace;

    bindInterface = bindInterface.removeWhitespace;

    for (final rule in onDemandRules) {
      rule.removeWhitespace();
    }

    allowAppList = allowAppList.removeWhitespace;
    disallowAppList = disallowAppList.removeWhitespace;
  }
}

extension OnDemandRuleStateValidator on OnDemandRuleState {
  void removeWhitespace() {
    ssid = ssid.removeWhitespace;
  }
}
