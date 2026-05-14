import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/home/xray/outbound/xhttp/controller.dart';
import 'package:mvmvpn/pages/home/xray/outbound/xhttp/params.dart';
import 'package:mvmvpn/pages/widget/bottom_button.dart';
import 'package:mvmvpn/pages/widget/bottom_view.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/service/xray/outbound/enum.dart';

class OutboundXhttpPage extends StatelessWidget {
  final OutboundXhttpParams params;

  const OutboundXhttpPage({super.key, required this.params});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => OutboundXhttpController(params),
      child: BlocBuilder<OutboundXhttpController, OutboundXhttpState>(
        builder: (context, state) {
          final controller = context.read<OutboundXhttpController>();
          return Scaffold(
            appBar: AppBar(
              title: Text(AppLocalizations.of(context)!.outboundXhttpScreenTitle),
            ),
            body: SafeArea(child: _body(context, controller, state)),
          );
        },
      ),
    );
  }

  Widget _body(BuildContext context, OutboundXhttpController controller, OutboundXhttpState state) {
    return DefaultTextStyle.merge(
      style: const TextStyle(fontSize: GlobalConstants.bodyFontSize),
      child: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                children: [
                  _headersSection(context, controller, state),
                  _xPaddingBytesSection(context, controller, state),
                  _xmuxSection(context, controller),
                  if (state.mode != XhttpMode.streamOne)
                    _downloadSettingsSection(context, controller),
                ],
              ),
            ),
          ),
          _bottomButton(context, controller),
        ],
      ),
    );
  }

  Widget _headersSection(BuildContext context, OutboundXhttpController controller, OutboundXhttpState state) {
    final headerViews = <Widget>[];
    for (final header in state.headers) {
      final key = TextField(
        controller: header.key,
        decoration: InputDecoration(
          label: Text(AppLocalizations.of(context)!.outboundXhttpScreenHeadersKey),
          hintText: AppLocalizations.of(context)!.outboundXhttpScreenHeadersKey,
        ),
      );
      final value = TextField(
        controller: header.value,
        decoration: InputDecoration(
          label: Text(AppLocalizations.of(context)!.outboundXhttpScreenHeadersValue),
          hintText: AppLocalizations.of(context)!.outboundXhttpScreenHeadersValue,
        ),
      );
      headerViews.add(key);
      headerViews.add(value);
    }
    return SectionView(
      title: "",
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(AppLocalizations.of(context)!.outboundXhttpScreenHeaders),
              IconButton(
                onPressed: () => controller.appendHeader(),
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          if (headerViews.isNotEmpty) Column(children: headerViews),
        ],
      ),
    );
  }

  Widget _xPaddingBytesSection(BuildContext context, OutboundXhttpController controller, OutboundXhttpState state) {
    return SectionView(
      title: "",
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _xPaddingBytes(context, controller),
          _noGRPCHeader(context, controller, state),
          _scMaxEachPostBytes(context, controller),
          _scMinPostsIntervalMs(context, controller),
        ],
      ),
    );
  }

  Widget _xPaddingBytes(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.xPaddingBytesController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXPaddingBytes),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXPaddingBytes,
      ),
    );
  }

  Widget _noGRPCHeader(BuildContext context, OutboundXhttpController controller, OutboundXhttpState state) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.outboundXhttpScreenNoGRPCHeader),
        Switch(
          value: state.extraState.noGRPCHeader,
          onChanged: (value) => controller.updateNoGRPCHeader(value),
        ),
      ],
    );
  }

  Widget _scMaxEachPostBytes(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.scMaxEachPostBytesController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenScMaxEachPostBytes),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenScMaxEachPostBytes,
      ),
    );
  }

  Widget _scMinPostsIntervalMs(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.scMinPostsIntervalMsController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenScMinPostsIntervalMs),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenScMinPostsIntervalMs,
      ),
    );
  }

  Widget _xmuxSection(BuildContext context, OutboundXhttpController controller) {
    return SectionView(
      title: AppLocalizations.of(context)!.outboundXhttpScreenXmux,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _maxConcurrency(context, controller),
          _maxConnections(context, controller),
          _cMaxReuseTimes(context, controller),
          _hMaxReusableSecs(context, controller),
          _hMaxRequestTimes(context, controller),
          _hKeepAlivePeriod(context, controller),
        ],
      ),
    );
  }

  Widget _maxConcurrency(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.maxConcurrencyController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConcurrency),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConcurrency,
      ),
    );
  }

  Widget _maxConnections(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.maxConnectionsController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConnections),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConnections,
      ),
    );
  }

  Widget _cMaxReuseTimes(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.cMaxReuseTimesController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxCMaxReuseTimes),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxCMaxReuseTimes,
      ),
    );
  }

  Widget _hMaxReusableSecs(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.hMaxReusableSecsController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxReusableSecs),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxReusableSecs,
      ),
    );
  }

  Widget _hMaxRequestTimes(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.hMaxRequestTimesController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxRequestTimes),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxRequestTimes,
      ),
    );
  }

  Widget _hKeepAlivePeriod(BuildContext context, OutboundXhttpController controller) {
    return TextField(
      controller: controller.hKeepAlivePeriodController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxHKeepAlivePeriod),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxHKeepAlivePeriod,
      ),
    );
  }

  Widget _downloadSettingsSection(BuildContext context, OutboundXhttpController controller) {
    return SectionView(
      title: "",
      child: InkWell(
        onTap: () => controller.editXhttpDownloadSettings(context),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(vertical: 5),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(AppLocalizations.of(context)!.outboundXhttpScreenDownloadConfigs),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }

  Widget _bottomButton(BuildContext context, OutboundXhttpController controller) {
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
