import 'dart:async';

import 'package:dio/dio.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/network/client.dart';
import 'package:mvmvpn/service/db/config_writer.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/localizations/service.dart';
import 'package:mvmvpn/service/ping/service.dart';
import 'package:mvmvpn/service/share/protocol.dart';
import 'package:mvmvpn/service/share/xray_share_reader.dart';
import 'package:mvmvpn/service/sub_update/state.dart';
import 'package:mvmvpn/service/toast/service.dart';

String? extractSubscriptionKey(String url) {
  try {
    final uri = Uri.tryParse(url.trim());
    if (uri == null) return null;
    final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    if (segments.isNotEmpty) {
      return segments.last;
    }
    if (!url.contains('/')) {
      return url.trim();
    }
  } catch (_) {}
  return null;
}

class SubscriptionService {
  static final SubscriptionService _singleton = SubscriptionService._internal();

  factory SubscriptionService() => _singleton;

  SubscriptionService._internal();

  Future<int> insertSubscription(
    String name,
    String url,
    bool showLoading,
  ) async {
    final eventBus = AppEventBus.instance;
    if (showLoading) {
      eventBus.updateDownloading(true);
    }

    final headers = await NetClient().getSubscriptionHeaders();
    final candidates = [url];
    final key = extractSubscriptionKey(url);
    if (key != null && key.isNotEmpty) {
      final fallbackDomains = [
        'https://xn--80ac0c.xn----ctbzfboapgel4j.xn--p1ai',
        'https://jl1x2z77a9.cdn.twcstorage.ru',
        'https://hd6458sp7z.cdn.twcstorage.ru',
        'https://gpy4me9ehp.cdn.twcstorage.ru',
      ];
      for (final domain in fallbackDomains) {
        final fallbackUrl = '$domain/$key';
        if (!candidates.contains(fallbackUrl)) {
          candidates.add(fallbackUrl);
        }
      }
    }

    Response<String>? response;
    String? workingUrl;
    List<CoreConfigCompanion> rows = [];

    for (final candidateUrl in candidates) {
      try {
        final res = await NetClient().getTextResponse(candidateUrl, headers: headers);
        if (res != null && res.data != null) {
          final text = res.data;
          final parsed = await _readConfigs(text);
          if (parsed.isNotEmpty) {
            response = res;
            workingUrl = candidateUrl;
            rows = parsed;
            break;
          }
        }
      } catch (e) {
        print('Error trying candidate URL $candidateUrl: $e');
      }
    }

    if (workingUrl == null || response == null) {
      if (showLoading) {
        ToastService().showToast(appLocalizationsNoContext().loginErrorInvalidKey);
        eventBus.updateDownloading(false);
      }
      return 0;
    }

    _checkSubscriptionExpiry(response.headers);

    final db = AppDatabase();
    final existingSubs = await db.subscriptionDao.allRows;
    SubscriptionData? existing;
    for (var sub in existingSubs) {
      if (sub.url == url || sub.url == workingUrl) {
        existing = sub;
        break;
      }
    }

    if (existing != null) {
      final count = await refreshSubscription(existing, false);
      if (showLoading) {
        eventBus.updateDownloading(false);
      }
      return count;
    }

    var count = 0;
    if (rows.isNotEmpty) {
      final row = SubscriptionCompanion.insert(
        name: name,
        url: workingUrl,
        timestamp: DateTime.now(),
        count: rows.length,
        expanded: true,
      );
      final subId = await db.subscriptionDao.insertRow(row);
      if (subId > DBConstants.defaultId) {
        count = await ConfigWriter.writeRows(rows, subId);
      }
    }
    if (showLoading) {
      eventBus.updateDownloading(false);
    }

    return count;
  }

  Future<void> updateSubscription(int id, String name) async {
    final sub = await AppDatabase().subscriptionDao.searchRow(id);
    if (sub != null) {
      final newRow = sub.copyWith(name: name);
      await AppDatabase().subscriptionDao.updateRow(newRow);
    }
  }

  Future<int> refreshSubscription(
    SubscriptionData subscription,
    bool showLoading,
  ) async {
    final eventBus = AppEventBus.instance;
    if (showLoading) {
      eventBus.updateDownloading(true);
    }
    final headers = await NetClient().getSubscriptionHeaders();

    final candidates = [subscription.url];
    final key = extractSubscriptionKey(subscription.url);
    if (key != null && key.isNotEmpty) {
      final fallbackDomains = [
        'https://xn--80ac0c.xn----ctbzfboapgel4j.xn--p1ai',
        'https://jl1x2z77a9.cdn.twcstorage.ru',
        'https://hd6458sp7z.cdn.twcstorage.ru',
        'https://gpy4me9ehp.cdn.twcstorage.ru',
      ];
      for (final domain in fallbackDomains) {
        final fallbackUrl = '$domain/$key';
        if (!candidates.contains(fallbackUrl)) {
          candidates.add(fallbackUrl);
        }
      }
    }

    Response<String>? response;
    String? workingUrl;
    List<CoreConfigCompanion> rows = [];

    for (final candidateUrl in candidates) {
      try {
        final res = await NetClient().getTextResponse(candidateUrl, headers: headers);
        if (res != null && res.data != null) {
          final text = res.data;
          final parsed = await _readConfigs(text);
          if (parsed.isNotEmpty) {
            response = res;
            workingUrl = candidateUrl;
            rows = parsed;
            break;
          }
        }
      } catch (e) {
        print('Error trying candidate URL $candidateUrl: $e');
      }
    }

    if (workingUrl == null || response == null) {
      if (showLoading) {
        ToastService().showToast(appLocalizationsNoContext().loginErrorInvalidKey);
        eventBus.updateDownloading(false);
      }
      return 0;
    }

    _checkSubscriptionExpiry(response.headers);

    var count = 0;
    if (rows.isNotEmpty) {
      final db = AppDatabase();
      await db.subscriptionDao.deleteConfigs(subscription.id);
      count = await ConfigWriter.writeRows(rows, subscription.id);
      final newRow = subscription.copyWith(
        url: workingUrl,
        timestamp: DateTime.now(),
        count: count,
      );
      await db.subscriptionDao.updateRow(newRow);
      await _autoPing(subscription.id);
    }
    if (showLoading) {
      eventBus.updateDownloading(false);
    }
    return count;
  }

  Future<List<CoreConfigCompanion>> _readConfigs(String? text) async {
    if (text == null) {
      return [];
    }
    final url = text.trim();
    if (AppShareService().checkAppShare(url)) {
      final result = await AppShareService().parseShareText(
        url,
        skipSubscription: true,
      );
      return result.item1;
    } else {
      return XrayShareReader().parseShareText(url);
    }
  }

  Future<void> refreshAllSubscription() async {
    final eventBus = AppEventBus.instance;
    eventBus.updateDownloading(true);

    final db = AppDatabase();
    final subscriptions = await db.subscriptionDao.allRows;
    for (final subscription in subscriptions) {
      await refreshSubscription(subscription, false);
    }
    eventBus.updateDownloading(false);
  }

  Future<void> refreshOutdatedSubscription() async {
    final eventBus = AppEventBus.instance;
    eventBus.updateDownloading(true);

    final subUpdateState = SubUpdateState();
    await subUpdateState.readFromPreferences();
    if (!subUpdateState.enable) {
      eventBus.updateDownloading(false);
      return;
    }
    final interval = subUpdateState.interval.value;
    final subs = await AppDatabase().subscriptionDao.allRows;
    final now = DateTime.now();
    for (final sub in subs) {
      if (now.difference(sub.timestamp).inHours >= interval) {
        await refreshSubscription(sub, false);
      }
    }

    eventBus.updateDownloading(false);
  }

  Future<void> _autoPing(int subId) async {
    final subUpdateState = SubUpdateState();
    await subUpdateState.readFromPreferences();
    if (subUpdateState.autoPing) {
      await PingService().pingOutboundConfigs(subId);
    }
  }

  void _checkSubscriptionExpiry(Headers headers) {
    final userInfo = headers.value('subscription-userinfo');
    if (userInfo != null) {
      final parts = userInfo.split(';');
      bool isExpired = false;
      for (var part in parts) {
        part = part.trim();
        if (part.startsWith('expire=')) {
          final valStr = part.substring('expire='.length).trim();
          final expireSeconds = int.tryParse(valStr);
          if (expireSeconds != null) {
            final expireDateTime = DateTime.fromMillisecondsSinceEpoch(expireSeconds * 1000, isUtc: true);
            final nowUtc = DateTime.now().toUtc();
            if (nowUtc.isAfter(expireDateTime)) {
              isExpired = true;
            }
          }
        }
      }
      AppEventBus.instance.updateSubscriptionExpired(isExpired);
      if (isExpired) {
        ToastService().showToast(appLocalizationsNoContext().subscriptionExpiredNeedUpdate);
      }
    }
  }
}
