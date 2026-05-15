import 'dart:async';


import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';


import 'package:mvmvpn/core/tools/logger.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/main/url.dart';
import 'package:mvmvpn/service/localizations/service.dart';
import 'package:mvmvpn/service/db/config_writer.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/share/protocol.dart';
import 'package:mvmvpn/service/share/xray_share_reader.dart';
import 'package:mvmvpn/service/toast/service.dart';


final class ShareService {
  static final ShareService _singleton = ShareService._internal();

  factory ShareService() => _singleton;

  ShareService._internal();

  //==========================

  void init() {
    final appLinks = AppLinks();
    appLinks.getInitialLink().then((uri) {
      if (uri != null) {
        _readDeepLink(uri);
      }
    });
    _deepLinkSubscription = appLinks.uriLinkStream.listen(
      (uri) => _readDeepLink(uri),
    );
  }

  void dispose() {
    _deepLinkSubscription.cancel();
  }

  late StreamSubscription<Uri> _deepLinkSubscription;

  Future<void> _readDeepLink(Uri uri) async {
    await readShareText(uri.toString());
  }


  Future<void> pickFile() async {}

  Future<void> readPasteboard() async {
    final hasStrings = await Clipboard.hasStrings();
    if (!hasStrings) {
      ToastService().showToast(
        appLocalizationsNoContext().mainOutboundViewNoValidConfig,
      );
      return;
    }
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    if (data == null) {
      ToastService().showToast(
        appLocalizationsNoContext().mainOutboundViewNoValidConfig,
      );
      return;
    }

    final text = data.text;
    if (text == null) {
      ToastService().showToast(
        appLocalizationsNoContext().mainOutboundViewNoValidConfig,
      );
      return;
    }
    await readShareText(text);
  }

  Future<void> readShareText(String? text) async {
    var success = false;
    if (text != null) {
      final eventBus = AppEventBus.instance;
      eventBus.updateDownloading(true);
      final url = text.trim();
      if (AppShareService().checkAppShare(url)) {
        final result = await AppShareService().parseShareText(url);
        final rows = result.item1;
        if (rows.isNotEmpty) {
          await ConfigWriter.writeRows(rows, null);
        }
        success = result.item2;
      } else if (url.startsWith("https://")) {
        final uri = Uri.tryParse(url);
        if (uri != null) {
          success = await AppShareService().addSubscription(
            url,
            uri.fragment,
            false,
          );
        }
      } else {
        final rows = await XrayShareReader().parseShareText(url);
        if (rows.isNotEmpty) {
          final res = await ConfigWriter.writeRows(rows, null);
          if (res > 0) {
            success = true;
          }
        }
      }
      eventBus.updateDownloading(false);
    }

    if (success) {
      await _showImportResultDialog(
        appLocalizationsNoContext().mainOutboundViewImportSuccess,
      );
    } else {
      await _showImportResultDialog(
        appLocalizationsNoContext().mainOutboundViewNoValidConfig,
      );
    }
  }

  Future<void> _showImportResultDialog(String message) async {
    final context = rootNavigatorKey.currentContext;
    if (context != null && context.mounted) {
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text(AppLocalizations.of(ctx)!.btnOK),
            ),
          ],
        ),
      );
    }
  }
}
