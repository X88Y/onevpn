import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/pages/widget/text_row.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/service/event_bus/state.dart';

class NodeInfoPage extends StatelessWidget {
  const NodeInfoPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(AppLocalizations.of(context)!.nodeInfoScreenTitle),
      ),
      body: SafeArea(child: _body(context)),
    );
  }

  Widget _body(BuildContext context) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: SingleChildScrollView(
        child: BlocBuilder<AppEventBus, AppEventBusState>(
          builder: (context, state) => _section(context, state),
        ),
      ),
    );
  }

  Widget _section(BuildContext context, AppEventBusState state) {
    final location = state.location;
    final duration =
        location.duration ?? AppLocalizations.of(context)!.nodeInfoScreenFetching;
    var delay = "";
    if (location.delay == null) {
      delay = AppLocalizations.of(context)!.nodeInfoScreenFetching;
    } else {
      delay = "${location.delay}ms";
    }
    final ipAddress =
        location.ipAddress ??
        AppLocalizations.of(context)!.nodeInfoScreenFetching;
    final ipVersion =
        location.ipVersion ??
        AppLocalizations.of(context)!.nodeInfoScreenFetching;
    final country =
        location.country ?? AppLocalizations.of(context)!.nodeInfoScreenFetching;
    final region =
        location.region ?? AppLocalizations.of(context)!.nodeInfoScreenFetching;
    final city =
        location.city ?? AppLocalizations.of(context)!.nodeInfoScreenFetching;

    return SectionView(
      title: "",
      child: Column(
        children: [
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenDuration,
            detail: duration,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenDelay,
            detail: delay,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenIP,
            detail: ipAddress,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenIPVersion,
            detail: ipVersion,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenCountryOrRegion,
            detail: country,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenRegion,
            detail: region,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.nodeInfoScreenCity,
            detail: city,
          ),
        ],
      ),
    );
  }
}
