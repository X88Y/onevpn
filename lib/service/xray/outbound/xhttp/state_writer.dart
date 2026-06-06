import 'package:mvmvpn/core/model/xray_json.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/download/state_validator.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/download/state_writer.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/state.dart';
import 'package:mvmvpn/service/xray/standard.dart';

extension XhttpExtraStateWriter on XhttpExtraState {
  XrayXhttpSettings get xrayJson {
    final xhttpSettings = XrayXhttpSettingsStandard.standard;

    if (headers.isNotEmpty) {
      xhttpSettings.headers = headers;
    }
    if (xPaddingBytes.isNotEmpty) {
      xhttpSettings.xPaddingBytes = xPaddingBytes;
    }
    if (noGRPCHeader) {
      xhttpSettings.noGRPCHeader = noGRPCHeader;
    }
    if (scMaxEachPostBytes.isNotEmpty) {
      xhttpSettings.scMaxEachPostBytes = scMaxEachPostBytes;
    }
    if (scMinPostsIntervalMs.isNotEmpty) {
      xhttpSettings.scMinPostsIntervalMs = scMinPostsIntervalMs;
    }

    if (seqKey.isNotEmpty) {
      xhttpSettings.seqKey = seqKey;
    }
    if (sessionKey.isNotEmpty) {
      xhttpSettings.sessionKey = sessionKey;
    }
    if (noSSEHeader) {
      xhttpSettings.noSSEHeader = noSSEHeader;
    }
    if (xPaddingKey.isNotEmpty) {
      xhttpSettings.xPaddingKey = xPaddingKey;
    }
    if (seqPlacement.isNotEmpty) {
      xhttpSettings.seqPlacement = seqPlacement;
    }
    if (uplinkDataKey.isNotEmpty) {
      xhttpSettings.uplinkDataKey = uplinkDataKey;
    }
    if (xPaddingHeader.isNotEmpty) {
      xhttpSettings.xPaddingHeader = xPaddingHeader;
    }
    if (xPaddingMethod.isNotEmpty) {
      xhttpSettings.xPaddingMethod = xPaddingMethod;
    }
    if (uplinkChunkSize.isNotEmpty) {
      xhttpSettings.uplinkChunkSize = int.tryParse(uplinkChunkSize) ?? uplinkChunkSize;
    }
    if (sessionPlacement.isNotEmpty) {
      xhttpSettings.sessionPlacement = sessionPlacement;
    }
    if (uplinkHTTPMethod.isNotEmpty) {
      xhttpSettings.uplinkHTTPMethod = uplinkHTTPMethod;
    }
    if (xPaddingObfsMode) {
      xhttpSettings.xPaddingObfsMode = xPaddingObfsMode;
    }
    if (xPaddingPlacement.isNotEmpty) {
      xhttpSettings.xPaddingPlacement = xPaddingPlacement;
    }
    if (scMaxBufferedPosts.isNotEmpty) {
      xhttpSettings.scMaxBufferedPosts = int.tryParse(scMaxBufferedPosts) ?? scMaxBufferedPosts;
    }
    if (uplinkDataPlacement.isNotEmpty) {
      xhttpSettings.uplinkDataPlacement = uplinkDataPlacement;
    }
    if (scStreamUpServerSecs.isNotEmpty) {
      xhttpSettings.scStreamUpServerSecs = scStreamUpServerSecs;
    }

    // PR #6258 – session-ID customisation
    if (sessionIDTable.isNotEmpty) {
      xhttpSettings.sessionIDTable = sessionIDTable;
    }
    if (sessionIDLength.isNotEmpty) {
      // Preserve as-is: can be a range string "8-16" or bare int "12".
      // The Go side (SplitHTTPConfig) expects Int32Range – pass as dynamic.
      xhttpSettings.sessionIDLength =
          int.tryParse(sessionIDLength) ?? sessionIDLength;
    }

    final xmux = XrayXhttpSettingsXmuxStandard.standard;
    if (maxConcurrency.isNotEmpty) {
      xmux.maxConcurrency = maxConcurrency;
    }
    if (maxConnections.isNotEmpty) {
      xmux.maxConnections = maxConnections;
    }
    if (cMaxReuseTimes.isNotEmpty) {
      xmux.cMaxReuseTimes = cMaxReuseTimes;
    }
    if (hMaxReusableSecs.isNotEmpty) {
      xmux.hMaxReusableSecs = hMaxReusableSecs;
    }
    if (hMaxRequestTimes.isNotEmpty) {
      xmux.hMaxRequestTimes = hMaxRequestTimes;
    }
    if (hKeepAlivePeriod.isNotEmpty) {
      xmux.hKeepAlivePeriod = int.tryParse(hKeepAlivePeriod);
    }
    xhttpSettings.xmux = xmux;

    if (!downloadSettings.isBlank) {
      xhttpSettings.downloadSettings = downloadSettings.xrayJson;
    }

    return xhttpSettings;
  }
}
