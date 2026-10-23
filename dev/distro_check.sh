#!/bin/sh
# Install a built Linux package on a clean distribution and start the app.
#
#   sh dev/distro_check.sh <deb|rpm|arch|appimage> <folder with the packages>
#
# Runs as root inside a distribution container (the release workflow and
# .github/workflows/distro-check.yml). It installs the package with the
# system's own package manager, adds what any desktop already has (an X11
# screen and Mesa's OpenGL drivers), then requires the app to print its
# version and to stay open for 40 seconds without a crash log.
set -u
kind=$1
# absolute: apt reads "pkg/x.deb" as a package name to download
packages=$(cd "$2" && pwd)

desktop_basics() {
    # an X server for the window and Mesa's OpenGL drivers, as any desktop has;
    # one package at a time, so a name one release lacks does not stop the rest
    if command -v apt-get >/dev/null; then
        for p in xvfb libgl1-mesa-dri; do DEBIAN_FRONTEND=noninteractive apt-get install -y "$p"; done
    elif command -v dnf >/dev/null; then
        for p in xorg-x11-server-Xvfb mesa-dri-drivers; do dnf install -y "$p"; done
        command -v Xvfb >/dev/null || { dnf install -y epel-release && dnf install -y xorg-x11-server-Xvfb; }
    elif command -v zypper >/dev/null; then
        for p in xorg-x11-server-Xvfb Mesa-dri; do zypper --non-interactive install "$p"; done
    elif command -v pacman >/dev/null; then
        for p in xorg-server-xvfb mesa; do pacman -S --noconfirm "$p"; done
    fi
}

set -e
case "$kind" in
    deb)
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$packages"/*.deb ;;
    rpm)
        if command -v dnf >/dev/null; then dnf install -y "$packages"/*.rpm
        else zypper --non-interactive install --allow-unsigned-rpm "$packages"/*.rpm; fi ;;
    arch)
        pacman -Syu --noconfirm
        pacman -U --noconfirm "$packages"/*.pkg.tar.zst ;;
    appimage)
        # the libraries a desktop already has, then the AppImage itself
        if command -v dnf >/dev/null; then
            dnf install -y nss alsa-lib mesa-libGL mesa-libEGL libxkbcommon fontconfig dbus-libs libwayland-server
        else
            apt-get update
            DEBIAN_FRONTEND=noninteractive apt-get install -y libnss3 libasound2 libgl1 libegl1 \
                libxkbcommon0 libfontconfig1 libdbus-1-3 libwayland-server0
        fi
        image=$(ls "$packages"/*.AppImage)
        chmod +x "$image"
        printf '#!/bin/sh\nAPPIMAGE_EXTRACT_AND_RUN=1 exec "%s" "$@"\n' "$image" > /usr/local/bin/tiktok-transcriber
        chmod +x /usr/local/bin/tiktok-transcriber ;;
esac
set +e
desktop_basics

tiktok-transcriber --version || { echo "the installed app does not start"; exit 1; }
if command -v Xvfb >/dev/null; then
    # 24-bit color like a real monitor: xvfb-run's default 8-bit screen has no
    # OpenGL configuration, and Qt stops on that
    Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
    server=$!
    sleep 3
    DISPLAY=:99 timeout 40 tiktok-transcriber
    code=$?
    kill "$server" 2>/dev/null
else
    echo "no Xvfb on this system: using Qt's offscreen platform"
    QT_QPA_PLATFORM=offscreen timeout 40 tiktok-transcriber
    code=$?
fi
crash="$HOME/.local/share/tiktok-transcriber/crash.log"
if [ -f "$crash" ]; then cat "$crash"; exit 1; fi
# timeout's 124 means it was still running when the 40 seconds were up
[ "$code" = 124 ] || { echo "TikTok Transcriber exited early with code $code"; exit 1; }
echo "Installed ($kind) and stayed open for 40 seconds."
