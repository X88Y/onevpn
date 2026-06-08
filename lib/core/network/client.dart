import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/core/network/constants.dart';
import 'package:mvmvpn/core/network/model.dart';
import 'package:mvmvpn/core/network/standard.dart';
import 'package:mvmvpn/core/tools/logger.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:uuid/uuid.dart';

class NetClient {
  static final NetClient _singleton = NetClient._internal();

  factory NetClient() => _singleton;

  NetClient._internal() {
    _proxyClient.httpClientAdapter = IOHttpClientAdapter(
      createHttpClient: () {
        final client = HttpClient();
        client.findProxy = (uri) => _proxy;
        return client;
      },
    );
    _downloadClient.httpClientAdapter = IOHttpClientAdapter(
      createHttpClient: () {
        final client = HttpClient();
        client.badCertificateCallback =
            (X509Certificate cert, String host, int port) => true;
        return client;
      },
    );
  }

  //========================
  final _proxyClient = Dio(
    BaseOptions(
      connectTimeout: Duration(seconds: 10),
      receiveTimeout: Duration(seconds: 10),
    ),
  );
  final _downloadClient = Dio(
    BaseOptions(connectTimeout: Duration(seconds: 10)),
  );

  String _proxyPort = "${NetConstants.defaultPingPort}";

  String get _proxy {
    return "PROXY ${NetConstants.proxyHost}:$_proxyPort";
  }

  Future<void> asyncInit() async {
    final packageInfo = await PackageInfo.fromPlatform();
    final userAgent =
        'MVMVpn/${packageInfo.version} (${packageInfo.packageName}; build:${packageInfo.buildNumber}; ${Platform.operatingSystem})';
    final headers = <String, String>{'User-Agent': userAgent};
    _downloadClient.options.headers = headers;
  }

  Future<GeoLocation> connectivityTest(String port, String url) async {
    _proxyPort = port;
    var location = GeoLocationStandard.standard;
    final retryCount = 3;
    for (var i = 0; i < retryCount; i++) {
      try {
        final start = DateTime.now().millisecondsSinceEpoch;
        location = await _geoLocation();
        if (location.ipAddress != null) {
          final end = DateTime.now().millisecondsSinceEpoch;
          location.delay = end - start;
          break;
        } else {
          await Future.delayed(Duration(seconds: 2));
        }
      } catch (e) {
        ygLogger("$e");
      }
    }
    return location;
  }

  final _geoIPUrl = "https://ip-check-perf.radar.cloudflare.com/";

  Future<GeoLocation> _geoLocation() async {
    var location = GeoLocationStandard.standard;
    try {
      final res = await _proxyClient.get<Map<String, dynamic>>(_geoIPUrl);
      if (res.statusCode == 200 && res.data != null) {
        final location = GeoLocation.fromJson(res.data!);
        return location;
      }
    } catch (e) {
      ygLogger("$e");
    }
    return location;
  }

  Future<Map<String, String>> getSubscriptionHeaders() async {
    final packageInfo = await PackageInfo.fromPlatform();
    final key = PreferencesKey();

    // 1. x-device-os
    String deviceOs = '';
    if (Platform.isAndroid) {
      deviceOs = 'Android';
    } else if (Platform.isIOS) {
      deviceOs = 'iOS';
    } else if (Platform.isMacOS) {
      deviceOs = 'macOS';
    } else if (Platform.isWindows) {
      deviceOs = 'Windows';
    } else if (Platform.isLinux) {
      deviceOs = 'Linux';
    } else {
      deviceOs = Platform.operatingSystem;
    }

    // 2. x-hwid
    var hwid = await key.readDeviceUuid();
    if (hwid == null || hwid.isEmpty) {
      try {
        final deviceInfo = DeviceInfoPlugin();
        if (Platform.isAndroid) {
          final androidInfo = await deviceInfo.androidInfo;
          hwid = androidInfo.id;
        } else if (Platform.isIOS) {
          final iosInfo = await deviceInfo.iosInfo;
          hwid = iosInfo.identifierForVendor;
        } else if (Platform.isMacOS) {
          final macosInfo = await deviceInfo.macOsInfo;
          hwid = macosInfo.systemGUID;
        } else if (Platform.isWindows) {
          final windowsInfo = await deviceInfo.windowsInfo;
          hwid = windowsInfo.deviceId;
        } else if (Platform.isLinux) {
          final linuxInfo = await deviceInfo.linuxInfo;
          hwid = linuxInfo.machineId;
        }
      } catch (e) {
        ygLogger("Failed to get native device id: $e");
      }
      if (hwid == null || hwid.isEmpty) {
        hwid = const Uuid().v4();
      }
      await key.saveDeviceUuid(hwid);
    }

    // 3. x-device-locale
    String deviceLocale = 'en';
    try {
      deviceLocale = Platform.localeName.split(RegExp(r'[_]')).first.toLowerCase();
    } catch (_) {}

    // 4. x-ver-os (OS version)
    String verOs = 'unknown';
    try {
      final deviceInfo = DeviceInfoPlugin();
      if (Platform.isAndroid) {
        final info = await deviceInfo.androidInfo;
        verOs = info.version.release;
      } else if (Platform.isIOS) {
        final info = await deviceInfo.iosInfo;
        verOs = info.systemVersion;
      } else if (Platform.isMacOS) {
        final info = await deviceInfo.macOsInfo;
        verOs = info.osRelease;
      } else if (Platform.isWindows) {
        final info = await deviceInfo.windowsInfo;
        verOs = info.deviceId; // fallback or releaseId
      } else if (Platform.isLinux) {
        final info = await deviceInfo.linuxInfo;
        verOs = info.versionId ?? 'unknown';
      }
    } catch (_) {}

    // 5. x-app-version
    final appVersion = packageInfo.version;

    // 6. x-device-model
    String deviceModel = 'unknown';
    try {
      final deviceInfo = DeviceInfoPlugin();
      if (Platform.isAndroid) {
        final info = await deviceInfo.androidInfo;
        deviceModel = info.model;
      } else if (Platform.isIOS) {
        final info = await deviceInfo.iosInfo;
        deviceModel = info.model;
      } else if (Platform.isMacOS) {
        final info = await deviceInfo.macOsInfo;
        deviceModel = info.model;
      } else if (Platform.isWindows) {
        final info = await deviceInfo.windowsInfo;
        deviceModel = info.productName;
      } else if (Platform.isLinux) {
        final info = await deviceInfo.linuxInfo;
        deviceModel = info.name;
      }
    } catch (_) {}

    // 7. user-agent: e.g. Happ/4.10.2/macos
    final userAgent = 'MVMVpn/$appVersion/${deviceOs.toLowerCase()}';

    // 8. accept-language
    final sysLocale = Platform.localeName.replaceAll('_', '-');
    final acceptLanguage = '$sysLocale,${sysLocale.split('-').first};q=0.9';

    return {
      'x-device-os': deviceOs,
      'x-hwid': hwid,
      'x-device-locale': deviceLocale,
      'priority': 'u=3',
      'accept-encoding': 'gzip, deflate, br',
      'accept-language': acceptLanguage,
      'user-agent': userAgent,
      'x-ver-os': verOs,
      'x-app-version': appVersion,
      'x-device-model': deviceModel,
    };
  }

  Future<String?> getText(String url, {Map<String, String>? headers}) async {
    try {
      final res = await _downloadClient.get<String>(
        url,
        options: Options(
          responseType: ResponseType.plain,
          headers: headers,
        ),
      );
      return res.data;
    } catch (e) {
      ygLogger("$e");
      return null;
    }
  }

  Future<Response<String>?> getTextResponse(String url, {Map<String, String>? headers}) async {
    try {
      final res = await _downloadClient.get<String>(
        url,
        options: Options(
          responseType: ResponseType.plain,
          headers: headers,
        ),
      );
      return res;
    } catch (e) {
      ygLogger("$e");
      return null;
    }
  }


  Future<bool> downloadFile(String url, String savePath) async {
    try {
      await _downloadClient.download(url, savePath);
      return true;
    } catch (e) {
      ygLogger("$e");
      return false;
    }
  }

  Future<bool> checkGoogle({String? port, HttpClient? client}) async {
    final httpClient = client ?? (HttpClient()
      ..connectionTimeout = const Duration(seconds: 2));
    if (port != null) {
      httpClient.findProxy = (uri) => "PROXY ${NetConstants.proxyHost}:$port";
    }
    try {
      final request = await httpClient.getUrl(Uri.parse("https://www.google.com/generate_204"));
      final response = await request.close().timeout(const Duration(seconds: 3));
      ygLogger("checkGoogle response: ${response.statusCode} (port: $port)");
      return response.statusCode == 204;
    } catch (e) {
      ygLogger("checkGoogle error: $e (port: $port)");
      return false;
    } finally {
      httpClient.close();
    }
  }
}
