import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/home/home/controller.dart';

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
      onTap: isLoading ? null : () => _showAccountModal(context, controller, showDelete: !isSmall),
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

  void _showAccountModal(BuildContext context, HomeController controller, {required bool showDelete}) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) {
        return BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF0F1120).withOpacity(0.8),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
              border: Border.all(color: Colors.white.withOpacity(0.1)),
            ),
            padding: EdgeInsets.only(
              bottom: MediaQuery.of(context).padding.bottom + 20,
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
                if (showDelete) ...[
                  ListTile(
                    leading: const Icon(Icons.delete_forever_rounded, color: Colors.redAccent),
                    title: Text(
                      AppLocalizations.of(context)!.homeDeleteAccount,
                      style: const TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600),
                    ),
                    onTap: () {
                      Navigator.pop(context);
                      controller.clearAllData();
                    },
                  ),
                  Divider(color: Colors.white.withOpacity(0.08)),
                ],
                ListTile(
                  leading: Icon(Icons.description_outlined, color: Colors.white.withOpacity(0.7)),
                  title: Text(
                    AppLocalizations.of(context)!.homeThirdPartyLicense,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
                  ),
                  onTap: () {
                    Navigator.pop(context);
                    controller.openUrl('https://front-redirect.vercel.app/license');
                  },
                ),
                ListTile(
                  leading: Icon(Icons.privacy_tip_outlined, color: Colors.white.withOpacity(0.7)),
                  title: Text(
                    AppLocalizations.of(context)!.homeTerms,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
                  ),
                  onTap: () {
                    Navigator.pop(context);
                    controller.openUrl('https://www.aiverge.net/terms');
                  },
                ),
                ListTile(
                  leading: Icon(Icons.shield_outlined, color: Colors.white.withOpacity(0.7)),
                  title: Text(
                    AppLocalizations.of(context)!.homePrivacy,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
                  ),
                  onTap: () {
                    Navigator.pop(context);
                    controller.openUrl('https://www.aiverge.net/privacy');
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
