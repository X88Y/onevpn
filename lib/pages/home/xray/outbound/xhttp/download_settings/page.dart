import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/pages/global/constants.dart';
import 'package:mvmvpn/pages/home/xray/outbound/xhttp/download_settings/controller.dart';
import 'package:mvmvpn/pages/home/xray/outbound/xhttp/download_settings/params.dart';
import 'package:mvmvpn/pages/widget/bottom_button.dart';
import 'package:mvmvpn/pages/widget/bottom_view.dart';
import 'package:mvmvpn/pages/widget/menu_picker.dart';
import 'package:mvmvpn/pages/widget/section.dart';
import 'package:mvmvpn/pages/widget/text_row.dart';
import 'package:mvmvpn/service/xray/outbound/enum.dart';

class XhttpDownloadSettingsPage extends StatelessWidget {
  final XhttpDownloadSettingsParams params;

  const XhttpDownloadSettingsPage({super.key, required this.params});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => XhttpDownloadSettingsController(params),
      child: BlocBuilder<XhttpDownloadSettingsController, XhttpDownloadSettingsState>(
        builder: (context, state) {
          final controller = context.read<XhttpDownloadSettingsController>();
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

  Widget _body(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
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
                  _downloadSettingsSection(context, controller, state),
                  _xhttpSection(context, controller, state),
                  _securitySection(context, controller, state),
                  _securitySettings(context, controller, state),
                ],
              ),
            ),
          ),
          _bottomButton(context, controller),
        ],
      ),
    );
  }

  Widget _headersSection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
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

  Widget _xPaddingBytesSection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
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

  Widget _xPaddingBytes(BuildContext context, XhttpDownloadSettingsController controller) {
    return TextField(
      controller: controller.xPaddingBytesController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXPaddingBytes),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenXPaddingBytes,
      ),
    );
  }

  Widget _noGRPCHeader(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(AppLocalizations.of(context)!.outboundXhttpScreenNoGRPCHeader),
        Switch(
          value: state.downloadState.noGRPCHeader,
          onChanged: (value) => controller.updateNoGRPCHeader(value),
        ),
      ],
    );
  }

  Widget _scMaxEachPostBytes(BuildContext context, XhttpDownloadSettingsController controller) {
    return TextField(
      controller: controller.scMaxEachPostBytesController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenScMaxEachPostBytes),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenScMaxEachPostBytes,
      ),
    );
  }

  Widget _scMinPostsIntervalMs(BuildContext context, XhttpDownloadSettingsController controller) {
    return TextField(
      controller: controller.scMinPostsIntervalMsController,
      decoration: InputDecoration(
        label: Text(AppLocalizations.of(context)!.outboundXhttpScreenScMinPostsIntervalMs),
        hintText: AppLocalizations.of(context)!.outboundXhttpScreenScMinPostsIntervalMs,
      ),
    );
  }

  Widget _xmuxSection(BuildContext context, XhttpDownloadSettingsController controller) {
    return SectionView(
      title: AppLocalizations.of(context)!.outboundXhttpScreenXmux,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(controller: controller.maxConcurrencyController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConcurrency), hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConcurrency)),
          TextField(controller: controller.maxConnectionsController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConnections), hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxMaxConnections)),
          TextField(controller: controller.cMaxReuseTimesController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxCMaxReuseTimes), hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxCMaxReuseTimes)),
          TextField(controller: controller.hMaxReusableSecsController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxReusableSecs), hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxReusableSecs)),
          TextField(controller: controller.hMaxRequestTimesController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxRequestTimes), hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxHMaxRequestTimes)),
          TextField(controller: controller.hKeepAlivePeriodController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundXhttpScreenXmuxHKeepAlivePeriod), hintText: AppLocalizations.of(context)!.outboundXhttpScreenXmuxHKeepAlivePeriod)),
        ],
      ),
    );
  }

  Widget _downloadSettingsSection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    return SectionView(
      title: "",
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(controller: controller.addressController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenAddress), hintText: AppLocalizations.of(context)!.outboundUIScreenAddressExample)),
          TextField(controller: controller.portController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenPort), hintText: AppLocalizations.of(context)!.outboundUIScreenPortExample)),
          TextRow(title: AppLocalizations.of(context)!.outboundUIScreenNetwork, detail: state.downloadState.network.name),
        ],
      ),
    );
  }

  Widget _xhttpSection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    return SectionView(
      title: AppLocalizations.of(context)!.outboundUIScreenXhttpConfigs,
      child: Column(
        children: [
          TextField(controller: controller.xhttpHostController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenHost), hintText: AppLocalizations.of(context)!.outboundUIScreenHostExample)),
          TextField(controller: controller.xhttpPathController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenPath), hintText: AppLocalizations.of(context)!.outboundUIScreenPathExample)),
          Padding(
            padding: const EdgeInsetsDirectional.symmetric(vertical: 5),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(AppLocalizations.of(context)!.outboundUIScreenXhttpMode),
                TextMenuPicker(title: state.downloadState.xhttpMode.name, selections: XhttpMode.values, callback: (value) => controller.updateXhttpMode(value)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _securitySection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    return SectionView(
      title: AppLocalizations.of(context)!.outboundUIScreenSecurity,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(AppLocalizations.of(context)!.outboundUIScreenSecurity),
          TextMenuPicker(title: state.downloadState.security.name, selections: StreamSettingsSecurity.xhttpDownloadSettingsSecurity, callback: (value) => controller.updateSecurity(value)),
        ],
      ),
    );
  }

  Widget _securitySettings(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    switch (state.downloadState.security) {
      case StreamSettingsSecurity.tls:
        return _tlsSection(context, controller, state);
      case StreamSettingsSecurity.reality:
        return _realitySection(context, controller, state);
      case StreamSettingsSecurity.none:
        return Container();
    }
  }

  Widget _tlsSection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    final children = StreamSettingsSecurityALPN.values.map((value) {
      return FilterChip(label: Text(value.name), selected: state.downloadState.alpn.contains(value), onSelected: (bool selected) => controller.updateAlpn(selected, value));
    }).toList();
    return SectionView(
      title: AppLocalizations.of(context)!.outboundUIScreenTlsConfigs,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(controller: controller.serverNameController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenServerName), hintText: AppLocalizations.of(context)!.outboundUIScreenServerNameExample)),
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(AppLocalizations.of(context)!.outboundUIScreenAlpn), Wrap(spacing: 5.0, runSpacing: 5.0, children: children)]),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(AppLocalizations.of(context)!.outboundUIScreenFingerprint), TextMenuPicker(title: state.downloadState.fingerprint.name, selections: StreamSettingsSecurityFingerprint.values, callback: (value) => controller.updateFingerprint(value))]),
          TextField(controller: controller.pinnedPeerCertSha256Controller, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenPinnedPeerCertSha256), hintText: AppLocalizations.of(context)!.outboundUIScreenPinnedPeerCertSha256)),
          TextField(controller: controller.verifyPeerCertByNameController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenVerifyPeerCertByName), hintText: AppLocalizations.of(context)!.outboundUIScreenVerifyPeerCertByName)),
          TextField(controller: controller.echConfigListController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenEchConfigList), hintText: AppLocalizations.of(context)!.outboundUIScreenEchConfigList)),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(AppLocalizations.of(context)!.outboundUIScreenEchForceQuery), TextMenuPicker(title: state.downloadState.echForceQuery.name, selections: StreamSettingsEchForceQuery.values, callback: (value) => controller.updateEchForceQuery(value))]),
        ],
      ),
    );
  }

  Widget _realitySection(BuildContext context, XhttpDownloadSettingsController controller, XhttpDownloadSettingsState state) {
    return SectionView(
      title: AppLocalizations.of(context)!.outboundUIScreenRealityConfigs,
      child: Column(
        children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(AppLocalizations.of(context)!.outboundUIScreenFingerprint), TextMenuPicker(title: state.downloadState.fingerprint.name, selections: StreamSettingsSecurityFingerprint.values, callback: (value) => controller.updateFingerprint(value))]),
          TextField(controller: controller.serverNameController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenServerName), hintText: AppLocalizations.of(context)!.outboundUIScreenServerNameExample)),
          TextField(controller: controller.passwordController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenPassword), hintText: AppLocalizations.of(context)!.outboundUIScreenPassword)),
          TextField(controller: controller.shortIdController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenShortId), hintText: AppLocalizations.of(context)!.outboundUIScreenShortId)),
          TextField(controller: controller.mldsa65VerifyController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenMldsa65Verify), hintText: AppLocalizations.of(context)!.outboundUIScreenMldsa65Verify)),
          TextField(controller: controller.spiderXController, decoration: InputDecoration(label: Text(AppLocalizations.of(context)!.outboundUIScreenSpiderX), hintText: AppLocalizations.of(context)!.outboundUIScreenSpiderX)),
        ],
      ),
    );
  }

  Widget _bottomButton(BuildContext context, XhttpDownloadSettingsController controller) {
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
