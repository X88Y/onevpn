
/**
 * Shared logic to generate a Happ routing deeplink based on the documentation.
 * https://www.happ.su/main/dev-docs/routing
 */
export function getHappRoutingProfile() {
  return {
    Name: "MVMVpn Premium",
    GlobalProxy: "true",
    RemoteDNSType: "DoH",
    RemoteDNSDomain: "https://8.8.8.8/dns-query",
    RemoteDNSIP: "8.8.8.8",
    DomesticDNSType: "DoH",
    DomesticDNSDomain: "https://77.88.8.8/dns-query",
    DomesticDNSIP: "77.88.8.8",
    DnsHosts: {
      "lkfl2.nalog.ru": "213.24.64.175",
      "lknpd.nalog.ru": "213.24.64.181",
    },
    Geoipurl: "https://cdn.jsdelivr.net/gh/hydraponique/roscomvpn-geoip@202604250521/release/geoip.dat",
    Geositeurl: "https://cdn.jsdelivr.net/gh/hydraponique/roscomvpn-geosite@202604152235/release/geosite.dat",
    DirectSites: [
      "geosite:private",
      "geosite:category-ru",
      "geosite:whitelist",
      "geosite:microsoft",
      "geosite:apple",
      "geosite:epicgames",
      "geosite:riot",
      "geosite:escapefromtarkov",
      "geosite:steam",
      "geosite:twitch",
      "geosite:pinterest",
      "geosite:faceit",
    ],
    ProxySites: [
      "geosite:google-play",
      "geosite:github",
      "geosite:twitch-ads",
      "geosite:youtube",
      "geosite:telegram",
    ],
    BlockSites: [
      "geosite:win-spy",
      "geosite:torrent",
      "geosite:category-ads",
    ],
    DirectIp: ["geoip:private", "geoip:direct"],
    ProxyIp: [],
    BlockIp: [],
    DomainStrategy: "IPIfNonMatch",
    FakeDNS: "false",
    UseChunkFiles: "true",
    RouteOrder: "block-proxy-direct",
    LastUpdated: 1777094515,
  };
}

export function getHappRoutingDeeplink(onAdd = true): string {
  const profile = getHappRoutingProfile();
  const encoded = Buffer.from(JSON.stringify(profile))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  
  const type = onAdd ? "onadd" : "add";
  return `happ://routing/${type}/${encoded}`;
}
