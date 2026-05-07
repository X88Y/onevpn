import 'package:flutter/material.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/service/ping/service.dart';
import 'package:delightful_toast/delight_toast.dart';
import 'package:delightful_toast/toast/components/toast_card.dart';
import 'package:delightful_toast/toast/utils/enums.dart';

class ContextAlert {
  static Future<void> showPermissionDialog(BuildContext context) async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(AppLocalizations.of(context)!.homePageOpenSettings),
        actions: <Widget>[
          TextButton(
            child: Text(AppLocalizations.of(context)!.buttonCancel),
            onPressed: () => Navigator.pop(ctx),
          ),
          TextButton(
            child: Text(AppLocalizations.of(context)!.buttonOK),
            onPressed: () {
              Navigator.pop(ctx);
            },
          ),
        ],
      ),
    );
  }

  static Future<void> showPingResultDialog(
    BuildContext context,
    int delay,
  ) async {
    final content = PingService().parsePingResponse(delay);
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppLocalizations.of(context)!.outboundPageRealPingResult),
        content: Text(content),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(AppLocalizations.of(context)!.buttonOK),
          ),
        ],
      ),
    );
  }

  static void showToast(BuildContext context, String message) {
    DelightToastBar(
      autoDismiss: true,
      position: DelightSnackbarPosition.bottom,
      builder: (context) => ToastCard(
        color: const Color(0xFF1E1E1E),
        leading: const Icon(
          Icons.info_outline,
          size: 28,
          color: Colors.white,
        ),
        title: Text(
          message,
          style: const TextStyle(
            fontWeight: FontWeight.w700,
            fontSize: 14,
            color: Colors.white,
          ),
        ),
      ),
    ).show(context);
  }
}
