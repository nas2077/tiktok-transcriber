#!/bin/sh
# Install a built Linux package on a clean distribution and start the app.
#
#   sh dev/distro_check.sh <deb|rpm|arch|appimage> <folder with the packages>
#
# Runs as root inside a distribution container (the release workflow and
# .github/workflows/distro-check.yml). It installs the package with the
# system's own package manager, adds what any desktop already has (an X11
# screen and Mesa's OpenGL drivers), then requires the app to print its
# version and to stay open for 40 seconds without a crash log. When the
# default start fails, it also tries Qt's EGL integration on X11 and reports
# that result, so a GLX-only failure can be told apart from a broken package.
set -u
kind=$1
# absolute: apt reads "pkg/x.deb" as a package name to download
packages=$(cd "$2" && pwd)

desktop_basics() {
    # an X server for the window and Mesa's OpenGL drivers, as any desktop has;
    # one package at a time, so a name one release lacks does not stop the rest
    if command -v apt-get >/dev/null; then
        for p in xvfb libgl1-mesa-dri libegl-mesa0; do DEBIAN_FRONTEND=noninteractive apt-get install -y "$p"; done
    elif command -v dnf >/dev/null; then
        for p in xorg-x11-server-Xvfb mesa-dri-drivers mesa-libEGL; do dnf install -y "$p"; done
        command -v Xvfb >/dev/null || { dnf install -y epel-release && dnf install -y xorg-x11-server-Xvfb; }
    elif command -v zypper >/dev/null; then
        for p in xorg-x11-server-Xvfb Mesa-dri Mesa-libEGL1; do zypper --non-interactive install "$p"; done
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
            dnf install -y nss alsa-lib mesa-libGL mesa-libEGL mesa-libgbm libxkbcommon fontconfig dbus-libs \
                libwayland-server libstdc++ expat zlib
        else
            apt-get update
            DEBIAN_FRONTEND=noninteractive apt-get install -y libnss3 libasound2 libgl1 libegl1 \
                libxkbcommon0 libfontconfig1 libdbus-1-3 libwayland-server0 libgbm1 libexpat1
        fi
        image=$(ls "$packages"/*.AppImage)
        chmod +x "$image"
        printf '#!/bin/sh\nAPPIMAGE_EXTRACT_AND_RUN=1 exec "%s" "$@"\n' "$image" > /usr/local/bin/tiktok-transcriber
        chmod +x /usr/local/bin/tiktok-transcriber ;;
esac
set +e
desktop_basics

tiktok-transcriber --version || { echo "the installed app does not start"; exit 1; }
crash="$HOME/.local/share/tiktok-transcriber/crash.log"

# start the window for 40 seconds with extra environment ("$@"); the result is
# 0 when it was still open at the end (timeout's 124) and left no crash log
start_window() {
    rm -f "$crash"
    env "$@" timeout 40 tiktok-transcriber
    code=$?
    if [ -f "$crash" ]; then cat "$crash"; return 1; fi
    [ "$code" = 124 ] || { echo "TikTok Transcriber exited early with code $code"; return 1; }
}

# when the window does not open: does the system's own OpenGL work on this
# screen, and which graphics libraries does the bundle carry
diagnose_gl() {
    echo "::group::OpenGL diagnosis"
    if command -v apt-get >/dev/null; then DEBIAN_FRONTEND=noninteractive apt-get install -y mesa-utils >/dev/null 2>&1
    elif command -v dnf >/dev/null; then dnf install -y glx-utils >/dev/null 2>&1
    elif command -v zypper >/dev/null; then zypper --non-interactive install Mesa-demo-x >/dev/null 2>&1
    elif command -v pacman >/dev/null; then pacman -S --noconfirm mesa-utils >/dev/null 2>&1; fi
    if command -v glxinfo >/dev/null; then
        DISPLAY=:99 glxinfo -B 2>&1 | head -20
    else
        echo "no glxinfo on this system"
    fi
    program=$(readlink -f "$(command -v tiktok-transcriber)")
    folder=$(dirname "$program")
    echo "bundle: $folder"
    find "$folder" -name '*.so*' | grep -i -E 'libgl|libegl|glapi|libdrm|libgbm|libxcb-glx|libx11|libstdc|libgcc|libexpat|libz\.so' | sort
    DISPLAY=:99 LIBGL_DEBUG=verbose timeout 15 tiktok-transcriber 2>&1 | grep -i -E 'libgl|dri|glx|egl|mesa' | head -30
    echo "::endgroup::"
}

if command -v Xvfb >/dev/null; then
    # 24-bit color like a real monitor: xvfb-run's default 8-bit screen has no
    # OpenGL configuration, and Qt stops on that
    Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
    server=$!
    sleep 3
    if start_window DISPLAY=:99; then
        result=0
    else
        result=1
        echo "::group::retry with QT_XCB_GL_INTEGRATION=xcb_egl"
        if start_window DISPLAY=:99 QT_XCB_GL_INTEGRATION=xcb_egl; then
            egl=passed
        else
            egl=failed
        fi
        echo "::endgroup::"
        echo "Default start failed; with QT_XCB_GL_INTEGRATION=xcb_egl it $egl."
        diagnose_gl
    fi
    kill "$server" 2>/dev/null
else
    echo "no Xvfb on this system: using Qt's offscreen platform"
    start_window QT_QPA_PLATFORM=offscreen
    result=$?
fi
[ "$result" = 0 ] || exit 1
echo "Installed ($kind) and stayed open for 40 seconds."
