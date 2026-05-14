import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/core/tools/extensions.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/mixin/alert.dart';
import 'package:mvmvpn/pages/subscription/edit/params.dart';
import 'package:mvmvpn/service/subscription/service.dart';

class SubscriptionEditState {
  final String url;

  const SubscriptionEditState({required this.url});

  factory SubscriptionEditState.initial() =>
      const SubscriptionEditState(url: "");

  SubscriptionEditState copyWith({String? url}) {
    return SubscriptionEditState(url: url ?? this.url);
  }
}

class SubscriptionEditController extends Cubit<SubscriptionEditState> {
  final SubscriptionEditParams params;
  SubscriptionEditController(this.params)
      : super(SubscriptionEditState.initial()) {
    _init();
  }

  final nameController = TextEditingController();

  @override
  Future<void> close() {
    nameController.dispose();
    return super.close();
  }

  Future<void> _init() async {
    final sub = await AppDatabase().subscriptionDao.searchRow(params.id);
    if (sub != null) {
      nameController.text = sub.name;
      emit(state.copyWith(url: sub.url));
    }
  }

  Future<void> save(BuildContext context) async {
    final sub = await AppDatabase().subscriptionDao.searchRow(params.id);
    if (sub == null) {
      return;
    }
    final name = nameController.text.removeWhitespace;
    if (name.isEmpty) {
      if (context.mounted) {
        ContextAlert.showToast(
          context,
          AppLocalizations.of(context)!.appValidationNameRequired,
        );
      }
      return;
    }
    await SubscriptionService().updateSubscription(params.id, name);
    if (context.mounted) {
      context.pop();
    }
  }
}
