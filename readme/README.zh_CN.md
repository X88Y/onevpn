# MVMVpn

## 应用介绍

关注我们的 Telegram 频道：[MVMVpn](https://t.me/MVMVpnApp)

[文档站](https://mvmvpn.com)

[First Run 指南](./FIRST_RUN.zh_CN.md)

## 下载

| 操作系统 | 版本                   | CPU 架构             | 安装包格式 | 下载链接                                                                                                                   |
| -------- | ---------------------- | -------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------- |
| Windows  | Windows 10, Windows 11 | x86_64               | exe        | [MVMVpn-windows-amd64.exe](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-windows-amd64.exe)         |
| Windows  | Windows 10, Windows 11 | x86_64               | zip        | [MVMVpn-windows-amd64.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-windows-amd64.zip)         |
| Android  | Android 10.0 及以上    | arm32, arm64, x86_64 | aab        | [Google Play Store](https://play.google.com/store/apps/details?id=com.svyatvpn.app)                                     |
| Android  | Android 10.0 及以上    | arm32, arm64, x86_64 | apk        | [MVMVpn-android-universal.apk](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-android-universal.apk) |
| iOS      | iOS 15.0 及以上        | arm64                | ipa        | [App Store](https://apps.apple.com/us/app/mvmvpn/id6745748773)                                                            |
| iOS      | iOS 15.0 及以上        | arm64                | ipa        | [MVMVpn-ios.ipa](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-ios.ipa)                             |
| macOS    | macOS 12.0 及以上      | Apple silicon, Intel | pkg        | [Mac App Store](https://apps.apple.com/us/app/mvmvpn/id6745748773)                                                        |
| macOS    | macOS 12.0 及以上      | Apple silicon, Intel | zip        | [MVMVpn-macos-universal.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-macos-universal.zip)     |
| Linux    | GLIBC >= 2.39          | x86_64               | deb        | [MVMVpn-linux-x86_64.deb](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-x86_64.deb)           |
| Linux    | GLIBC >= 2.39          | x86_64               | zip        | [MVMVpn-linux-x86_64.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-x86_64.zip)           |
| Linux    | GLIBC >= 2.39          | arm64                | deb        | [MVMVpn-linux-aarch64.deb](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-aarch64.deb)         |
| Linux    | GLIBC >= 2.39          | arm64                | zip        | [MVMVpn-linux-aarch64.zip](https://github.com/MVMVpn/MVMVpn/releases/latest/download/MVMVpn-linux-x86_64.zip)          |

## 使用注意

### iOS

若您没有 Apple ID ，或您的 Apple ID 无法下载 MVMVpn ，您可以下载 **MVMVpn-ios.ipa** ，然后使用 [AltStore](https://altstore.io/) 或
其他第三方工具进行安装。

### Linux

若您使用 zip 包，您需要进行如下设置才可正常使用 MVMVpn。

执行指令前请确认目录。

```shell
sudo apt install -y procps libcap2-bin libayatana-appindicator3-1
sudo setcap cap_net_admin,cap_net_raw+eip MVMVpn/bin/MVMVpnCore
```

若您使用 deb 包，您可使用如下指令进行安装和卸载。

```shell
sudo apt install ./MVMVpn-linux-x86_64.deb
sudo apt remove mvmvpn
```

若您的桌面环境为 gnome，请安装 [AppIndicator](https://github.com/ubuntu/gnome-shell-extension-appindicator) 扩展。

若您的机器 CPU 架构为 Arm64，当您将语言切换为 CJK（中文，日文，韩文）时，MVMVpn 会将界面语言修正为英文。

### 内核升级

在 Linux 和 Windows 平台，您可自行升级或替换 Xray-core 。您可按照 [libXray](https://github.com/XTLS/libXray) 中的指引，使用 build 脚本进行编译。

#### Linux

将 `MVMVpn/lib/libXray.so` 替换为 libXray 的编译产物 `linux_so/libXray.so` 。

将 `MVMVpn/bin/MVMVpnCore` 替换为 libXray 的编译产物 `bin/xray` 。

#### Windows

将 `MVMVpn/libXray.dll` 替换为 libXray 的编译产物 `windows_dll/libXray.dll` 。

将 `MVMVpn/bin/MVMVpnCore.exe` 替换为 libXray 的编译产物 `bin/xray.exe` 。

## 贡献

若本项目对您有所帮助，您可考虑通过以下方式对本项目进行贡献。

1. 给本项目一个 star 。
2. 翻译 App 的文档 [mvmvpn.com](https://github.com/MVMVpn/mvmvpn.com) 。
3. 分享您的路由设置 [Routing](https://github.com/MVMVpn/Routing) 。
