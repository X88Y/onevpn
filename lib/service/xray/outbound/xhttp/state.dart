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

  var downloadSettings = XhttpDownloadState();
}

