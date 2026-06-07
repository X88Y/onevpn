import 'dart:async';
import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/db/database/enum.dart';
import 'package:mvmvpn/core/tools/empty.dart';
import 'package:mvmvpn/service/localizations/service.dart';
import 'package:mvmvpn/service/ping/state.dart';
import 'package:mvmvpn/service/xray/outbound/state.dart';
import 'package:mvmvpn/service/xray/outbound/state_ping.dart';
import 'package:mvmvpn/service/xray/outbound/state_reader.dart';
import 'package:mvmvpn/service/xray/raw/ping.dart';

class PingService {
  static final PingService _singleton = PingService._internal();

  factory PingService() => _singleton;

  PingService._internal();

  Future<void> pingOutboundConfigs(int subId) async {
    final eventBus = AppEventBus.instance;
    eventBus.updatePinging(true);
    final db = AppDatabase();
    final rows = await db.coreConfigDao.allOutboundRowsWithDataBySubId(subId);
    await _pingConfigs(db, rows);
    eventBus.updatePinging(false);
  }

  Future<void> pingAllConfigs() async {
    final eventBus = AppEventBus.instance;
    eventBus.updatePinging(true);
    final db = AppDatabase();
    final subscriptions = await db.subscriptionDao.allRows;
    final allSubIds = [DBConstants.defaultId, ...subscriptions.map((s) => s.id)];
    
    final allRows = <CoreConfigData>[];
    for (final subId in allSubIds) {
      final outboundRows = await db.coreConfigDao.allOutboundRowsWithDataBySubId(subId);
      final rawRows = await db.coreConfigDao.allRawRowsWithDataBySubId(subId);
      allRows.addAll(outboundRows);
      allRows.addAll(rawRows);
    }
    
    if (allRows.isNotEmpty) {
      await _pingConfigs(db, allRows);
    }
    eventBus.updatePinging(false);
  }

  Future<void> pingConfigs(List<CoreConfigData> rows, {int pingCount = 1}) async {
    final eventBus = AppEventBus.instance;
    eventBus.updatePinging(true);
    final db = AppDatabase();
    if (rows.isNotEmpty) {
      await _pingConfigs(db, rows, pingCount: pingCount);
    }
    eventBus.updatePinging(false);
  }

  Future<int> _pingOutbound(CoreConfigData row, PingState pingState) async {
    if (EmptyTool.checkString(row.data)) {
      final outbound = OutboundState();
      outbound.readFromDbData(row);
      return outbound.ping(pingState);
    }
    return PingDelayConstants.unknown;
  }

  Future<void> pingRawConfigs(int subId) async {
    final eventBus = AppEventBus.instance;
    eventBus.updatePinging(true);
    final db = AppDatabase();
    final rows = await db.coreConfigDao.allRawRowsWithDataBySubId(subId);
    await _pingConfigs(db, rows);
    eventBus.updatePinging(false);
  }

  Future<int> _pingRawConfig(CoreConfigData row, PingState pingState) async {
    if (EmptyTool.checkString(row.data)) {
      final bytes = base64Decode(row.data!);
      final text = utf8.decode(bytes);
      return XrayRawPing.ping(text, pingState);
    }
    return PingDelayConstants.unknown;
  }

  Future<void> _pingConfigs(AppDatabase db, List<CoreConfigData> rows, {int pingCount = 1}) async {
    final pingState = PingState();
    await pingState.readFromPreferences();
    var concurrency = pingState.concurrency.toInt();
    if (AppPlatform.isLinux || AppPlatform.isWindows) {
      concurrency = 1;
    }
    final slices = rows.slices(concurrency);
    for (final slice in slices) {
      final futures = <Future<void>>[];
      for (final row in slice) {
        futures.add(_pingAndSaveConfig(db, row, pingState, pingCount));
      }
      await Future.wait(futures);
    }
  }

  Future<void> _pingAndSaveConfig(
    AppDatabase db,
    CoreConfigData row,
    PingState pingState,
    int pingCount,
  ) async {
    final type = CoreConfigType.fromString(row.type);
    if (type == null) return;

    Future<int> runSinglePing() {
      if (type == CoreConfigType.outbound) {
        return _pingOutbound(row, pingState);
      } else if (type == CoreConfigType.raw) {
        return _pingRawConfig(row, pingState);
      }
      return Future.value(PingDelayConstants.unknown);
    }

    if (pingCount <= 1) {
      final res = await runSinglePing();
      await _updateRow(db, row, res);
      return;
    }

    int? bestDelay;
    int completedCount = 0;
    bool hasSuccess = false;

    final List<Future<void>> pingFutures = List.generate(pingCount, (_) async {
      try {
        final delay = await runSinglePing();
        completedCount++;

        if (delay < 9000) {
          if (!hasSuccess || delay < bestDelay!) {
            bestDelay = delay;
            hasSuccess = true;
            await _updateRow(db, row, delay);
          }
        } else {
          if (!hasSuccess && completedCount == pingCount) {
            await _updateRow(db, row, delay);
          }
        }
      } catch (e) {
        completedCount++;
        if (!hasSuccess && completedCount == pingCount) {
          await _updateRow(db, row, PingDelayConstants.error);
        }
      }
    });

    await Future.wait(pingFutures);
  }

  Future<void> _updateRow(AppDatabase db, CoreConfigData row, int delay) async {
    var newRow = row;
    if (delay != PingDelayConstants.unknown) {
      newRow = newRow.copyWith(delay: delay);
    }
    await db.coreConfigDao.updateRow(newRow);
  }

  String parsePingResponse(int delay) {
    var content = "";
    switch (delay) {
      case PingDelayConstants.timeout:
        content = appLocalizationsNoContext().appPingTimeout;
        break;
      case PingDelayConstants.error:
        content = "error";
        break;
      default:
        content = "${delay}ms";
        break;
    }

    return content;
  }
}
