# Debug Environment Setup

This guide is for MVMVpn developers. It describes the minimum setup for the **local debug environment** and does not cover release, store submission, signing, or fastlane publishing.

## 1. Initialize the project

This repository pins Flutter with `.fvmrc`. After cloning the repository, install FVM first:

```shell
# macOS / Linux
curl -fsSL https://fvm.app/install.sh | bash
export PATH="$HOME/fvm/bin:$PATH"

# Windows
choco install fvm
```

Then run in the repository root:

```shell
fvm install
fvm flutter pub get
```

Then prepare the local config files needed for debugging:

```shell
cp .env.example .env
cp firebase.json.example firebase.json
cp lib/firebase_options.dart.example lib/firebase_options.dart
cp android/app/google-services.json.example android/app/google-services.json
cp swift/AppStore/GoogleService-Info.plist.example swift/AppStore/GoogleService-Info.plist
cp swift/macOSSE/GoogleService-Info.plist.example swift/macOSSE/GoogleService-Info.plist
```

The `.example` files are enough for local development. Replace them with your own config later if you need to test real Firebase or AdMob behavior.

## 2. Prepare libMVM artifacts

Local MVMVpn debugging depends on artifacts built from the sibling `libMVM` repository. The main outputs from `libMVM/build` are:

- Apple: `LibMVM.xcframework`
- Android: `libMVM.aar`, `libMVM-sources.jar`
- Linux: `linux_so/libMVM.so`, `bin/xray`
- Windows: `windows_dll/libMVM.dll`, `bin/xray.exe`

Build the required targets in `libMVM` first:

```shell
cd ../libMVM
python3 build/main.py apple go
python3 build/main.py android
python3 build/main.py linux
python3 build/main.py windows
```

Then copy the artifacts into the corresponding MVMVpn directories.

### iOS / macOS

Apple platforms share `LibMVM.xcframework`. Copy it into `swift/All/`:

```shell
cp -R ../libXray/LibMVM.xcframework swift/All/
```

`swift/All/` already contains Swift integration files such as `BridgeHeader.h`; in practice you mainly update `LibMVM.xcframework` here.

### Android

Android uses the `aar` and the sources jar. Copy them into `android/app/libs/`:

```shell
mkdir -p android/app/libs
cp ../libMVM/libMVM.aar android/app/libs/
cp ../libMVM/libMVM-sources.jar android/app/libs/
```

### Linux

`linux/app.cmake` links `libMVM.so` from `linux/app/` and installs `MVMVpnCore` into the final bundle. Copy the Linux artifacts into `linux/app/`, and rename `bin/xray` to match MVMVpn's expected name:

```shell
mkdir -p linux/app
cp ../libMVM/linux_so/libMVM.so linux/app/
cp ../libMVM/bin/xray linux/app/MVMVpnCore
```

### Windows

`windows/app.cmake` installs `libMVM.dll` and `MVMVpnCore.exe` from `windows/app/`. Copy the Windows artifacts into `windows/app/`, and rename `bin/xray.exe` to match MVMVpn's expected name:

```shell
mkdir -p windows/app
cp ../libMVM/windows_dll/libMVM.dll windows/app/
cp ../libMVM/bin/xray.exe windows/app/MVMVpnCore.exe
```

> `windows/app.cmake` also packages `wintun.dll`. That file does not come from `libMVM` and must be prepared separately in the Windows development environment.

### Geo Data

Copy the geo data files from `libMVM/dat` into `assets/dat/`, and rename `timestamp.txt` to `timestamp`:

```shell
mkdir -p assets/dat
cp ../libMVM/dat/geoip.dat assets/dat/
cp ../libMVM/dat/geosite.dat assets/dat/
cp ../libMVM/dat/timestamp.txt assets/dat/timestamp
```

### Generated Code

Generate the FFI bindings and other boilerplate code:

```shell
fvm dart run ffigen
fvm dart run build_runner build --delete-conflicting-outputs
```

## 3. Start debugging

Run the target platform with:

```shell
fvm flutter run -d android
fvm flutter run -d macos
```

Before debugging Linux, install the local build dependencies:

```shell
sudo apt-get update
sudo apt-get install -y \
  ninja-build clang cmake pkg-config \
  libgtk-3-dev liblzma-dev libblkid-dev libsecret-1-dev \
  libayatana-appindicator3-dev \
  file
fvm flutter run -d linux
```

Before debugging iOS, install CocoaPods dependencies:

```shell
cd ios
pod install
cd ..
fvm flutter run -d ios
```

## 4. `.env` notes

For local debugging, `.env` can usually stay empty:

- If `ADMOB_APP_ID_ANDROID` or `ADMOB_APP_ID_IOS` is empty, MVMVpn falls back to Google's official test App ID.
- If `ADMOB_AD_UNIT_ID_ANDROID` or `ADMOB_AD_UNIT_ID_IOS` is empty, no real ad unit IDs are injected.
- `FASTLANE_*` variables are only for release flows and are not required for debugging.

You only need to `source .env` and set `BUILD_NUMBER` when running the repository's packaging scripts.

## 5. Related `.gitignore` files

The following paths are ignored by `.gitignore`. In the **debug environment**, they should be understood like this:

| Path | Role in debug setup | Notes |
| ---- | ------------------- | ----- |
| `android/fastlane/playservice.json` | Not used | Only used for Play Store publishing. |
| `android/keystore/` | Not used | Only used for Android release signing; local debug uses the debug keystore. |
| `ios/fastlane/AuthKey.p8` | Not used | Only used for iOS release. |
| `macos/fastlane/AuthKey.p8` | Not used | Only used for Mac App Store release. |
| `macos_se/fastlane/AuthKey.p8` | Not used | Only used for macOS SE release / notarization. |
| `ios/Flutter/AdMob.xcconfig` | Optional | If missing, iOS uses the default test App ID; release scripts can also generate it automatically. |
| `swift/AppStore/GoogleService-Info.plist` | Provide when needed | Used when debugging iOS / macOS with Firebase enabled. |
| `swift/macOSSE/GoogleService-Info.plist` | Provide when needed | Used when debugging macOS SE with Firebase enabled. |

## 6. Files commonly used in debug

These are the files you will usually touch more often in local development:

| Path | Purpose |
| ---- | ------- |
| `swift/All/LibMVM.xcframework` | Apple libMVM artifact used by iOS / macOS. |
| `android/app/libs/libMVM.aar` | Android libMVM package. |
| `android/app/libs/libMVM-sources.jar` | Matching sources jar for Android. |
| `linux/app/libMVM.so` | Shared library linked by the Linux desktop app. |
| `linux/app/MVMVpnCore` | Core binary used by the Linux desktop app. |
| `windows/app/libMVM.dll` | Dynamic library loaded by the Windows desktop app. |
| `windows/app/MVMVpnCore.exe` | Core binary used by the Windows desktop app. |
| `lib/firebase_options.dart` | Flutter-side Firebase initialization config. |
| `android/app/google-services.json` | Android Firebase config. |
| `swift/AppStore/GoogleService-Info.plist` | Firebase plist for the iOS / macOS App Store targets. |
| `swift/macOSSE/GoogleService-Info.plist` | Firebase plist for the macOS SE target. |

The repository already provides matching `.example` files. For the first debug setup, copying those files is enough.

## 7. Minimal setup summary

For local development and breakpoint debugging, the minimum setup is:

1. Copy the `.example` config files.
2. Build `libMVM` and copy its artifacts into the corresponding MVMVpn directories.
3. Prepare the geo data in `assets/dat/`.
4. Run `fvm install` and `fvm flutter pub get`.
5. Run `ffigen` and `build_runner`.
6. Install platform-specific dependencies when needed, such as `pod install` on Apple platforms and `libayatana-appindicator3-dev` on Linux.
7. Start the app with `fvm flutter run -d <device>`.

Files such as `playservice.json`, `android/keystore/`, and the platform `AuthKey.p8` files are part of the release workflow, not the debug environment bootstrap.
