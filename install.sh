#!/bin/sh
# TikTok Transcriber installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/nas2077/tiktok-transcriber/main/install.sh | sh
#
# No root needed. macOS: TikTok Transcriber.app goes to /Applications (or ~/Applications).
# Linux: the app goes to ~/.local/share/tiktok-transcriber, the `tiktok-transcriber` command to
# ~/.local/bin and a menu entry to ~/.local/share/applications.
#
# Environment: TIKTOK_TRANSCRIBER_VERSION=0.2.0 installs that version instead of the
# latest; TIKTOK_TRANSCRIBER_UNINSTALL=1 removes TikTok Transcriber (settings and models stay).
# TIKTOK_TRANSCRIBER_MIRROR=<url> downloads the release files from there instead of
# GitHub (the release workflow tests this script against a local server).
set -eu

REPO="https://github.com/nas2077/tiktok-transcriber"
APP_ID="io.github.nas2077.TikTokTranscriber"

say() { printf '%s\n' "$*"; }
fail() { printf 'tiktok-transcriber: %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

fetch() { # url target
    if has curl; then
        if [ -n "${TIKTOK_TRANSCRIBER_MIRROR:-}" ]; then
            curl -fL --retry 3 --progress-bar -o "$2" "$1"
        else
            curl -fL --proto '=https' --tlsv1.2 --retry 3 --progress-bar -o "$2" "$1"
        fi
    elif has wget; then
        wget -q --show-progress -O "$2" "$1"
    else
        fail "curl or wget is required"
    fi
}

latest_version() {
    if has curl; then
        url=$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$REPO/releases/latest")
    else
        url=$(wget -q --max-redirect=0 -S "$REPO/releases/latest" 2>&1 | sed -n 's/^ *[Ll]ocation: *//p' | tr -d '\r')
    fi
    case "$url" in
        */tag/v*) printf '%s\n' "${url##*/tag/v}" ;;
        *) fail "could not find the latest release" ;;
    esac
}

verify() { # file name sums
    expected=$(grep " [*]\{0,1\}$2\$" "$3" | cut -d' ' -f1)
    [ -n "$expected" ] || fail "$2 is not in the checksums"
    if has sha256sum; then
        actual=$(sha256sum "$1" | cut -d' ' -f1)
    elif has shasum; then
        actual=$(shasum -a 256 "$1" | cut -d' ' -f1)
    else
        fail "sha256sum or shasum is required"
    fi
    [ "$expected" = "$actual" ] || fail "checksum mismatch for $2: the download is damaged"
}

uninstall_mac() {
    for dir in /Applications "$HOME/Applications"; do
        [ -d "$dir/TikTok Transcriber.app" ] && rm -rf "$dir/TikTok Transcriber.app" && say "Removed $dir/TikTok Transcriber.app"
    done
    return 0
}

uninstall_linux() {
    rm -rf "$HOME/.local/share/tiktok-transcriber/app"
    rm -f "$HOME/.local/bin/tiktok-transcriber" \
          "$HOME/.local/share/applications/$APP_ID.desktop" \
          "$HOME/.local/share/icons/hicolor/512x512/apps/$APP_ID.png"
    say "Removed TikTok Transcriber from ~/.local"
}

install_mac() {
    case "$(uname -m)" in
        arm64) arch=arm64 ;;
        x86_64) arch=x64 ;;
        *) fail "unsupported Mac: $(uname -m)" ;;
    esac
    name="TikTok-Transcriber-$VERSION-macos-$arch.dmg"
    fetch "$BASE/$name" "$TMP/$name"
    verify "$TMP/$name" "$name" "$TMP/SHA256SUMS.txt"
    mkdir "$TMP/mount"
    hdiutil attach -nobrowse -readonly -quiet -mountpoint "$TMP/mount" "$TMP/$name"
    target=/Applications
    [ -w "$target" ] || { target="$HOME/Applications"; mkdir -p "$target"; }
    rm -rf "$target/TikTok Transcriber.app"
    ditto "$TMP/mount/TikTok Transcriber.app" "$target/TikTok Transcriber.app"
    hdiutil detach -quiet "$TMP/mount" || true
    # the app is not notarized: downloaded this way it carries no quarantine
    # flag, and this makes sure an older copy's flag does not linger
    xattr -dr com.apple.quarantine "$target/TikTok Transcriber.app" 2>/dev/null || true
    say ""
    say "TikTok Transcriber $VERSION is in $target. Open it from Launchpad, or run: open -a \"TikTok Transcriber\""
}

install_linux() {
    case "$(uname -m)" in
        x86_64|amd64) arch=x86_64 ;;
        aarch64|arm64) arch=aarch64 ;;
        *) fail "unsupported processor: $(uname -m). TikTok Transcriber runs on x86_64 and aarch64." ;;
    esac
    if ldd --version 2>&1 | grep -qi musl; then
        fail "this system uses musl (like Alpine). TikTok Transcriber needs a glibc distribution; try the Flatpak."
    fi
    # x86_64 is built on Ubuntu 22.04, aarch64 on 24.04 (Qt's ARM wheels need it)
    if [ "$arch" = x86_64 ]; then floor=35; systems="Ubuntu 22.04, Debian 12, Fedora 36, RHEL 10"
    else floor=39; systems="Ubuntu 24.04, Debian 13, Fedora 40"; fi
    glibc=$(ldd --version 2>/dev/null | sed -n '1s/.* \([0-9][0-9]*\.[0-9][0-9]*\)$/\1/p')
    if [ -n "$glibc" ]; then
        major=${glibc%%.*}; minor=${glibc#*.}
        if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt "$floor" ]; }; then
            fail "glibc $glibc found; TikTok Transcriber for $arch needs 2.$floor or newer ($systems or later). On this system, install the Flatpak from $REPO/releases instead."
        fi
    fi
    name="TikTok-Transcriber-$VERSION-linux-$arch.tar.gz"
    fetch "$BASE/$name" "$TMP/$name"
    verify "$TMP/$name" "$name" "$TMP/SHA256SUMS.txt"
    home="$HOME/.local/share/tiktok-transcriber"
    mkdir -p "$home" "$HOME/.local/bin" "$HOME/.local/share/applications" \
             "$HOME/.local/share/icons/hicolor/512x512/apps"
    tar -xzf "$TMP/$name" -C "$TMP"
    rm -rf "$home/app"
    mv "$TMP/tiktok-transcriber" "$home/app"
    ln -sf "$home/app/tiktok-transcriber" "$HOME/.local/bin/tiktok-transcriber"
    mv "$home/app/$APP_ID.png" "$HOME/.local/share/icons/hicolor/512x512/apps/$APP_ID.png"
    sed "s|^Exec=.*|Exec=$home/app/tiktok-transcriber|" "$home/app/$APP_ID.desktop" \
        > "$HOME/.local/share/applications/$APP_ID.desktop"
    rm -f "$home/app/$APP_ID.desktop" "$home/app/$APP_ID.metainfo.xml"
    has update-desktop-database && update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
    has gtk-update-icon-cache && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    say ""
    say "TikTok Transcriber $VERSION is installed. Find it in your applications menu, or run: tiktok-transcriber"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) say "Add ~/.local/bin to your PATH to use the tiktok-transcriber command." ;;
    esac
}

main() {
    system=$(uname -s)
    if [ "${TIKTOK_TRANSCRIBER_UNINSTALL:-}" = 1 ]; then
        case "$system" in
            Darwin) uninstall_mac ;;
            Linux) uninstall_linux ;;
            *) fail "unsupported system: $system" ;;
        esac
        say "Settings, downloaded models and transcripts were kept."
        return
    fi
    VERSION=${TIKTOK_TRANSCRIBER_VERSION:-$(latest_version)}
    VERSION=${VERSION#v}
    BASE=${TIKTOK_TRANSCRIBER_MIRROR:-$REPO/releases/download/v$VERSION}
    TMP=$(mktemp -d)
    # with set -e a failing command in the trap would become the exit code:
    # hdiutil only exists on macOS, and the disk image may already be detached
    trap 'hdiutil detach -quiet "$TMP/mount" 2>/dev/null || true; rm -rf "$TMP"' EXIT INT TERM
    say "Installing TikTok Transcriber $VERSION"
    fetch "$BASE/SHA256SUMS.txt" "$TMP/SHA256SUMS.txt"
    case "$system" in
        Darwin) install_mac ;;
        Linux) install_linux ;;
        *) fail "unsupported system: $system. On Windows use install.ps1." ;;
    esac
}

main "$@"
