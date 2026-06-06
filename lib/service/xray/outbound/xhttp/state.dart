import 'package:mvmvpn/service/xray/outbound/xhttp/download/state.dart';

class XhttpExtraState {
  var headers = <String, String>{};
  var xPaddingBytes = "";
  var noGRPCHeader = false;
  var scMaxEachPostBytes = "";
  var scMinPostsIntervalMs = "";

  var maxConcurrency = "0";
  var maxConnections = "0";
  var cMaxReuseTimes = "0";
  var hMaxReusableSecs = "0";
  var hMaxRequestTimes = "0";
  var hKeepAlivePeriod = "0";

  var seqKey = "";
  var sessionKey = "";
  var noSSEHeader = false;
  var xPaddingKey = "";
  var seqPlacement = "";
  var uplinkDataKey = "";
  var xPaddingHeader = "";
  var xPaddingMethod = "";
  var uplinkChunkSize = "";
  var sessionPlacement = "";
  var uplinkHTTPMethod = "";
  var xPaddingObfsMode = false;
  var xPaddingPlacement = "";
  var scMaxBufferedPosts = "";
  var uplinkDataPlacement = "";
  var scStreamUpServerSecs = "";

  /// PR #6258 – ASCII character table used to generate session IDs.
  /// Predefined presets: "base62", "hex", "HEX".
  var sessionIDTable = "";

  /// PR #6258 – session-ID length range, stored as a range string "min-max"
  /// or a bare integer string (e.g. "12" or "8-16").
  var sessionIDLength = "";

  var downloadSettings = XhttpDownloadState();
}

