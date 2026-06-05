import 'package:mvmvpn/core/model/xray_json.dart';
import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/service/xray/outbound/enum.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/download/state.dart';

extension XhttpDownloadStateReader on XhttpDownloadState {
  bool readFromXrayJson(XrayStreamSettings settings) {
    if (EmptyTool.checkString(settings.address)) {
      address = settings.address!;
    }

    if (settings.port != null) {
      port = "${settings.port!}";
    }

    if (settings.xhttpSettings != null) {
      if (!_parseXhttpSettings(settings.xhttpSettings!)) {
        return false;
      }
    }

    if (EmptyTool.checkString(settings.security)) {
      final security = StreamSettingsSecurity.fromString(settings.security!);
      if (security != null) {
        this.security = security;
      } else {
        return false;
      }
    }

    switch (security) {
      case StreamSettingsSecurity.tls:
        if (settings.tlsSettings != null) {
          if (!_parseTlsSettings(settings.tlsSettings!)) {
            return false;
          }
        }
        break;
      case StreamSettingsSecurity.reality:
        if (settings.realitySettings != null) {
          if (!_parseRealitySettings(settings.realitySettings!)) {
            return false;
          }
        }
        break;
      default:
        return false;
    }

    if (settings.xhttpSettings != null) {
      _readExtraSettings(settings.xhttpSettings!);
      if (settings.xhttpSettings!.extra != null) {
        _readExtraSettings(settings.xhttpSettings!.extra!);
      }
    }

    return true;
  }

  bool _parseXhttpSettings(XrayXhttpSettings settings) {
    if (EmptyTool.checkString(settings.host)) {
      xhttpHost = settings.host!;
    }
    if (EmptyTool.checkString(settings.path)) {
      xhttpPath = settings.path!;
    }
    if (EmptyTool.checkString(settings.mode)) {
      final mode = XhttpMode.fromString(settings.mode!);
      if (mode == null) {
        return false;
      }
      xhttpMode = mode;
    }
    return true;
  }

  bool _parseTlsSettings(XrayTlsSettings settings) {
    if (EmptyTool.checkString(settings.serverName)) {
      serverName = settings.serverName!;
    }
    if (EmptyTool.checkList(settings.alpn)) {
      alpn = StreamSettingsSecurityALPN.fromStrings(settings.alpn!);
    }
    if (EmptyTool.checkString(settings.fingerprint)) {
      final fingerprint = StreamSettingsSecurityFingerprint.fromString(
        settings.fingerprint!,
      );
      if (fingerprint == null) {
        return false;
      }
      this.fingerprint = fingerprint;
    }
    if (EmptyTool.checkString(settings.pinnedPeerCertSha256)) {
      pinnedPeerCertSha256 = settings.pinnedPeerCertSha256!;
    }
    if (EmptyTool.checkString(settings.verifyPeerCertByName)) {
      verifyPeerCertByName = settings.verifyPeerCertByName!;
    }
    if (EmptyTool.checkString(settings.echConfigList)) {
      echConfigList = settings.echConfigList!;
    }
    if (EmptyTool.checkString(settings.echForceQuery)) {
      final echForceQuery = StreamSettingsEchForceQuery.fromString(
        settings.echForceQuery!,
      );
      if (echForceQuery == null) {
        return false;
      }
      this.echForceQuery = echForceQuery;
    }
    return true;
  }

  bool _parseRealitySettings(XrayRealitySettings settings) {
    if (EmptyTool.checkString(settings.fingerprint)) {
      final fingerprint = StreamSettingsSecurityFingerprint.fromString(
        settings.fingerprint!,
      );
      if (fingerprint == null) {
        return false;
      }
      this.fingerprint = fingerprint;
    }
    if (EmptyTool.checkString(settings.serverName)) {
      serverName = settings.serverName!;
    }
    if (EmptyTool.checkString(settings.password)) {
      password = settings.password!;
    } else if (EmptyTool.checkString(settings.publicKey)) {
      password = settings.publicKey!;
    }
    if (EmptyTool.checkString(settings.shortId)) {
      shortId = settings.shortId!;
    }
    if (EmptyTool.checkString(settings.mldsa65Verify)) {
      mldsa65Verify = settings.mldsa65Verify!;
    }
    if (EmptyTool.checkString(settings.spiderX)) {
      spiderX = settings.spiderX!;
    }
    return true;
  }

  bool _readExtraSettings(XrayXhttpSettings settings) {
    if (EmptyTool.checkMap(settings.headers)) {
      headers = settings.headers!;
    }
    if (settings.xPaddingBytes != null) {
      final str = settings.xPaddingBytes.toString();
      if (str.isNotEmpty) {
        xPaddingBytes = str;
      }
    }
    if (settings.noGRPCHeader != null) {
      noGRPCHeader = settings.noGRPCHeader!;
    }
    if (settings.scMaxEachPostBytes != null) {
      final str = settings.scMaxEachPostBytes.toString();
      if (str.isNotEmpty) {
        scMaxEachPostBytes = str;
      }
    }
    if (settings.scMinPostsIntervalMs != null) {
       final str = settings.scMinPostsIntervalMs.toString();
       if (str.isNotEmpty) {
         scMinPostsIntervalMs = str;
       }
     }

     if (settings.seqKey != null) {
       seqKey = settings.seqKey!;
     }
     if (settings.sessionKey != null) {
       sessionKey = settings.sessionKey!;
     }
     if (settings.noSSEHeader != null) {
       noSSEHeader = settings.noSSEHeader!;
     }
     if (settings.xPaddingKey != null) {
       xPaddingKey = settings.xPaddingKey!;
     }
     if (settings.seqPlacement != null) {
       seqPlacement = settings.seqPlacement!;
     }
     if (settings.uplinkDataKey != null) {
       uplinkDataKey = settings.uplinkDataKey!;
     }
     if (settings.xPaddingHeader != null) {
       xPaddingHeader = settings.xPaddingHeader!;
     }
     if (settings.xPaddingMethod != null) {
       xPaddingMethod = settings.xPaddingMethod!;
     }
     if (settings.uplinkChunkSize != null) {
       uplinkChunkSize = settings.uplinkChunkSize.toString();
     }
     if (settings.sessionPlacement != null) {
       sessionPlacement = settings.sessionPlacement!;
     }
     if (settings.uplinkHTTPMethod != null) {
       uplinkHTTPMethod = settings.uplinkHTTPMethod!;
     }
     if (settings.xPaddingObfsMode != null) {
       xPaddingObfsMode = settings.xPaddingObfsMode!;
     }
     if (settings.xPaddingPlacement != null) {
       xPaddingPlacement = settings.xPaddingPlacement!;
     }
     if (settings.scMaxBufferedPosts != null) {
       scMaxBufferedPosts = settings.scMaxBufferedPosts.toString();
     }
     if (settings.uplinkDataPlacement != null) {
       uplinkDataPlacement = settings.uplinkDataPlacement!;
     }
     if (settings.scStreamUpServerSecs != null) {
       scStreamUpServerSecs = settings.scStreamUpServerSecs.toString();
     }

    if (settings.xmux != null) {
      final xmux = settings.xmux!;
      if (xmux.maxConcurrency != null) {
        final str = xmux.maxConcurrency.toString();
        if (str.isNotEmpty) {
          maxConcurrency = str;
        }
      }
      if (xmux.maxConnections != null) {
        final str = xmux.maxConnections.toString();
        if (str.isNotEmpty) {
          maxConnections = str;
        }
      }
      if (xmux.cMaxReuseTimes != null) {
        final str = xmux.cMaxReuseTimes.toString();
        if (str.isNotEmpty) {
          cMaxReuseTimes = str;
        }
      }
      if (xmux.hMaxReusableSecs != null) {
        final str = xmux.hMaxReusableSecs.toString();
        if (str.isNotEmpty) {
          hMaxReusableSecs = str;
        }
      }
      if (xmux.hMaxRequestTimes != null) {
        final str = xmux.hMaxRequestTimes.toString();
        if (str.isNotEmpty) {
          hMaxRequestTimes = str;
        }
      }
      if (xmux.hKeepAlivePeriod != null) {
        hKeepAlivePeriod = "${xmux.hKeepAlivePeriod!}";
      }
    }

    return true;
  }
}
