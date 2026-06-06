import 'package:mvmvpn/core/model/xray_json.dart';
import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/download/state_reader.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/state.dart';

extension XhttpExtraStateReader on XhttpExtraState {
  bool readFromXrayJson(XrayXhttpSettings settings) {
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

    // PR #6258 – session-ID customisation
    if (settings.sessionIDTable != null &&
        settings.sessionIDTable!.isNotEmpty) {
      sessionIDTable = settings.sessionIDTable!;
    }
    if (settings.sessionIDLength != null) {
      final str = settings.sessionIDLength.toString();
      if (str.isNotEmpty) {
        sessionIDLength = str;
      }
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

    if (settings.downloadSettings != null) {
      if (!downloadSettings.readFromXrayJson(settings.downloadSettings!)) {
        return false;
      }
    }
    return true;
  }
}
