import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:window_manager/window_manager.dart';

final class WindowService with WindowListener {
  static final WindowService _singleton = WindowService._internal();

  factory WindowService() => _singleton;

  WindowService._internal();

  //==========================

  Future<void> asyncInit() async {
    if (!AppPlatform.isDesktop) {
      return;
    }
    await windowManager.setPreventClose(true);
    windowManager.addListener(this);

    final hideDockIcon = await PreferencesKey().readHideDockIcon();
    await windowManager.setSkipTaskbar(hideDockIcon);
  }

  void dispose() {
    if (!AppPlatform.isDesktop) {
      return;
    }
    windowManager.removeListener(this);
  }

  @override
  Future<void> onWindowClose() async {
    super.onWindowClose();
    await windowManager.hide();
    final eventBus = AppEventBus.instance;
    eventBus.updateWindowClosed(true);
  }

  @override
  void onWindowFocus() {
    super.onWindowFocus();
    final eventBus = AppEventBus.instance;
    eventBus.updateWindowClosed(false);
  }
}
