import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/home/xray/setting/routing_rule_dns_query/controller.dart';
import 'package:mvmvpn/pages/home/xray/setting/routing_rule_dns_query/params.dart';
import 'package:mvmvpn/pages/widget/bottom_button.dart';
import 'package:mvmvpn/pages/widget/bottom_view.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/pages/widget/text_row.dart';

class RoutingRuleDnsQueryPage extends StatelessWidget {
  final RoutingRuleDnsQueryParams params;

  const RoutingRuleDnsQueryPage({super.key, required this.params});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => RoutingRuleDnsQueryController(params),
      child: BlocBuilder<RoutingRuleDnsQueryController, RoutingRuleDnsQueryCubitState>(
        builder: (context, state) {
          final controller = context.read<RoutingRuleDnsQueryController>();
          return Scaffold(
        appBar: AppBar(
          title: Text(AppLocalizations.of(context)!.routingRuleScreenTitle),
        ),
        body: SafeArea(child: _body(context, controller, state)),
      );
        },
      ),
    );
  }

  Widget _body(BuildContext context, RoutingRuleDnsQueryController controller, RoutingRuleDnsQueryCubitState state) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _inboundTagSection(context, controller, state),
                  _tagSection(context, controller, state),
                ],
              ),
            ),
          ),
          _bottomButton(context, controller),
        ],
      ),
    );
  }

  Widget _inboundTagSection(
    BuildContext context,
    RoutingRuleDnsQueryController controller, RoutingRuleDnsQueryCubitState state) {
    final views = state.ruleState.inboundTag
        .map((e) => Text(e))
        .toList();
    return SectionView(
      title: AppLocalizations.of(context)!.routingRuleScreenInboundTag,
      child: Column(children: views),
    );
  }

  Widget _tagSection(
    BuildContext context,
    RoutingRuleDnsQueryController controller, RoutingRuleDnsQueryCubitState state) {
    return SectionView(
      title: "",
      child: Column(
        children: [
          _outboundTag(context, controller, state),
          _ruleTag(context, controller, state),
        ],
      ),
    );
  }

  Widget _outboundTag(
    BuildContext context,
    RoutingRuleDnsQueryController controller, RoutingRuleDnsQueryCubitState state) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.routingRuleScreenOutboundTag),
        TextMenuPicker(
          title: state.ruleState.outboundTag,
          selections: state.outboundTags,
          callback: (value) => controller.updateOutboundTag(value),
        ),
      ],
    );
  }

  Widget _ruleTag(
    BuildContext context,
    RoutingRuleDnsQueryController controller, RoutingRuleDnsQueryCubitState state) {
    return TextRow(
      title: AppLocalizations.of(context)!.routingRuleScreenRuleTag,
      detail: state.ruleState.ruleTag,
    );
  }

  Widget _bottomButton(
    BuildContext context,
    RoutingRuleDnsQueryController controller,
  ) {
    return BottomView(
      child: Row(
        children: [
          Expanded(
            child: PrimaryBottomButton(
              title: AppLocalizations.of(context)!.btnSave,
              callback: () => controller.save(context),
            ),
          ),
        ],
      ),
    );
  }
}
