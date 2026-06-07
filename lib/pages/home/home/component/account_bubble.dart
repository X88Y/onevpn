import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';
import 'package:mvmvpn/pages/main/url.dart';

class AccountBubble extends StatelessWidget {
  final HomeController controller;
  final bool isSmall;
  final bool isLoading;

  const AccountBubble({
    super.key,
    required this.controller,
    this.isSmall = false,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    final size = isSmall ? 36.0 : 46.0;
    final iconSize = isSmall ? 16.0 : 20.0;
    
    return GestureDetector(
      onTap: isLoading ? null : () => _showAccountModal(context, controller),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.white.withOpacity(0.07),
          border: Border.all(color: Colors.white.withOpacity(0.12), width: 1.5),
        ),
        alignment: Alignment.center,
        child: Icon(
          Icons.person_outline_rounded,
          color: Colors.white.withOpacity(0.8),
          size: iconSize,
        ),
      ),
    );
  }

  void _showAccountModal(BuildContext context, HomeController controller) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) {
        return BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF0F1120).withOpacity(0.85),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
              border: Border.all(color: Colors.white.withOpacity(0.1)),
            ),
            padding: EdgeInsets.only(
              bottom: MediaQuery.of(sheetContext).padding.bottom + 20,
              top: 20,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(height: 16),
                ListTile(
                  leading: Icon(Icons.shield_outlined, color: Colors.blueAccent.withOpacity(0.8)),
                  title: Text(
                    AppLocalizations.of(sheetContext)!.privacyPolicy,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
                  ),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    controller.openUrl('https://www.aiverge.net/privacy');
                  },
                ),
                Divider(color: Colors.white.withOpacity(0.08)),
                ListTile(
                  leading: const Icon(Icons.delete_forever_rounded, color: Colors.redAccent),
                  title: Text(
                    AppLocalizations.of(sheetContext)!.mainDeleteAccount,
                    style: const TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600),
                  ),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _showDeleteConfirmation(context, controller);
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showClearDataConfirmation(BuildContext context, HomeController controller) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF0F1120),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: Colors.white.withOpacity(0.1)),
        ),
        title: Row(
          children: [
            Icon(Icons.cleaning_services_rounded, color: Colors.orangeAccent.withOpacity(0.8)),
            const SizedBox(width: 8),
            Text(
              AppLocalizations.of(ctx)!.profileClearAllData,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        content: Text(
          AppLocalizations.of(ctx)!.profileClearAllDataConfirm,
          style: TextStyle(color: Colors.white.withOpacity(0.7), height: 1.4),
        ),
        actions: <Widget>[
          TextButton(
            child: Text(
              AppLocalizations.of(ctx)!.btnCancel,
              style: TextStyle(color: Colors.white.withOpacity(0.6)),
            ),
            onPressed: () => Navigator.pop(ctx),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.orangeAccent,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            child: Text(
              AppLocalizations.of(ctx)!.navClean,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            onPressed: () {
              Navigator.pop(ctx);
              controller.clearAllData();
            },
          ),
        ],
      ),
    );
  }

  void _showDeleteConfirmation(BuildContext context, HomeController controller) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF0F1120),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: Colors.white.withOpacity(0.1)),
        ),
        title: Row(
          children: [
            const Icon(Icons.warning_amber_rounded, color: Colors.redAccent),
            const SizedBox(width: 8),
            Text(
              AppLocalizations.of(ctx)!.mainDeleteAccount,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        content: Text(
          AppLocalizations.of(ctx)!.mainDeleteAccountConfirm,
          style: TextStyle(color: Colors.white.withOpacity(0.7), height: 1.4),
        ),
        actions: <Widget>[
          TextButton(
            child: Text(
              AppLocalizations.of(ctx)!.btnCancel,
              style: TextStyle(color: Colors.white.withOpacity(0.6)),
            ),
            onPressed: () => Navigator.pop(ctx),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.redAccent,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            child: Text(
              AppLocalizations.of(ctx)!.navDelete,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            onPressed: () {
              Navigator.pop(ctx);
              controller.clearAllData(redirectTo: RouterPath.welcome);
            },
          ),
        ],
      ),
    );
  }
}
