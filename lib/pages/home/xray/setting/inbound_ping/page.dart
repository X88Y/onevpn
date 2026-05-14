import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/home/xray/setting/inbound_ping/controller.dart';
import 'package:mvmvpn/pages/home/xray/setting/inbound_ping/params.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/pages/widget/text_row.dart';

class InboundPingPage extends StatelessWidget {
  final InboundPingParams params;

  const InboundPingPage({super.key, required this.params});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => InboundPingController(params),
      child: BlocBuilder<InboundPingController, InboundPingCubitState>(
        builder: (context, state) {
          final controller = context.read<InboundPingController>();
          return Scaffold(
            appBar: AppBar(
              title: Text(AppLocalizations.of(context)!.inboundPingScreenTitle),
            ),
            body: SafeArea(child: _body(context, controller, state)),
          );
        },
      ),
    );
  }

  Widget _body(
    BuildContext context,
    InboundPingController controller,
    InboundPingCubitState state,
  ) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: SingleChildScrollView(
        child: Column(
          children: [
            _listenSection(context, controller, state),
            _tagSection(context, controller, state),
          ],
        ),
      ),
    );
  }

  Widget _listenSection(
    BuildContext context,
    InboundPingController controller,
    InboundPingCubitState state,
  ) {
    return SectionView(
      title: "",
      child: Column(
        children: [
          TextRow(
            title: AppLocalizations.of(context)!.inboundPingScreenListen,
            detail: state.httpState.listen,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.inboundPingScreenPort,
            detail: state.httpState.port,
          ),
          TextRow(
            title: AppLocalizations.of(context)!.inboundPingScreenProtocol,
            detail: state.httpState.protocol.name,
          ),
        ],
      ),
    );
  }

  Widget _tagSection(
    BuildContext context,
    InboundPingController controller,
    InboundPingCubitState state,
  ) {
    return SectionView(
      title: "",
      child: Column(
        children: [
          TextRow(
            title: AppLocalizations.of(context)!.inboundPingScreenTag,
            detail: state.httpState.tag.name,
          ),
        ],
      ),
    );
  }
}
