import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/home/xray/setting/simple/controller.dart';
import 'package:mvmvpn/pages/widget/bottom_button.dart';
import 'package:mvmvpn/pages/widget/bottom_view.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/pages/widget/tag_view.dart';
import 'package:mvmvpn/service/xray/setting/enum.dart';
import 'package:mvmvpn/service/xray/setting/simple_state.dart';

class XraySettingSimplePage extends StatelessWidget {
  const XraySettingSimplePage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => XraySettingSimpleController(),
      child:
          BlocBuilder<XraySettingSimpleController, XraySettingSimpleCubitState>(
            builder: (context, state) {
              final controller = context.read<XraySettingSimpleController>();
              return Scaffold(
                appBar: AppBar(
                  title: Text(
                    AppLocalizations.of(context)!.xrayConfigSimpleScreenTitle,
                  ),
                ),
                body: SafeArea(child: _body(context, controller, state)),
              );
            },
          ),
    );
  }

  Widget _body(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                children: [
                  _logSection(context, controller, state),
                  _routingSection(context, controller, state),
                  _dnsSection(context, controller, state),
                ],
              ),
            ),
          ),
          _bottomButton(context, controller),
        ],
      ),
    );
  }

  Widget _logSection(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return SectionView(
      title: AppLocalizations.of(context)!.logScreenTitle,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenEnableLog),
          Switch(
            value: state.xraySetting.enableLog,
            onChanged: (value) => controller.updateEnableLog(value),
          ),
        ],
      ),
    );
  }

  Widget _routingSection(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return SectionView(
      title: AppLocalizations.of(context)!.xrayConfigSimpleScreenRouting,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _domainStrategy(context, controller, state),
          _queryStrategy(context, controller, state),
          _directSet(context, controller, state),
          _appleDirect(context, controller, state),
          _localDirect(context, controller, state),
          _enableIPRule(context, controller, state),
          _localDns(context, controller, state),
        ],
      ),
    );
  }

  Widget _domainStrategy(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenDomainStrategy),
        TextMenuPicker(
          title: state.xraySetting.routing.domainStrategy.name,
          selections: RoutingDomainStrategy.simpleStrategy,
          callback: (value) => controller.updateDomainStrategy(value),
        ),
      ],
    );
  }

  Widget _queryStrategy(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenQueryStrategy),
        TextMenuPicker(
          title: state.xraySetting.routing.queryStrategy.name,
          selections: DnsQueryStrategy.names,
          callback: (value) => controller.updateQueryStrategy(value),
        ),
      ],
    );
  }

  Widget _directSet(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenDirectSet),
        TextMenuPicker(
          title: state.xraySetting.routing.directSet.name,
          selections: SimpleCountry.names,
          callback: (value) => controller.updateDirectSet(value),
        ),
      ],
    );
  }

  Widget _appleDirect(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenAppleDirect),
        Switch(
          value: state.xraySetting.routing.appleDirect,
          onChanged: (value) => controller.updateAppleDirect(value),
        ),
      ],
    );
  }

  Widget _localDirect(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenLocalDirect),
        Switch(
          value: state.xraySetting.routing.localDirect,
          onChanged: (value) => controller.updateLocalDirect(value),
        ),
      ],
    );
  }

  Widget _enableIPRule(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenEnableIPRule),
        Switch(
          value: state.xraySetting.routing.enableIPRule,
          onChanged: (value) => controller.updateEnableIPRule(value),
        ),
      ],
    );
  }

  Widget _localDns(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.xrayConfigSimpleScreenLocalDns),
        Switch(
          value: state.xraySetting.routing.localDns,
          onChanged: (value) => controller.updateLocalDns(value),
        ),
      ],
    );
  }

  Widget _dnsSection(
    BuildContext context,
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
  ) {
    final children = SimpleDns.values
        .map((e) => _simpleDns(controller, state, e))
        .toList();
    return SectionView(
      title: AppLocalizations.of(context)!.xrayConfigSimpleScreenDns,
      child: RadioGroup<int>(
        groupValue: state.xraySetting.dns.id,
        onChanged: (value) => controller.updateDnsId(value),
        child: Column(children: children),
      ),
    );
  }

  Widget _simpleDns(
    XraySettingSimpleController controller,
    XraySettingSimpleCubitState state,
    SimpleDns dns,
  ) {
    final queryStrategy = state.xraySetting.routing.queryStrategy;
    return RadioListTile(
      value: dns.id,
      title: Text(dns.address),
      subtitle: Row(
        children: [
          TagView(tag: dns.outbound.name),
          TagView(tag: queryStrategy.name),
        ],
      ),
    );
  }

  Widget _bottomButton(
    BuildContext context,
    XraySettingSimpleController controller,
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
