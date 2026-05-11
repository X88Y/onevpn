import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:uuid/uuid.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:mvmvpn/core/constants/preferences.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:mvmvpn/core/tools/logger.dart';
import 'package:mvmvpn/core/tools/platform.dart';
import 'package:flutter/foundation.dart';

final class NotificationService {
  static final NotificationService _singleton = NotificationService._internal();

  factory NotificationService() => _singleton;

  NotificationService._internal();

  //==========================
  final _localNotification = FlutterLocalNotificationsPlugin();
  final _messaging = FirebaseMessaging.instance;

  Future<void> asyncInit() async {
    const initializationSettingsAndroid = AndroidInitializationSettings(
      'ic_launcher',
    );
    final initializationSettingsDarwin = DarwinInitializationSettings();
    final initializationSettingsLinux = LinuxInitializationSettings(
      defaultActionName: 'Open notification',
    );
    final WindowsInitializationSettings initializationSettingsWindows =
        WindowsInitializationSettings(
          appName: 'MVMVpn',
          appUserModelId: 'app.svyatvpn.com',
          // Search online for GUID generators to make your own
          guid: '835d7bbd-85bb-4c73-97f8-ce0740f151a7',
        );
    final initializationSettings = InitializationSettings(
      android: initializationSettingsAndroid,
      iOS: initializationSettingsDarwin,
      macOS: initializationSettingsDarwin,
      linux: initializationSettingsLinux,
      windows: initializationSettingsWindows,
    );
    await _localNotification.initialize(
      settings: initializationSettings,
      onDidReceiveNotificationResponse: _onReceiveNotification,
    );

    if (AppPlatform.isAndroid) {
      await _localNotification
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >()
          ?.requestNotificationsPermission();
    }

    if (AppPlatform.isMobile) {
      await _initFirebaseMessaging();
    }
  }

  Future<void> _initFirebaseMessaging() async {
    try {
      final settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );
      debugPrint('[NotificationService] FCM settings: ${settings.authorizationStatus}');

      if (AppPlatform.isIOS) {
        debugPrint('[NotificationService] iOS detected, waiting for APNS token...');
        String? apnsToken;
        int retryCount = 0;
        while (apnsToken == null && retryCount < 10) {
          try {
            apnsToken = await _messaging.getAPNSToken();
          } catch (e) {
            debugPrint('[NotificationService] APNS token not ready yet...');
          }
          
          if (apnsToken == null) {
            await Future.delayed(const Duration(seconds: 1));
            retryCount++;
            debugPrint('[NotificationService] Still waiting for APNS token... ($retryCount/10)');
          }
        }
        if (apnsToken != null) {
          debugPrint('[NotificationService] APNS token received: $apnsToken');
        } else {
          debugPrint('[NotificationService] Warning: APNS token not received after 10 seconds. FCM token might fail.');
        }
      }

      _messaging.onTokenRefresh.listen((token) {
        debugPrint('[NotificationService] FCM token refreshed: $token');
        syncTokenWithBackend(token);
      });

      // Also sync when user state changes (e.g. login after startup)
      FirebaseAuth.instance.authStateChanges().listen((user) {
        if (user != null) {
          debugPrint('[NotificationService] User state changed to logged in, syncing token');
          syncTokenWithBackend();
        }
      });

      final token = await _messaging.getToken();
      if (token != null) {
        debugPrint('[NotificationService] Initial FCM token: $token');
        syncTokenWithBackend(token);
      }
    } catch (e) {
      debugPrint('[NotificationService] Error initializing FCM: $e');
    }
  }

  Future<void> syncTokenWithBackend([String? token]) async {
    try {
      final user = FirebaseAuth.instance.currentUser;
      if (user == null) {
        debugPrint('[NotificationService] User not logged in, skipping token sync');
        return;
      }

      String? fcmToken = token;
      if (fcmToken == null) {
        if (AppPlatform.isIOS) {
          String? apns = await _messaging.getAPNSToken();
          int retryCount = 0;
          while (apns == null && retryCount < 5) {
            debugPrint('[NotificationService] APNS token missing during sync, retrying... ($retryCount/5)');
            await Future.delayed(const Duration(seconds: 1));
            apns = await _messaging.getAPNSToken();
            retryCount++;
          }
          
          if (apns == null) {
             debugPrint('[NotificationService] APNS token still missing after retries, skipping sync');
             return;
          }
        }
        fcmToken = await _messaging.getToken();
      }

      if (fcmToken == null) {
        debugPrint('[NotificationService] FCM token is null, skipping sync');
        return;
      }

      final prefs = PreferencesKey();
      
      // Check if already synced
      final lastSyncedToken = await prefs.readLastSyncedFcmToken();
      final lastSyncedUserId = await prefs.readLastSyncedUserId();
      
      if (lastSyncedToken == fcmToken && lastSyncedUserId == user.uid) {
        // debugPrint('[NotificationService] Device token already successfully synced for this user, skipping');
        return;
      }

      var deviceUuid = await prefs.readDeviceUuid();
      if (deviceUuid == null) {
        deviceUuid = const Uuid().v4();
        await prefs.saveDeviceUuid(deviceUuid);
      }

      String deviceName = 'Unknown';
      String os = AppPlatform.isAndroid ? 'android' : 'ios';

      final deviceInfo = DeviceInfoPlugin();
      if (AppPlatform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        deviceName = '${androidInfo.manufacturer} ${androidInfo.model}';
      } else if (AppPlatform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        debugPrint('[NotificationService] iOS device name: ${iosInfo}');
        deviceName = iosInfo.modelName + " " + iosInfo.systemVersion;
      }

      final callable = FirebaseFunctions.instance.httpsCallable('updateDeviceToken');
      await callable.call({
        'random_uuid': deviceUuid,
        'name': deviceName,
        'os': os,
        'sendnotifyToken': fcmToken,
      });
      
      // Update sync state
      await prefs.saveLastSyncedFcmToken(fcmToken);
      await prefs.saveLastSyncedUserId(user.uid);
      
      debugPrint('[NotificationService] Device token synced with backend');
    } catch (e) {
      debugPrint('[NotificationService] Error syncing token with backend: $e');
    }
  }

  void dispose() {}

  Future<void> _onReceiveNotification(
    NotificationResponse notificationResponse,
  ) async {
    final payload = notificationResponse.payload;
    if (payload != null) {
      ygLogger(payload);
    }
  }

  Future<void> pushNotification(String message) async {
    if (AppPlatform.isAndroid) {
      await _pushAndroidNotification(message);
    } else {
      await _localNotification.show(id: 0, title: message);
    }
  }

  Future<void> _pushAndroidNotification(String message) async {
    const androidNotificationDetails = AndroidNotificationDetails(
      'app.svyatvpn.com',
      'MVMVpn',
      channelDescription: 'MVMVpn',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
      ticker: 'MVMVpn',
    );
    const notificationDetails = NotificationDetails(
      android: androidNotificationDetails,
    );
    await _localNotification.show(
      id: 0,
      title: message,
      body: null,
      notificationDetails: notificationDetails,
    );
  }
}
