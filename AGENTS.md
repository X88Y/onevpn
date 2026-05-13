# MVMVpn — Agent Guide

> This file is written for AI coding agents. If you are reading this, you are expected to know nothing about the project beyond what is written here. Do not assume conventions that are not documented.

---

## Project Overview

MVMVpn is a cross-platform VPN client application built with Flutter. It wraps the Xray-core engine (via the sibling `libXray` project) and provides a unified UI for Android, iOS, macOS, Windows, and Linux.

The repository contains three major parts:

1. **Flutter App** (`lib/`, `android/`, `ios/`, `macos/`, `macos_se/`, `windows/`, `linux/`, `swift/`) — the client UI and platform-specific glue.
2. **Backend Services** (`backend/`) — Python services (Telegram/VK bots, a FastAPI server manager, and a monitoring stack) plus Firebase Cloud Functions written in TypeScript.
3. **Build Scripts** (`build_scripts/`) — Python tooling (Poetry + Typer) that drives Flutter builds, updates build numbers, and packages release artifacts.

The app supports localization (English, Chinese, Russian, Persian), Firebase Auth (Apple Sign-In, anonymous), in-app subscriptions, push notifications, and deep linking.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Flutter 3.x (Dart >= 3.8.0) |
| State Management | `flutter_bloc` |
| Routing | `go_router` |
| Local DB | Drift (SQLite) |
| Localizations | `flutter_localizations` + ARB files |
| Native Android | Kotlin (Pigeon host API, VPN service) |
| Native iOS/macOS | Swift + `LibXray.xcframework` |
| Native Desktop | C FFI via `ffigen` (Linux/Windows) |
| Backend API | Python 3.12 + FastAPI (`server_manager`) |
| Backend Bots | Python 3 + `aiogram` / `vkbottle` |
| Cloud Functions | Firebase Functions (Node.js 20 + TypeScript) |
| CI/CD | GitHub Actions (backend deploy only) |
| Release Packaging | Fastlane (iOS/macOS/Android) + custom Python scripts (desktop) |

---

## Repository Structure

```
MVMVpn/
├── lib/                          # Dart source
│   ├── core/                     # Foundations (DB, FFI, Pigeon, network, models, tools)
│   ├── pages/                    # UI pages organized by feature
│   ├── service/                  # Business-logic services (VPN, auth, subscription, ping, etc.)
│   ├── l10n/                     # Localization files (ARB → generated Dart)
│   ├── gen/                      # Generated asset references (flutter_gen)
│   ├── main.dart                 # Entry point
│   └── firebase_options.dart     # Firebase config (gitignored, has .example)
│
├── android/                      # Android project (Kotlin)
├── ios/                          # iOS project (CocoaPods)
├── macos/                        # Mac App Store target
├── macos_se/                     # macOS Standalone (Developer ID) target
├── windows/                      # Windows CMake build
├── linux/                        # Linux CMake build
├── swift/                        # Shared Swift code + xcframework home
│   ├── All/                      # LibXray.xcframework + bridge files
│   ├── App/                      # iOS app-specific Swift
│   ├── AppStore/                 # App Store plist / config
│   ├── Tunnel/                   # NetworkExtension tunnel
│   ├── macOS/                    # macOS app-specific Swift
│   ├── macOSSE/                  # macOS SE app-specific Swift
│   └── macOSStore/               # Mac App Store specific Swift
│
├── backend/
│   ├── functions/                # Firebase Cloud Functions (TypeScript)
│   ├── server_manager/           # FastAPI service for VPN server lifecycle
│   ├── bot/                      # Telegram & VK user bots
│   ├── bot_admin/                # Telegram admin bot
│   ├── monitoring/               # Prometheus + Grafana (docker-compose)
│   ├── deploy.sh                 # Remote VPS deploy script
│   └── firebase.json             # Firebase project config
│
├── build_scripts/                # Python build tooling
│   ├── app/                      # Per-platform builders (android, apple, linux, windows)
│   ├── main.py                   # CLI entry point (Typer)
│   └── pyproject.toml            # Poetry manifest
│
├── assets/                       # Images, icons, markdown docs, geo data
├── c/include/                    # C header for ffigen (`libXray.h`)
├── pigeon/                       # Pigeon message definitions
├── readme/                       # Human docs (FIRST_RUN.md, etc.)
└── .github/workflows/            # CI/CD (backend deploy only)
```

---

## Build and Test Commands

### Prerequisites

- Install FVM (Flutter Version Management). The project pins a Flutter version in `.fvmrc`.
- Install Python 3.12+ and Poetry for build scripts.
- For local debugging, copy all `.example` config files to their real names (see `readme/FIRST_RUN.md`).
- The app requires **pre-built `libXray` artifacts** for every target platform. These are built from the sibling `libXray` repository and copied into platform-specific directories (see `readme/FIRST_RUN.md` for exact copy commands).

### Common Commands

```bash
# Install Flutter SDK pinned by .fvmrc
fvm install
fvm flutter pub get

# Run code generators (must be done after changing Drift tables, JSON models, or Pigeon definitions)
fvm dart run build_runner build --delete-conflicting-outputs
fvm dart run pigeon --input pigeon/message.dart
fvm dart run ffigen

# Debug on a target device
fvm flutter run -d android
fvm flutter run -d ios      # requires `pod install` in ios/ first
fvm flutter run -d macos
fvm flutter run -d linux    # requires Linux desktop dependencies
fvm flutter run -d windows

# Run the Python build script for releases
cd build_scripts
poetry install
poetry run python main.py build --project MVMVpn --system <android|ios|macos|linux|windows>
```

### Generated Files

The following files are generated and should **not** be edited manually:

- `lib/core/pigeon/messages.g.dart`
- `lib/core/ffi/generated_bindings.dart`
- `lib/core/**/*.g.dart` (json_serializable, drift)
- `lib/gen/assets.gen.dart`
- `lib/l10n/localizations/app_localizations*.dart`

Regenerate them with the commands listed above.

### Testing

There is **no automated test suite** currently in the repository. The `test/` directory is gitignored. When modifying code, rely on manual debugging via `flutter run` and platform emulators/devices.

---

## Code Style Guidelines

- **Linter**: `analysis_options.yaml` includes `package:flutter_lints/flutter.yaml` and enforces `always_use_package_imports`.
- **Imports**: Always use `package:mvmvpn/...` imports. Never use relative imports across `lib/` boundaries.
- **Generated code suffix**: `.g.dart` for `json_serializable`, `drift_dev`, and `pigeon` outputs.
- **State management**: Prefer `flutter_bloc` (Cubit / Bloc) for page-level state and complex service logic.
- **Navigation**: `go_router` is used for declarative routing. Routes are defined in `lib/pages/main/router.dart`.
- **Models**: JSON-serializable models use `json_annotation` + `json_serializable`. Hand-written models are in `lib/core/model/` and `lib/service/**/model.dart`.
- **Database**: Drift is used for local persistence. Table definitions are in `lib/core/db/table/`. DAOs are in `lib/core/db/dao/`.
- **Platform channel**: Do **not** write raw `MethodChannel` code. Use **Pigeon** (`pigeon/message.dart`) for type-safe platform communication. The generated Kotlin and Swift files live in `android/app/src/main/kotlin/.../pigeon/` and `swift/App/pigeon/`.
- **Desktop FFI**: Linux and Windows talk to `libXray` via `dart:ffi`. Bindings are generated by `ffigen` from `c/include/libXray.h`.

---

## Key Module Divisions

### `lib/core/`
Foundational code with no UI dependencies.
- `db/` — Drift database, tables, DAOs.
- `ffi/` — FFI bindings and platform-specific wrappers (`linux_ffi_api.dart`, `windows_ffi_api.dart`).
- `pigeon/` — Pigeon-generated and hand-written model adapters for platform channels.
- `network/` — HTTP client wrappers and network models.
- `model/` — Pure Dart data classes for Xray JSON, geo data, ping results, etc.
- `tools/` — Platform detection, file helpers, JSON utilities, logger, extensions.

### `lib/service/`
Business logic organized by domain. Each service is typically a singleton or a class accessed via context.
- `vpn/` — VPN tunnel lifecycle (start/stop/status).
- `auth/` — Firebase Auth state and Apple Sign-In.
- `subscription/` — Subscription list management and validation.
- `sub_update/` — Remote subscription update logic.
- `xray/` — Xray configuration builders (outbounds, routing, DNS, inbounds, etc.).
- `ping/` — Latency testing state and service.
- `geo_data/` — GeoIP/GeoSite data management.
- `share/` — Import/export of configs and backups.
- `notification/` — Local push notifications.
- `background_task/` — Background refresh logic.
- `event_bus/` — Global app event bus (theme, locale changes).

### `lib/pages/`
UI pages following a feature-folder convention. Each page typically has:
- `page.dart` — The widget.
- `controller.dart` — The `Cubit` or `Bloc`.
- `params.dart` — Route argument classes (if any).

Major feature areas:
- `home/` — Main VPN screen, config rows, subscription pills, node info, settings, share, Xray raw editing.
- `setting/` — App settings (theme, language, logs, backup, ping, TUN, app icon).
- `subscription/` — Add / edit subscription URLs.
- `geo_data/` — Add / list / select / show geo data rules.
- `launch/` — Splash, privacy, first-run onboarding.
- `main/` — Root router and menu.

---

## Backend Architecture

### Firebase Cloud Functions (`backend/functions/`)
TypeScript functions deployed to Firebase. Key functions:
- User sync / Apple user creation handlers.
- VPN key generation and regeneration.
- Trial start logic.
- Payment webhooks (Heleket, PlateGa, FreeKassa).
- Public constants endpoint.
- Device token updates for push notifications.

### Server Manager (`backend/server_manager/`)
A FastAPI (Uvicorn) service that runs on a VPS. It manages VPN server lifecycle:
- Provisions inbounds on VPN panels.
- Syncs traffic usage to Firestore.
- Health checks servers.
- Serves subscription configs to clients.

Configuration is loaded from `backend/server_manager/.env` (see `config.py` for required variables). It requires `MANAGER_API_KEY`, `SERVER_MANAGER_FERNET_KEY`, `MANAGER_PUBLIC_URL`, and optional Firebase credentials.

### Bots (`backend/bot/`, `backend/bot_admin/`)
- `bot/` — Customer-facing Telegram and VK bots for support and key retrieval.
- `bot_admin/` — Admin Telegram bot for server management and payment monitoring.

Both read `TELEGRAM_BOT_TOKEN` (or `BOT_TOKEN`) from their respective `.env` files and share the same Firebase credential lookup logic.

### Monitoring (`backend/monitoring/`)
Docker Compose stack with Prometheus and Grafana. The `server_manager` exposes metrics that are scraped by Prometheus.

---

## Deployment Processes

### Backend (VPS)
Pushing to `main` with changes under `backend/**` triggers `.github/workflows/deploy-backend.yml`. The workflow:
1. SSHs into `92.118.232.155`.
2. Runs `backend/deploy.sh`.
3. The script rsyncs code, creates a Python venv, installs dependencies from `requirements.txt` files, creates systemd services, and restarts them.

Services deployed:
- `mvm-tg-bot.service`
- `mvm-vk-bot.service`
- `mvm-server-manager.service`
- `mvm-admin-bot.service`

### Firebase Functions
Deployed manually or via Firebase CLI (`firebase deploy --only functions`) from the `backend/functions/` directory.

### Client Apps
Built locally via `build_scripts/main.py` or Fastlane lanes. The Python script:
1. Updates the build number in `pubspec.yaml`.
2. Runs `flutter pub get`.
3. Runs `ffigen`.
4. Runs `flutter build <platform>` with optional `--dart-define` for AdMob.
5. Copies release artifacts to `dist/` or platform-specific output dirs.

Fastlane is configured under `android/fastlane/`, `ios/fastlane/`, `macos/fastlane/`, and `macos_se/fastlane/`. Signing secrets (`AuthKey.p8`, keystores, etc.) are gitignored.

---

## Security Considerations

- **Firestore rules** (`backend/firestore.rules`) deny all direct client read/write. The backend services and Cloud Functions are the only authorized accessors.
- **API keys** (`MANAGER_API_KEY`) and **Fernet keys** (`SERVER_MANAGER_FERNET_KEY`) must be strong and stored only in server `.env` files.
- **Firebase service account JSON** is gitignored. It is looked up via `GOOGLE_APPLICATION_CREDENTIALS` or copied into the backend directory at deploy time.
- **Signing material** (`.p8`, `.p12`, `.jks`, `.mobileprovision`) is gitignored globally.
- **AdMob IDs** are injected at build time via `--dart-define` and are not hard-coded in the source.
- **Desktop binaries** (`MVMVpnCore`, `libXray.so`, `libXray.dll`) are built externally and copied in; do not commit prebuilt native libraries.

---

## Quick Reference for Agents

| Task | Command / File |
|------|----------------|
| Add a new route | `lib/pages/main/router.dart` + `lib/pages/main/url.dart` |
| Add a new table | `lib/core/db/table/<name>.dart`, then run `build_runner` |
| Add a new JSON model | `lib/core/model/<name>.dart` with `@JsonSerializable()`, then run `build_runner` |
| Add a platform channel method | `pigeon/message.dart`, then run `pigeon` command |
| Add a new FFI binding | Update `c/include/libXray.h`, then run `ffigen` |
| Add a new asset | Drop into `assets/`, run `build_runner` for `flutter_gen` |
| Add a new locale string | Add to `lib/l10n/app_<lang>.arb`, run `flutter gen-l10n` |
| Change backend env vars | Edit the respective `.env` in `backend/server_manager/` or `backend/bot_admin/` |
| Deploy backend | Push to `main` with changes in `backend/**` |
| Build release | `cd build_scripts && poetry run python main.py build --project MVMVpn --system <platform>` |

---

## Notes

- The project uses **FVM**. Always prefix Flutter/Dart commands with `fvm` (e.g., `fvm flutter run`, `fvm dart run build_runner build`).
- `macos_se/` is a special target for macOS Standalone (Developer ID, outside the Mac App Store). The build script temporarily replaces `macos/` with `macos_se/` before building. Run `git checkout -- macos/` to restore the MAS configuration afterward.
- Desktop builds (Linux/Windows) require `libXray` artifacts and a helper binary named `MVMVpnCore` (the Xray-core executable). See `readme/FIRST_RUN.md` for exact copy instructions.
- The app reads `String.fromEnvironment` for AdMob unit IDs at compile time; empty values safely fall back to Google's test ads.
