import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'dart:math';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:mvmvpn/service/auth/model.dart';
import 'package:mvmvpn/service/event_bus/service.dart';
import 'package:mvmvpn/core/db/database/database.dart';
import 'package:mvmvpn/service/subscription/service.dart';
class AuthService {
  static final AuthService _instance = AuthService._internal();
  factory AuthService() => _instance;
  AuthService._internal();

  final FirebaseAuth _auth = FirebaseAuth.instance;
  final FirebaseFunctions _functions = FirebaseFunctions.instance;

  User? get currentUser => _auth.currentUser;
  Stream<User?> get authStateChanges => _auth.authStateChanges();

  Future<UserCredential?> signInWithApple() async {
    try {
      debugPrint('[AuthService][Apple] Starting Apple sign-in flow');
      final rawNonce = _generateNonce();
      final nonce = _sha256ofString(rawNonce);
      debugPrint(
        '[AuthService][Apple] Nonce generated (rawLength=${rawNonce.length}, hashedLength=${nonce.length})',
      );

      final appleCredential = await SignInWithApple.getAppleIDCredential(
        scopes: [
          AppleIDAuthorizationScopes.email,
          AppleIDAuthorizationScopes.fullName,
        ],
        nonce: nonce,
      );
      debugPrint(
        '[AuthService][Apple] Apple credential received '
        '(userIdentifier=${appleCredential.userIdentifier}, '
        'hasIdentityToken=${appleCredential.identityToken != null && appleCredential.identityToken!.isNotEmpty}, '
        'hasAuthorizationCode=${appleCredential.authorizationCode.isNotEmpty}, '
        'email=${appleCredential.email})',
      );

      if (appleCredential.identityToken == null ||
          appleCredential.identityToken!.isEmpty) {
        debugPrint(
          '[AuthService][Apple][Error] Missing identityToken from Apple response',
        );
        return null;
      }

      final tokenAudience = _extractAudienceFromJwt(
        appleCredential.identityToken!,
      );
      if (tokenAudience != null) {
        debugPrint(
          '[AuthService][Apple] Identity token audience: $tokenAudience',
        );
      }

      final oauthCredential = OAuthProvider('apple.com').credential(
        idToken: appleCredential.identityToken,
        rawNonce: rawNonce,
        accessToken: appleCredential.authorizationCode,
      );
      debugPrint('[AuthService][Apple] Firebase OAuth credential created');

      final userCredential = await _auth.signInWithCredential(oauthCredential);
      debugPrint(
        '[AuthService][Apple] Firebase sign-in success '
        '(uid=${userCredential.user?.uid}, provider=${userCredential.credential?.providerId})',
      );
      return userCredential;
    } on FirebaseAuthException catch (e, stackTrace) {
      debugPrint(
        '[AuthService][Apple][FirebaseAuthException] '
        'code=${e.code}, message=${e.message}, email=${e.email}, credential=${e.credential}',
      );
      debugPrintStack(
        label: '[AuthService][Apple][FirebaseAuthException][StackTrace]',
        stackTrace: stackTrace,
      );
      return null;
    } on SignInWithAppleAuthorizationException catch (e, stackTrace) {
      debugPrint(
        '[AuthService][Apple][SignInWithAppleAuthorizationException] '
        'code=${e.code}, message=${e.message}',
      );
      debugPrintStack(
        label:
            '[AuthService][Apple][SignInWithAppleAuthorizationException][StackTrace]',
        stackTrace: stackTrace,
      );
      return null;
    } catch (e, stackTrace) {
      debugPrint('[AuthService][Apple][UnexpectedError] $e');
      debugPrintStack(
        label: '[AuthService][Apple][UnexpectedError][StackTrace]',
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  Future<void> signOut() async {
    await _auth.signOut();
    await PreferencesKey().saveUserProfile(null);
    AppEventBus.instance.updateUserData(null);
  }

  Future<UserModel?> syncUserWithBackend() async {
    try {
      final myUserRes = await FirebaseFunctions.instance
          .httpsCallable('getMyUser')
          .call();
      debugPrint('[AuthService][Backend][Info] myUserRes: ${myUserRes.data}');
      final responseData = _asStringKeyedMap(myUserRes.data);
      if (responseData == null) {
        debugPrint(
          '[AuthService][Backend][Warning] getMyUser returned invalid top-level payload',
        );
        return null;
      }
      final userDataMap = _asStringKeyedMap(responseData['user']);
      final publicConstant = _asStringKeyedMap(responseData['publicConstant']);
      final telegramUrl = publicConstant?['tg'] as String?;
      final vkUrl = publicConstant?['vk'] as String?;

      if (userDataMap == null) {
        debugPrint(
          '[AuthService][Backend][Warning] getMyUser returned invalid user payload',
        );
        return null;
      }

      final userModel = UserModel.fromMap(
        userDataMap, 
        uid: _auth.currentUser?.uid,
        telegramUrl: telegramUrl,
        vkUrl: vkUrl,
      );
      await PreferencesKey().saveUserProfile(userModel.toJson());
      AppEventBus.instance.updateUserData(userModel);

      return userModel;
    } on FirebaseFunctionsException catch (e, stackTrace) {
      debugPrint(
        '[AuthService][Backend][FirebaseFunctionsException] '
        'code=${e.code}, message=${e.message}, details=${e.details}',
      );
      debugPrintStack(
        label: '[AuthService][Backend][FirebaseFunctionsException][StackTrace]',
        stackTrace: stackTrace,
      );
      return null;
    } catch (e, stackTrace) {
      debugPrint('[AuthService][Backend][UnexpectedError] $e');
      debugPrintStack(
        label: '[AuthService][Backend][UnexpectedError][StackTrace]',
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  Future<bool> activateTrial() async {
    return activateTrialForProvider('apple');
  }

  Future<int?> fetchAndSetRandomVpnKey({bool forceRegenerate = false}) async {
    final functionName = forceRegenerate ? 'regenerateVpnKey' : 'getRandomVpnKey';
    debugPrint('[AuthService] fetchAndSetRandomVpnKey called (forceRegenerate: $forceRegenerate)');
    try {
      final res = await _functions.httpsCallable(functionName).call();
      final data = _asStringKeyedMap(res.data);
      debugPrint('[AuthService] $functionName response: $data');
      if (data != null && data['ok'] == true) {
        final keyUrl = data['key'] as String?;
        debugPrint('[AuthService] keyUrl: $keyUrl');
        if (keyUrl != null) {
          final db = AppDatabase();
          final exists = await db.subscriptionDao.urlExists(keyUrl);
          debugPrint('[AuthService] urlExists: $exists');
          if (!exists) {
            final count = await SubscriptionService().insertSubscription('Premium Subscription', keyUrl, false);
            debugPrint('[AuthService] insertSubscription count: $count');
          }
          
          final subs = await db.subscriptionDao.allRows;
          var subId = -1;
          for (final sub in subs) {
            if (sub.url == keyUrl) {
              subId = sub.id;
              break;
            }
          }
          debugPrint('[AuthService] found subId: $subId');
          
          if (subId != -1) {
            final configs = await db.select(db.coreConfig).get();
            debugPrint('[AuthService] total configs in db: ${configs.length}');
            for (final config in configs) {
              if (config.subId == subId) {
                debugPrint('[AuthService] found config matching subId: ${config.id}');
                await PreferencesKey().saveLastConfigId(config.id);
                return config.id;
              }
            }
            debugPrint('[AuthService] No config found for subId: $subId');
          }
        }
      } else {
        debugPrint('[AuthService] data ok is false or data is null');
      }
    } catch (e, stack) {
      debugPrint('[AuthService][Backend][fetchAndSetRandomVpnKey] Error: $e\n$stack');
    }
    debugPrint('[AuthService] fetchAndSetRandomVpnKey returning null');
    return null;
  }

  Future<bool> activateTrialForProvider(String provider) async {
    try {
      final startTrialCallable = _functions.httpsCallable('startTrial');
      await startTrialCallable.call({'provider': provider});
      debugPrint(
        '[AuthService][Backend] startTrial completed successfully (provider=$provider)',
      );
      return true;
    } on FirebaseFunctionsException catch (e, stackTrace) {
      if (e.code == 'failed-precondition') {
        if (e.message?.contains('already activated') ?? false) {
          debugPrint(
            '[AuthService][Backend] startTrial: Trial already active, ignoring error',
          );
          return true;
        }
        if (e.message?.contains('not connected for this account') ?? false) {
          debugPrint(
            '[AuthService][Backend] startTrial: Service not connected for this account, ignoring error',
          );
          return true;
        }
      }
      debugPrint(
        '[AuthService][Backend][startTrial][FirebaseFunctionsException] '
        'code=${e.code}, message=${e.message}, details=${e.details}',
      );
      debugPrintStack(
        label:
            '[AuthService][Backend][startTrial][FirebaseFunctionsException][StackTrace]',
        stackTrace: stackTrace,
      );
      return false;
    } catch (e, stackTrace) {
      debugPrint('[AuthService][Backend][startTrial][UnexpectedError] $e');
      debugPrintStack(
        label:
            '[AuthService][Backend][startTrial][UnexpectedError][StackTrace]',
        stackTrace: stackTrace,
      );
      return false;
    }
  }

  Future<bool> handleDeepLinkJwt(String jwt) async {
    try {
      final jwtPayload = _decodeJwtPayload(jwt);
      if (jwtPayload == null) {
        debugPrint(
          '[AuthService][DeepLink][Warning] Failed to decode JWT payload',
        );
        return false;
      }

      final provider = _extractProviderFromPayload(jwtPayload);
      if (provider == null) {
        debugPrint(
          '[AuthService][DeepLink][Warning] JWT provider claim is missing',
        );
        return false;
      }

      await PreferencesKey().saveAuthProvider(provider);
      debugPrint('[AuthService][DeepLink] Provider saved: $provider');

      if (Firebase.apps.isEmpty) {
        debugPrint('[AuthService][DeepLink][Warning] Firebase is not ready');
        return false;
      }

      final syncUserCallable = _functions.httpsCallable('syncUser');
      final syncResponse = await syncUserCallable.call({
        'externalJwt': jwt,
      });

      final action = _extractAction(syncResponse.data);
      if (action == null) {
        debugPrint(
          '[AuthService][DeepLink][Warning] syncUser action is missing',
        );
        return false;
      }

      if (action == 'login_external') {
        final customToken = _extractCustomToken(syncResponse.data);
        if (customToken == null || customToken.isEmpty) {
          debugPrint(
            '[AuthService][DeepLink][Warning] login_external action missing custom token',
          );
          return false;
        }
        await _auth.signInWithCustomToken(customToken);
        debugPrint('[AuthService][DeepLink] Signed in with custom token');
      } else if (action == 'merged') {
        debugPrint('[AuthService][DeepLink] Merge action completed');
      } else if (action == 'login_apple') {
        debugPrint('[AuthService][DeepLink] Apple login action completed');
      } else {
        debugPrint('[AuthService][DeepLink][Warning] Unknown action: $action');
        return false;
      }

      if (_isTrialProvider(provider)) {
        await activateTrialForProvider(provider);
      }

      await syncUserWithBackend();

      return true;
    } on FirebaseAuthException catch (e, stackTrace) {
      debugPrint(
        '[AuthService][DeepLink][FirebaseAuthException] code=${e.code}, message=${e.message}',
      );
      debugPrintStack(
        label: '[AuthService][DeepLink][FirebaseAuthException][StackTrace]',
        stackTrace: stackTrace,
      );
      return false;
    } on FirebaseFunctionsException catch (e, stackTrace) {
      debugPrint(
        '[AuthService][DeepLink][FirebaseFunctionsException] code=${e.code}, message=${e.message}, details=${e.details}',
      );
      debugPrintStack(
        label:
            '[AuthService][DeepLink][FirebaseFunctionsException][StackTrace]',
        stackTrace: stackTrace,
      );
      return false;
    } catch (e, stackTrace) {
      debugPrint('[AuthService][DeepLink][UnexpectedError] $e');
      debugPrintStack(
        label: '[AuthService][DeepLink][UnexpectedError][StackTrace]',
        stackTrace: stackTrace,
      );
      return false;
    }
  }

  String _generateNonce([int length = 32]) {
    const charset =
        '0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._';
    final random = Random.secure();
    return List.generate(
      length,
      (_) => charset[random.nextInt(charset.length)],
    ).join();
  }

  String _sha256ofString(String input) {
    final bytes = utf8.encode(input);
    final digest = sha256.convert(bytes);
    return digest.toString();
  }

  String? _extractAudienceFromJwt(String jwt) {
    try {
      final parts = jwt.split('.');
      if (parts.length < 2) {
        return null;
      }
      final normalized = base64Url.normalize(parts[1]);
      final payload = utf8.decode(base64Url.decode(normalized));
      final payloadMap = jsonDecode(payload);
      if (payloadMap is! Map<String, dynamic>) {
        return null;
      }
      final aud = payloadMap['aud'];
      if (aud is String && aud.isNotEmpty) {
        return aud;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  Map<String, dynamic>? _asStringKeyedMap(Object? value) {
    if (value is Map<String, dynamic>) {
      return value;
    }
    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }
    return null;
  }

  Map<String, dynamic>? _decodeJwtPayload(String jwt) {
    try {
      final parts = jwt.split('.');
      if (parts.length < 2) {
        return null;
      }
      final normalized = base64Url.normalize(parts[1]);
      final payload = utf8.decode(base64Url.decode(normalized));
      final payloadMap = jsonDecode(payload);
      return _asStringKeyedMap(payloadMap);
    } catch (_) {
      return null;
    }
  }

  String? _extractProviderFromPayload(Map<String, dynamic> payload) {
    const providerKeys = [
      'provider',
      'authProvider',
      'source',
      'socialProvider',
    ];
    for (final key in providerKeys) {
      final raw = payload[key];
      if (raw is String && raw.isNotEmpty) {
        return raw.toLowerCase();
      }
    }
    return null;
  }

  String? _extractAction(Object? responseData) {
    final data = _asStringKeyedMap(responseData);
    if (data == null) {
      return null;
    }
    final action = data['action'];
    if (action is String && action.isNotEmpty) {
      return action.toLowerCase();
    }
    final result = _asStringKeyedMap(data['result']);
    final nestedAction = result?['action'];
    if (nestedAction is String && nestedAction.isNotEmpty) {
      return nestedAction.toLowerCase();
    }
    return null;
  }

  String? _extractCustomToken(Object? responseData) {
    final data = _asStringKeyedMap(responseData);
    if (data == null) {
      return null;
    }
    const tokenKeys = ['customToken', 'token'];
    for (final key in tokenKeys) {
      final value = data[key];
      if (value is String && value.isNotEmpty) {
        return value;
      }
    }
    final result = _asStringKeyedMap(data['result']);
    if (result == null) {
      return null;
    }
    for (final key in tokenKeys) {
      final value = result[key];
      if (value is String && value.isNotEmpty) {
        return value;
      }
    }
    return null;
  }

  bool _isTrialProvider(String provider) {
    final value = provider.toLowerCase();
    return value == 'tg' || value == 'vk';
  }
}
