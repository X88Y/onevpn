import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/tools/extensions.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/mixin/alert.dart';
import 'package:mvmvpn/service/ping/state.dart';

class PingPageState {
  final PingState pingState;

  PingPageState({PingState? pingState}) : pingState = pingState ?? PingState();

  PingPageState _copy() {
    return PingPageState(pingState: pingState);
  }
}

class PingController extends Cubit<PingPageState> {
  PingController() : super(PingPageState()) {
    _readPingState();
  }

  final customUrlController = TextEditingController();

  Future<void> _readPingState() async {
    final pingState = PingState();
    await pingState.readFromPreferences();
    emit(PingPageState(pingState: pingState));
    customUrlController.text = pingState.customUrl;
  }

  void updateTimeout(double value) {
    state.pingState.timeout = value;
    emit(state._copy());
  }

  void updateConcurrency(double value) {
    state.pingState.concurrency = value;
    emit(state._copy());
  }

  void updateUrl(String value) {
    final url = PingUrl.fromString(value);
    if (url != null) {
      state.pingState.url = url;
      emit(state._copy());
    }
  }

  Future<void> save(BuildContext context) async {
    final url = customUrlController.text.removeWhitespace;
    if (state.pingState.url == PingUrl.custom) {
      if (url.isEmpty) {
        ContextAlert.showToast(
          context,
          AppLocalizations.of(context)!.appValidationUrlRequired,
        );
        return;
      }
      final uri = Uri.tryParse(url);
      if (uri == null) {
        ContextAlert.showToast(
          context,
          AppLocalizations.of(context)!.appValidationUrlInvalid,
        );
        return;
      }
    }
    state.pingState.customUrl = url;

    await state.pingState.saveToPreferences();
    if (context.mounted) {
      context.pop();
    }
  }

  @override
  Future<void> close() {
    customUrlController.dispose();
    return super.close();
  }
}
