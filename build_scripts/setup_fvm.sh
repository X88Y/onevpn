#!/usr/bin/env bash

set -euo pipefail

fvm_root="${FVM_CACHE_PATH:-$HOME/fvm}"
fvm_bin_dir="$fvm_root/bin"
fvm_version="${FVM_VERSION:?FVM_VERSION must be set}"

if command -v python3 >/dev/null 2>&1; then
  python_cmd="python3"
elif command -v python >/dev/null 2>&1; then
  python_cmd="python"
else
  echo "python is required to read .fvmrc" >&2
  exit 1
fi

flutter_version="${FLUTTER_VERSION:-$("$python_cmd" -c 'import json; print(json.load(open(".fvmrc", encoding="utf-8"))["flutter"])')}"

uname_s="$(uname -s)"
uname_m="$(uname -m)"

case "$uname_s" in
  Linux)
    platform="linux"
    archive_ext="tar.gz"
    ;;
  Darwin)
    platform="macos"
    archive_ext="tar.gz"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    platform="windows"
    archive_ext="zip"
    ;;
  *)
    echo "unsupported operating system: $uname_s" >&2
    exit 1
    ;;
esac

case "$uname_m" in
  x86_64|amd64)
    arch="x64"
    ;;
  arm64|aarch64)
    arch="arm64"
    ;;
  *)
    echo "unsupported architecture: $uname_m" >&2
    exit 1
    ;;
esac

asset_name="fvm-${fvm_version}-${platform}-${arch}.${archive_ext}"
asset_url="https://github.com/leoafarias/fvm/releases/download/${fvm_version}/${asset_name}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "$fvm_bin_dir"
archive_path="$tmp_dir/$asset_name"

curl -fsSL "$asset_url" -o "$archive_path"

if [[ "$archive_ext" == "tar.gz" ]]; then
  tar -xzf "$archive_path" -C "$tmp_dir"
else
  archive_win_path="$(cygpath -w "$archive_path")"
  tmp_win_path="$(cygpath -w "$tmp_dir")"
  powershell.exe -NoLogo -NoProfile -Command "Expand-Archive -LiteralPath '$archive_win_path' -DestinationPath '$tmp_win_path' -Force"
fi

if [[ "$platform" == "windows" ]]; then
  fvm_executable_name="fvm.exe"
else
  fvm_executable_name="fvm"
fi

fvm_executable="$(find "$tmp_dir" -type f -name "$fvm_executable_name" | head -n 1)"
if [[ -z "$fvm_executable" ]]; then
  echo "failed to find ${fvm_executable_name} in ${asset_name}" >&2
  exit 1
fi

cp "$fvm_executable" "$fvm_bin_dir/$fvm_executable_name"
if [[ "$platform" != "windows" ]]; then
  chmod +x "$fvm_bin_dir/$fvm_executable_name"
fi

add_to_github_path() {
  local path_value="$1"
  if [[ -z "${GITHUB_PATH:-}" ]]; then
    return
  fi

  if [[ "$platform" == "windows" ]]; then
    cygpath -w "$path_value" >> "$GITHUB_PATH"
  else
    echo "$path_value" >> "$GITHUB_PATH"
  fi
}

add_to_github_env() {
  local name="$1"
  local value="$2"
  if [[ -z "${GITHUB_ENV:-}" ]]; then
    return
  fi

  if [[ "$platform" == "windows" ]]; then
    value="$(cygpath -w "$value")"
  fi
  echo "${name}=${value}" >> "$GITHUB_ENV"
}

export FVM_CACHE_PATH="$fvm_root"
export FVM_USE_GIT_CACHE=false
export PATH="$fvm_bin_dir:$PATH"

add_to_github_path "$fvm_bin_dir"
add_to_github_env "FVM_CACHE_PATH" "$fvm_root"
echo "FVM_USE_GIT_CACHE=false" >> "${GITHUB_ENV:-/dev/null}"

"$fvm_bin_dir/$fvm_executable_name" --version
"$fvm_bin_dir/$fvm_executable_name" install "$flutter_version"

flutter_sdk_dir="$fvm_root/versions/$flutter_version"
flutter_bin_dir="$flutter_sdk_dir/bin"
export PATH="$flutter_bin_dir:$PATH"

add_to_github_path "$flutter_bin_dir"
add_to_github_env "FLUTTER_ROOT" "$flutter_sdk_dir"

flutter --version
