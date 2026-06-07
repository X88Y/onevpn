import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:mvmvpn/core/tools/extensions.dart';
import 'package:mvmvpn/pages/mixin/alert.dart';
import 'package:mvmvpn/service/subscription/service.dart';
import 'package:mvmvpn/service/subscription/validator.dart';

class SubscriptionAddController {
  final nameController = TextEditingController();
  final urlController = TextEditingController();

  void dispose() {
    nameController.dispose();
    urlController.dispose();
  }

  Future<void> save(BuildContext context) async {
    final name = nameController.text.trim();
    final url = urlController.text.removeWhitespace;
    final check = await SubscriptionValidator.validate(name, url);
    if (check.item1) {
      final count = await SubscriptionService().insertSubscription(
        name,
        url,
        true,
      );
      if (context.mounted) {
        if (count > 0) {
          context.pop();
        }
      }
    } else {
      if (context.mounted) {
        ContextAlert.showToast(context, check.item2);
      }
    }
  }
}
