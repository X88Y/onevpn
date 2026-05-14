import 'dart:ffi';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:mvmvpn/service/localizations/service.dart';

enum ThemeCode {
  system("system"),
  light("light"),
  dark("dark");

  const ThemeCode(this.name);

  final String name;

  @override
  String toString() {
    switch (this) {
      case ThemeCode.system:
        return appLocalizationsNoContext().themeScreenSystem;
      case ThemeCode.light:
        return appLocalizationsNoContext().themeScreenLight;
      case ThemeCode.dark:
        return appLocalizationsNoContext().themeScreenDark;
    }
  }

  static ThemeCode fromString(String? name) {
    if (name == null) {
      return ThemeCode.system;
    }
    final theme = ThemeCode.values.firstWhereOrNull(
      (value) => value.name == name,
    );
    if (theme == null) {
      return ThemeCode.system;
    }
    return theme;
  }

  ThemeMode get themeMode {
    switch (this) {
      case ThemeCode.light:
        return ThemeMode.light;
      case ThemeCode.dark:
        return ThemeMode.dark;
      case ThemeCode.system:
        return ThemeMode.system;
    }
  }
}

enum LanguageCode {
  system("system"),
  en("en"),
  ru("ru"),
  fa("fa"),
  zh("zh");

  const LanguageCode(this.name);

  final String name;

  @override
  String toString() {
    switch (this) {
      case LanguageCode.system:
        return appLocalizationsNoContext().languageScreenSystem;
      case LanguageCode.en:
        return appLocalizationsNoContext().languageScreenEnglish;
      case LanguageCode.ru:
        return appLocalizationsNoContext().languageScreenRussian;
      case LanguageCode.fa:
        return appLocalizationsNoContext().languageScreenPersian;
      case LanguageCode.zh:
        return appLocalizationsNoContext().languageScreenChinese;
    }
  }

  static LanguageCode fromString(String? name) {
    if (name == null) {
      return LanguageCode.system;
    }
    final value = LanguageCode.values.firstWhereOrNull(
      (value) => value.name == name,
    );
    if (value != null) {
      return value;
    }
    return LanguageCode.system;
  }

  Locale get locale {
    Locale current;
    switch (this) {
      case LanguageCode.system:
        final deviceLocale =
            WidgetsBinding.instance.platformDispatcher.locale;
        current = deviceLocale;
        break;
      default:
        current = Locale(name);
        break;
    }
    return _checkCJKLocale(current);
  }

  Locale _checkCJKLocale(Locale locale) {
    if (locale.languageCode == "zh" ||
        locale.languageCode == "ja" ||
        locale.languageCode == "ko") {
      if (AppPlatform.isLinux && Abi.current() == Abi.linuxArm64) {
        return Locale(LanguageCode.en.name);
      }
    }
    return locale;
  }

  TextDirection get textDirection {
    switch (this) {
      case LanguageCode.ru:
        return TextDirection.ltr;
      case LanguageCode.en:
        return TextDirection.ltr;
      case LanguageCode.fa:
        return TextDirection.rtl;
      case LanguageCode.zh:
        return TextDirection.ltr;
      case LanguageCode.system:
        final locale =
            WidgetsBinding.instance.platformDispatcher.locale;
        final rtlLanguages = <String>[
          'ar', // Arabic
          'fa', // Persian
          'he', // Hebrew
          'ur', // Urdu
        ];
        if (rtlLanguages.contains(locale.languageCode.toLowerCase())) {
          return TextDirection.rtl;
        }
        return TextDirection.ltr;
    }
  }
}
