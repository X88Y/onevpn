import 'package:flutter/foundation.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:mvmvpn/core/tools/logger.dart';

class AdsService {
  static final AdsService _singleton = AdsService._internal();

  factory AdsService() => _singleton;

  AdsService._internal();

  static String get adUnitId {
    return '';
  }

  Future<void> init() async {}

  void dispose() {}

  Future<bool> get canRequestAds async {
    return false;
  }
}
