import 'package:flutter/material.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/setting/log/controller.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/service/xray/constants.dart';

class LogPage extends StatelessWidget {
  const LogPage({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = LogController.instance;
    return Scaffold(
      appBar: AppBar(title: Text(AppLocalizations.of(context)!.logScreenTitle)),
      body: SafeArea(child: _body(context, controller)),
    );
  }

  Widget _body(BuildContext context, LogController controller) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: SingleChildScrollView(
        child: Column(
          children: [
            _logSection(context, controller),
            _configSection(context, controller),
          ],
        ),
      ),
    );
  }

  Widget _logSection(BuildContext context, LogController controller) {
    return SectionView(
      title: AppLocalizations.of(context)!.logScreenLogFile,
      child: Column(
        children: [
          ListTile(
            title: Text(AppLocalizations.of(context)!.logScreenAccess),
            trailing: IconMenuPicker(
              icon: Icons.more_vert,
              menus: [
                if (!AppPlatform.isLinux) IconMenuId.share,
                IconMenuId.save,
              ],
              callback: (menuId) => controller.moreAction(
                context,
                XrayStateConstants.accessLogPath,
                menuId,
              ),
            ),
          ),
          ListTile(
            title: Text(AppLocalizations.of(context)!.logScreenError),
            trailing: IconMenuPicker(
              icon: Icons.more_vert,
              menus: [
                if (!AppPlatform.isLinux) IconMenuId.share,
                IconMenuId.save,
              ],
              callback: (menuId) => controller.moreAction(
                context,
                XrayStateConstants.errorLogPath,
                menuId,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _configSection(BuildContext context, LogController controller) {
    return SectionView(
      title: "",
      child: Column(
        children: [
          ListTile(
            onTap: () => controller.gotoXrayConfigFile(context),
            title: Text(AppLocalizations.of(context)!.logScreenXrayConfig),
          ),
        ],
      ),
    );
  }
}
