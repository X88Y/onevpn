import 'package:mvmvpn/service/xray/outbound/enum.dart';
import 'package:mvmvpn/service/xray/outbound/xhttp/state.dart';

class OutboundXhttpParams {
  final XhttpMode mode;
  final XhttpExtraState state;

  OutboundXhttpParams(this.mode, this.state);
}
