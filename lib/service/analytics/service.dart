import 'package:mvmvpn/core/tools/platform.dart';

class AnalyticsService {
  static final AnalyticsService _singleton = AnalyticsService._internal();

  factory AnalyticsService() => _singleton;

  AnalyticsService._internal();

  void init() {
  }

  void dispose() {}

  void logEvent(String name) {
  }
}
