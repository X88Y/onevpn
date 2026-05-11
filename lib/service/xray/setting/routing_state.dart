import 'package:mvmvpn/core/model/xray_json.dart';
import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/service/xray/setting/enum.dart';
import 'package:mvmvpn/service/xray/setting/routing_rule_state.dart';
import 'package:mvmvpn/service/xray/setting/state.dart';
import 'package:mvmvpn/service/xray/standard.dart';

class RoutingState {
  var domainStrategy = RoutingDomainStrategy.ipIfNonMatch;
  var dnsQueryRule = RoutingRuleState.dnsQueryRule;
  final dnsOutRule = RoutingRuleState.dnsOutRule;
  var dnsDoTRule = RoutingRuleState.dnsDoTRule;
  final pingRule = RoutingRuleState.pingRule;
  var customRules = <RoutingRuleState>[];

  /// Pre-configured routing rules matching the panel's default Xray config.
  static RoutingState get panelDefault {
    final state = RoutingState();
    state.domainStrategy = RoutingDomainStrategy.ipIfNonMatch;

    // Block rule: win-spy, torrent, category-ads
    final blockRule = RoutingRuleState();
    blockRule.domain = [
      'geosite:win-spy',
      'geosite:torrent',
      'geosite:category-ads',
    ];
    blockRule.outboundTag = RoutingOutboundTag.block.name;
    blockRule.ruleTag = 'block';

    // Proxy rule: google-play, github, twitch-ads, youtube, telegram
    final proxyRule = RoutingRuleState();
    proxyRule.domain = [
      'geosite:google-play',
      'geosite:github',
      'geosite:twitch-ads',
      'geosite:youtube',
      'geosite:telegram',
    ];
    proxyRule.outboundTag = RoutingOutboundTag.proxy.name;
    proxyRule.ruleTag = 'proxy';

    // Direct rule: private, category-ru, whitelist, microsoft, apple,
    // epicgames, riot, escapefromtarkov, steam, twitch, pinterest, faceit
    final directDomainRule = RoutingRuleState();
    directDomainRule.domain = [
      'geosite:private',
      'geosite:category-ru',
      'geosite:whitelist',
      'geosite:microsoft',
      'geosite:apple',
      'geosite:epicgames',
      'geosite:riot',
      'geosite:escapefromtarkov',
      'geosite:steam',
      'geosite:twitch',
      'geosite:pinterest',
      'geosite:faceit',
    ];
    directDomainRule.outboundTag = RoutingOutboundTag.direct.name;
    directDomainRule.ruleTag = 'direct';

    // Direct rule: geoip:private, geoip:direct
    final directIpRule = RoutingRuleState();
    directIpRule.ip = ['geoip:private', 'geoip:direct'];
    directIpRule.outboundTag = RoutingOutboundTag.direct.name;
    directIpRule.ruleTag = 'directIP';

    // Proxy DNS rule: 8.8.8.8:443 → proxy
    final proxyDnsRule = RoutingRuleState();
    proxyDnsRule.ip = ['8.8.8.8'];
    proxyDnsRule.port = '443';
    proxyDnsRule.outboundTag = RoutingOutboundTag.proxy.name;
    proxyDnsRule.ruleTag = 'proxyDNS';

    // Direct DNS rule: 77.88.8.8:443 → direct
    final directDnsRule = RoutingRuleState();
    directDnsRule.ip = ['77.88.8.8'];
    directDnsRule.port = '443';
    directDnsRule.outboundTag = RoutingOutboundTag.direct.name;
    directDnsRule.ruleTag = 'directDNS';

    // Inbound passthrough: socks-direct → direct
    final socksDirect = RoutingRuleState();
    socksDirect.inboundTag = {'socks-direct'};
    socksDirect.outboundTag = RoutingOutboundTag.direct.name;
    socksDirect.ruleTag = 'socksDirect';

    state.customRules = [
      blockRule,
      proxyRule,
      directDomainRule,
      directIpRule,
      proxyDnsRule,
      directDnsRule,
      socksDirect,
    ];

    return state;
  }

  void removeWhitespace() {
    for (final rule in customRules) {
      rule.removeWhitespace();
    }
  }

  void readFromXrayJson(XrayJson xrayJson) {
    if (xrayJson.routing == null) {
      return;
    }
    final routing = xrayJson.routing!;
    if (EmptyTool.checkString(routing.domainStrategy)) {
      final domainStrategy = RoutingDomainStrategy.fromString(
        routing.domainStrategy!,
      );
      if (domainStrategy != null) {
        this.domainStrategy = domainStrategy;
      }
    }
    if (EmptyTool.checkList(routing.rules)) {
      for (final rule in routing.rules!) {
        final ruleState = RoutingRuleState();
        if (EmptyTool.checkString(rule.ruleTag)) {
          if (rule.ruleTag! == RoutingRuleTag.dnsQuery) {
            ruleState.readFromRoutingRule(rule);
            dnsQueryRule.outboundTag = ruleState.outboundTag;
          } else if (rule.ruleTag! == RoutingRuleTag.dnsOut) {
            continue;
          } else if (rule.ruleTag! == RoutingRuleTag.dnsDoT) {
            ruleState.readFromRoutingRule(rule);
            dnsDoTRule.outboundTag = ruleState.outboundTag;
          } else if (rule.ruleTag! == RoutingRuleTag.ping) {
            continue;
          } else {
            ruleState.readFromRoutingRule(rule);
            customRules.add(ruleState);
          }
        } else {
          ruleState.readFromRoutingRule(rule);
          customRules.add(ruleState);
        }
      }
    }
  }

  XrayRouting get xrayJson {
    final routing = XrayRoutingStandard.standard;
    routing.domainStrategy = domainStrategy.name;
    final rules = <RoutingRuleState>[
      dnsQueryRule,
      dnsOutRule,
      dnsDoTRule,
      pingRule,
    ];
    if (customRules.isNotEmpty) {
      rules.addAll(customRules);
    }
    routing.rules = rules.map((e) => e.xrayJson).toList();
    return routing;
  }
}
