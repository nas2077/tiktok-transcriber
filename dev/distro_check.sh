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
packages=$2

desktop_basics() {
    # Xvfb plays the screen; Mesa's DRI drivers give it OpenGL, as on a desktop
    if command -v apt-get >/dev/null; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth libgl1-mesa-dri
    elif command -v dnf >/dev/null; then
        dnf install -y xorg-x11-server-Xvfb xorg-x11-xauth mesa-dri-drivers which
    elif command -v zypper >/dev/null; then
        zypper --non-interactive install xvfb-run Mesa-dri
    elif command -v pacman >/dev/null; then
        pacman -S --noconfirm xorg-server-xvfb xorg-xauth mesa
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
        image=$(ls "$PWD/$packages"/*.AppImage)
        chmod +x "$image"
        printf '#!/bin/sh\nAPPIMAGE_EXTRACT_AND_RUN=1 exec "%s" "$@"\n' "$image" > /usr/local/bin/tiktok-transcriber
        chmod +x /usr/local/bin/tiktok-transcriber ;;
esac
set +e
desktop_basics

tiktok-transcriber --version || { echo "the installed app does not start"; exit 1; }
if command -v xvfb-run >/dev/null; then
    timeout 40 xvfb-run -a tiktok-transcriber
else
    echo "no Xvfb on this system: using Qt's offscreen platform"
    QT_QPA_PLATFORM=offscreen timeout 40 tiktok-transcriber
fi
code=$?
crash="$HOME/.local/share/tiktok-transcriber/crash.log"
if [ -f "$crash" ]; then cat "$crash"; exit 1; fi
# timeout's 124 means it was still running when the 40 seconds were up
[ "$code" = 124 ] || { echo "TikTok Transcriber exited early with code $code"; exit 1; }
echo "Installed ($kind) and stayed open for 40 seconds."
