import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/core/tools/extensions.dart';
import 'package:mvmvpn/service/xray/outbound/enum.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/download/state.dart';

extension XhttpDownloadStateValidator on XhttpDownloadState {
  void removeWhitespace() {
    address = address.removeWhitespace;
    port = port.removeWhitespace;

    xhttpHost = xhttpHost.removeWhitespace;
    xhttpPath = xhttpPath.removeWhitespace;

    serverName = serverName.removeWhitespace;
    pinnedPeerCertSha256 = pinnedPeerCertSha256.removeWhitespace;
    verifyPeerCertByName = verifyPeerCertByName.removeWhitespace;
    echConfigList = echConfigList.removeWhitespace;
    password = password.removeWhitespace;
    shortId = shortId.removeWhitespace;
    mldsa65Verify = mldsa65Verify.removeWhitespace;
    spiderX = spiderX.removeWhitespace;

    _removeWhitespaceExtra();
  }

  void _removeWhitespaceExtra() {
    final newHeaders = <String, String>{};
    headers.forEach((key, value) {
      final newKey = key.removeWhitespace;
      if (newKey.isNotEmpty) {
        final newValue = value.removeWhitespace;
        if (newValue.isNotEmpty) {
          newHeaders[newKey] = newValue;
        }
      }
    });
    headers = newHeaders;

    xPaddingBytes = xPaddingBytes.removeWhitespace;
    scMaxEachPostBytes = scMaxEachPostBytes.removeWhitespace;
    scMinPostsIntervalMs = scMinPostsIntervalMs.removeWhitespace;

    maxConcurrency = maxConcurrency.removeWhitespace;
    maxConnections = maxConnections.removeWhitespace;
    cMaxReuseTimes = cMaxReuseTimes.removeWhitespace;
    hMaxReusableSecs = hMaxReusableSecs.removeWhitespace;
    hMaxRequestTimes = hMaxRequestTimes.removeWhitespace;
    hKeepAlivePeriod = hKeepAlivePeriod.removeWhitespace;

    seqKey = seqKey.removeWhitespace;
    sessionKey = sessionKey.removeWhitespace;
    xPaddingKey = xPaddingKey.removeWhitespace;
    seqPlacement = seqPlacement.removeWhitespace;
    uplinkDataKey = uplinkDataKey.removeWhitespace;
    xPaddingHeader = xPaddingHeader.removeWhitespace;
    xPaddingMethod = xPaddingMethod.removeWhitespace;
    uplinkChunkSize = uplinkChunkSize.removeWhitespace;
    sessionPlacement = sessionPlacement.removeWhitespace;
    uplinkHTTPMethod = uplinkHTTPMethod.removeWhitespace;
    xPaddingPlacement = xPaddingPlacement.removeWhitespace;
    scMaxBufferedPosts = scMaxBufferedPosts.removeWhitespace;
    uplinkDataPlacement = uplinkDataPlacement.removeWhitespace;
    scStreamUpServerSecs = scStreamUpServerSecs.removeWhitespace;
  }

  bool get isBlank {
    if (!_isBlankExtra) {
      return false;
    }

    if (EmptyTool.checkString(address)) {
      return false;
    }
    if (EmptyTool.checkString(port)) {
      return false;
    }

    if (EmptyTool.checkString(xhttpHost)) {
      return false;
    }
    if (EmptyTool.checkString(xhttpPath)) {
      return false;
    }
    if (xhttpMode != XhttpMode.auto) {
      return false;
    }

    if (security != StreamSettingsSecurity.tls) {
      return false;
    }
    if (EmptyTool.checkString(serverName)) {
      return false;
    }
    if (fingerprint != StreamSettingsSecurityFingerprint.none) {
      return false;
    }
    if (EmptyTool.checkString(pinnedPeerCertSha256)) {
      return false;
    }
    if (EmptyTool.checkString(verifyPeerCertByName)) {
      return false;
    }
    if (EmptyTool.checkString(echConfigList)) {
      return false;
    }
    if (EmptyTool.checkString(password)) {
      return false;
    }
    if (EmptyTool.checkString(shortId)) {
      return false;
    }
    if (EmptyTool.checkString(mldsa65Verify)) {
      return false;
    }
    if (EmptyTool.checkString(spiderX)) {
      return false;
    }

    return true;
  }

  bool get _isBlankExtra {
    if (headers.isNotEmpty) {
      return false;
    }
    if (EmptyTool.checkString(xPaddingBytes)) {
      if (xPaddingBytes != "0") {
        return false;
      }
    }

    if (noGRPCHeader) {
      return false;
    }
    if (EmptyTool.checkString(scMaxEachPostBytes)) {
      if (scMaxEachPostBytes != "0") {
        return false;
      }
    }
    if (EmptyTool.checkString(scMinPostsIntervalMs)) {
      if (scMinPostsIntervalMs != "0") {
        return false;
      }
    }

    if (EmptyTool.checkString(maxConcurrency)) {
      if (maxConcurrency != "0") {
        return false;
      }
    }
    if (EmptyTool.checkString(maxConnections)) {
      if (maxConnections != "0") {
        return false;
      }
    }
    if (EmptyTool.checkString(cMaxReuseTimes)) {
      if (cMaxReuseTimes != "0") {
        return false;
      }
    }
    if (EmptyTool.checkString(hMaxReusableSecs)) {
      if (hMaxReusableSecs != "0") {
        return false;
      }
    }
    if (EmptyTool.checkString(hMaxRequestTimes)) {
      if (hMaxRequestTimes != "0") {
        return false;
      }
    }
    if (EmptyTool.checkString(hKeepAlivePeriod)) {
      if (hKeepAlivePeriod != "0") {
        return false;
      }
    }

    if (EmptyTool.checkString(seqKey)) return false;
    if (EmptyTool.checkString(sessionKey)) return false;
    if (noSSEHeader) return false;
    if (EmptyTool.checkString(xPaddingKey)) return false;
    if (EmptyTool.checkString(seqPlacement)) return false;
    if (EmptyTool.checkString(uplinkDataKey)) return false;
    if (EmptyTool.checkString(xPaddingHeader)) return false;
    if (EmptyTool.checkString(xPaddingMethod)) return false;
    if (EmptyTool.checkString(uplinkChunkSize)) return false;
    if (EmptyTool.checkString(sessionPlacement)) return false;
    if (EmptyTool.checkString(uplinkHTTPMethod)) return false;
    if (xPaddingObfsMode) return false;
    if (EmptyTool.checkString(xPaddingPlacement)) return false;
    if (EmptyTool.checkString(scMaxBufferedPosts)) return false;
    if (EmptyTool.checkString(uplinkDataPlacement)) return false;
    if (EmptyTool.checkString(scStreamUpServerSecs)) return false;

    return true;
  }
}
