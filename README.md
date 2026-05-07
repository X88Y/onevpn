# MVMVpn

[简体中文](./readme/README.zh_CN.md)

## App Introduction

Follow us on Telegram: [MVMVpn](https://t.me/MVMVpnApp)

[Documentation](https://mvmvpn.com)

[First Run](./readme/FIRST_RUN.md)

## Download

| Operating System | Version                | CPU Architecture     | Installation Package Format | Download Link                                                                                                              |
| ---------------- | ---------------------- | -------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Windows          | Windows 10, Windows 11 | x86_64               | exe                         | [MVMVpn-windows-amd64.exe](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-windows-amd64.exe)         |
| Windows          | Windows 10, Windows 11 | x86_64               | zip                         | [MVMVpn-windows-amd64.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-windows-amd64.zip)         |
| Android          | Android 10.0 and above | arm32, arm64, x86_64 | aab                         | [Google Play Store](https://play.google.com/store/apps/details?id=com.svyatvpn.app)                                     |
| Android          | Android 10.0 and above | arm32, arm64, x86_64 | apk                         | [MVMVpn-android-universal.apk](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-android-universal.apk) |
| iOS              | iOS 15.0 and above     | arm64                | ipa                         | [App Store](https://apps.apple.com/us/app/mvmvpn/id6745748773)                                                            |
| iOS              | iOS 15.0 and above     | arm64                | ipa                         | [MVMVpn-ios.ipa](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-ios.ipa)                             |
| macOS            | macOS 12.0 and above   | Apple silicon, Intel | pkg                         | [Mac App Store](https://apps.apple.com/us/app/mvmvpn/id6745748773)                                                        | \ |
| macOS            | macOS 12.0 and above   | Apple silicon, Intel | zip                         | [MVMVpn-macos-universal.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-macos-universal.zip)     |
| Linux            | GLIBC >= 2.39          | x86_64               | deb                         | [MVMVpn-linux-x86_64.deb](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-x86_64.deb)           |
| Linux            | GLIBC >= 2.39          | x86_64               | zip                         | [MVMVpn-linux-x86_64.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-x86_64.zip)           |
| Linux            | GLIBC >= 2.39          | arm64                | deb                         | [MVMVpn-linux-aarch64.deb](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-aarch64.deb)         |
| Linux            | GLIBC >= 2.39          | arm64                | zip                         | [MVMVpn-linux-aarch64.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-aarch64.zip)         |

## Notes

### iOS

If you don't have an Apple ID, or your Apple ID cannot download MVMVpn, you can download **MVMVpn-ios.ipa** and then use [AltStore](https://altstore.io/) or other third-party tools to install it.

### Linux

If you use the zip package, you need to make the following settings to use MVMVpn normally.

Please confirm the directory before executing the command.

```shell
sudo apt install -y procps libcap2-bin libayatana-appindicator3-1
sudo setcap cap_net_admin,cap_net_raw+eip MVMVpn/bin/MVMVpnCore
```

If you use the deb package, you can use the following commands to install and uninstall.

```shell
sudo apt install ./MVMVpn-linux-x86_64.deb
sudo apt remove mvmvpn
```

If your desktop environment is gnome, please install the [AppIndicator](https://github.com/ubuntu/gnome-shell-extension-appindicator) extension.

If your machine's CPU architecture is Arm64, switching the language to a CJK language (Chinese, Japanese, or Korean) will cause MVMVpn to reset the interface language to English.

### Kernel Upgrade

On Linux and Windows platforms, you can upgrade or replace Xray-core yourself. You can compile it using the build script according to the instructions in [libXray](https://github.com/XTLS/libXray).

#### Linux

Replace `MVMVpn/lib/libXray.so` with the compiled product of libXray `linux_so/libXray.so`.

Replace `MVMVpn/bin/MVMVpnCore` with the compiled product of libXray `bin/xray`.

#### Windows

Replace `MVMVpn/libXray.dll` with the compiled product of libXray `windows_dll/libXray.dll`.

Replace `MVMVpn/bin/MVMVpnCore.exe` with the compiled product of libXray `bin/xray.exe`.

## Contribution

If this project is helpful to you, you can consider contributing to this project in the following ways.

1. Give this project a star.
2. Translate the app's documentation [mvmvpn.com](https://github.com/MVMVpn/mvmvpn.com) .
3. Share your routing settings [Routing](https://github.com/MVMVpn/Routing) .
