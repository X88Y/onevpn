import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/setting/backup/controller.dart';
import 'package:mvmvpn/pages/widget/bottom_button.dart';
import 'package:mvmvpn/pages/widget/bottom_view.dart';
import 'package:mvmvpn/pages/widget/date_view.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/service/event_bus/service.dart';

class BackupPage extends StatelessWidget {
  const BackupPage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => BackupController(),
      child: BlocBuilder<BackupController, BackupState>(
        builder: (context, state) {
          final controller = context.read<BackupController>();
          return Scaffold(
            appBar: AppBar(
              title: Text(AppLocalizations.of(context)!.backupScreenTitle),
              actions: [
                IconButton(
                  onPressed: () => controller.importBackup(context),
                  icon: Icon(Icons.add),
                ),
              ],
            ),
            body: SafeArea(child: _body(context, state, controller)),
          );
        },
      ),
    );
  }

  Widget _body(
    BuildContext context,
    BackupState state,
    BackupController controller,
  ) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: Column(
        children: [
          Expanded(child: _fileList(context, state, controller)),
          _bottomButton(context, state, controller),
        ],
      ),
    );
  }

  Widget _fileList(
    BuildContext context,
    BackupState state,
    BackupController controller,
  ) {
    if (state.files.isEmpty) {
      return Center(
        child: Text(AppLocalizations.of(context)!.backupScreenNoFiles),
      );
    } else {
      return RadioGroup<String>(
        groupValue: state.selection,
        onChanged: (value) => controller.updateSelection(value),
        child: ListView.separated(
          itemBuilder: (ctx, index) =>
              _itemRow(ctx, state, controller, index),
          itemCount: state.files.length,
          separatorBuilder: (_, _) => const Divider(),
        ),
      );
    }
  }

  Widget _itemRow(
    BuildContext context,
    BackupState state,
    BackupController controller,
    int index,
  ) {
    final file = state.files[index];
    return RadioListTile(
      toggleable: true,
      value: file.name,
      title: Text(file.name),
      subtitle: DateView(date: file.timestamp!),
      secondary: IconMenuPicker(
        icon: Icons.more_vert,
        menus: [
          if (!AppPlatform.isLinux) IconMenuId.share,
          IconMenuId.save,
          IconMenuId.delete,
        ],
        callback: (menuId) => controller.moreAction(context, file, menuId),
      ),
    );
  }

  Widget _bottomButton(
    BuildContext context,
    BackupState state,
    BackupController controller,
  ) {
    final eventBus = AppEventBus.instance;
    if (eventBus.state.downloading) {
      return const CircularProgressIndicator();
    } else {
      return BottomView(
        child: Row(
          spacing: 12,
          children: [
            if (state.selection.isEmpty)
              Expanded(
                child: SecondaryBottomButton(
                  title: AppLocalizations.of(context)!.backupScreenRestore,
                  callback: null,
                ),
              )
            else
              Expanded(
                child: SecondaryBottomButton(
                  title: AppLocalizations.of(context)!.backupScreenRestore,
                  callback: () => controller.restore(context),
                ),
              ),
            Expanded(
              child: PrimaryBottomButton(
                title: AppLocalizations.of(context)!.backupScreenBackup,
                callback: () => controller.backup(context),
              ),
            ),
          ],
        ),
      );
    }
  }
}
