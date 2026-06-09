import 'package:flutter/widgets.dart';
import 'package:mvmvpn/core/tools/logger.dart';
import 'package:mvmvpn/service/event_bus/enum.dart';
import 'package:mvmvpn/service/event_bus/service.dart';

class DocURLHelper {
  static const _domain = "mvmvpn.com";

  static bool _isRussian() {
    final langCode = AppEventBus.instance.state.languageCode;
    return langCode == LanguageCode.ru ||
        (langCode == LanguageCode.system &&
            WidgetsBinding.instance.platformDispatcher.locale.languageCode == "ru");
  }

  static Uri docUri() {
    var path = "/";
    if (AppEventBus.instance.state.languageCode == LanguageCode.zh) {
      path = "/zh";
    }

    final uri = Uri.https(_domain, path);
    ygLogger("$uri");
    return uri;
  }

  static Uri creditsUri() {
    var path = "/docs/credits/";
    if (AppEventBus.instance.state.languageCode == LanguageCode.zh) {
      path = "/zh/docs/credits/";
    }

    final uri = Uri.https(_domain, path);
    ygLogger("$uri");
    return uri;
  }

  static Uri privacyUri() {
    return Uri.parse("https://vk.com/@mvmvpn-politika-konfidencialnosti");

    var path = "/docs/privacy/";
    if (AppEventBus.instance.state.languageCode == LanguageCode.zh) {
      path = "/zh/docs/privacy/";
    }

    final uri = Uri.https(_domain, path);
    ygLogger("$uri");
    return uri;
  }

  static Uri termsUri() {
    return Uri.parse("https://vk.com/@mvmvpn-polzovatelskoe-soglashenie");

    var path = "/docs/terms/";
    if (AppEventBus.instance.state.languageCode == LanguageCode.zh) {
      path = "/zh/docs/terms/";
    }

    final uri = Uri.https(_domain, path);
    ygLogger("$uri");
    return uri;
  }
}
