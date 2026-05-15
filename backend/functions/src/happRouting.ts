
/**
 * Shared logic to generate a Happ routing deeplink based on the documentation.
 * https://www.happ.su/main/dev-docs/routing
 */
export function getHappRoutingProfile() {
  return {
    Name: "MVMVpn Premium",
    GlobalProxy: "true",
    RemoteDNSType: "DoH",
    RemoteDNSDomain: "https://cloudflare-dns.com/dns-query",
    RemoteDNSIP: "1.1.1.1",
    DomesticDNSType: "DoH",
    DomesticDNSDomain: "https://dns.google/dns-query",
    DomesticDNSIP: "8.8.8.8",
    Geoipurl: "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
    Geositeurl: "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
    DirectSites: [
      "geosite:category-gov-ru",
      "geosite:yandex",
      "geosite:vk",
      "domain:gosuslugi.ru",
      "domain:mos.ru",
    ],
    DirectIp: [
      "geoip:ru",
      "geoip:private",
      "10.0.0.0/8",
      "172.16.0.0/12",
      "192.168.0.0/16",
      "169.254.0.0/16",
      "224.0.0.0/4",
      "255.255.255.255",
    ],
    ProxySites: [],
    ProxyIp: [],
    BlockSites: ["geosite:category-ads-all"],
    BlockIp: [],
    DomainStrategy: "IPIfNonMatch",
    FakeDNS: "false",
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
