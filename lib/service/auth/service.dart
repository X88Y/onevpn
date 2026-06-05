import 'dart:async';
import 'package:mvmvpn/service/auth/model.dart';

class AuthService {
  static final AuthService _instance = AuthService._internal();
  factory AuthService() => _instance;
  AuthService._internal();

  Null get currentUser => null;
  Stream<Null> get authStateChanges => Stream.value(null);

  Future<void> signOut() async {}

  Future<UserModel?> syncUserWithBackend() async {
    return null;
  }

  Future<bool> activateTrial() async {
    return false;
  }

  Future<int?> fetchAndSetRandomVpnKey({bool forceRegenerate = false}) async {
    return null;
  }

  Future<bool> handleDeepLinkJwt(String jwt) async {
    return false;
  }
}
