import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/home/xray/setting/inbound_sniffing/controller.dart';
import 'package:mvmvpn/pages/home/xray/setting/inbound_sniffing/params.dart';
import 'package:mvmvpn/pages/widget/bottom_button.dart';
import 'package:mvmvpn/pages/widget/bottom_view.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/service/xray/setting/inbounds_state.dart';

class InboundSniffingPage extends StatelessWidget {
  final InboundSniffingParams params;

  const InboundSniffingPage({super.key, required this.params});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => InboundSniffingController(params),
      child: BlocBuilder<InboundSniffingController, InboundSniffingCubitState>(
        builder: (context, state) {
          final controller = context.read<InboundSniffingController>();
          return Scaffold(
        appBar: AppBar(
          title: Text(AppLocalizations.of(context)!.inboundSniffingScreenTitle),
        ),
        body: SafeArea(child: _body(context, controller, state)),
      );
        },
      ),
    );
  }

  Widget _body(BuildContext context, InboundSniffingController controller, InboundSniffingCubitState state) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _enableSection(context, controller, state),
                  _routeOnlySection(context, controller, state),
                  _destOverrideSection(context, controller, state),
                  _domainsExcludedSection(context, controller, state),
                ],
              ),
            ),
          ),
          _bottomButton(context, controller),
        ],
      ),
    );
  }

  Widget _enableSection(
    BuildContext context,
    InboundSniffingController controller, InboundSniffingCubitState state) {
    return SectionView(
      title: "",
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(AppLocalizations.of(context)!.appSwitchEnabled),
          Switch(
            value: state.sniffingState.enabled,
            onChanged: (value) => controller.updateEnabled(value),
          ),
        ],
      ),
    );
  }

  Widget _routeOnlySection(
    BuildContext context,
    InboundSniffingController controller, InboundSniffingCubitState state) {
    return SectionView(
      title: "",
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(AppLocalizations.of(context)!.appSwitchRouteOnly),
          Switch(
            value: state.sniffingState.routeOnly,
            onChanged: (value) => controller.updateRouteOnly(value),
          ),
        ],
      ),
    );
  }

  Widget _destOverrideSection(
    BuildContext context,
    InboundSniffingController controller, InboundSniffingCubitState state) {
    final children = InboundSniffingDestOverride.values.map((value) {
      return FilterChip(
        label: Text(value.name),
        selected: state.sniffingState.destOverride.contains(value),
        onSelected: (bool selected) =>
            controller.updateDestOverride(selected, value),
      );
    }).toList();

    return SectionView(
      title: AppLocalizations.of(context)!.inboundSniffingScreenDestOverride,
      child: Wrap(spacing: 5.0, runSpacing: 5.0, children: children),
    );
  }

  Widget _domainsExcludedSection(
    BuildContext context,
    InboundSniffingController controller, InboundSniffingCubitState state) {
    final domainsExcludedViews = state.sniffingState.domainsExcluded
        .mapIndexed(
          (index, host) => Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller.domainsExcludedControllers[index],
                  decoration: InputDecoration(
                    label: Text(
                      AppLocalizations.of(
                        context,
                      )!.inboundSniffingScreenDomainsExcluded,
                    ),
                    hintText: AppLocalizations.of(
                      context,
                    )!.inboundSniffingScreenDomainsExcludedExample,
                  ),
                ),
              ),
              IconButton(
                onPressed: () =>
                    controller.deleteDomainsExcluded(context, index),
                icon: Icon(Icons.delete),
              ),
            ],
          ),
        )
        .toList();
    return SectionView(
      title: "",
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                AppLocalizations.of(
                  context,
                )!.inboundSniffingScreenDomainsExcluded,
              ),
              IconButton(
                onPressed: () => controller.appendDomainsExcluded(),
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          if (domainsExcludedViews.isNotEmpty)
            Column(children: domainsExcludedViews),
        ],
      ),
    );
  }

  Widget _bottomButton(
    BuildContext context,
    InboundSniffingController controller,
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
