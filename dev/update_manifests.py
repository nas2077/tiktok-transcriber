"""Write the package-manager manifests for a release from its SHA256SUMS.txt.

    python dev/update_manifests.py 0.2.0 SHA256SUMS.txt

Writes, all pointing at https://github.com/nas2077/syllark/releases/tag/v<version>:

- Casks/syllark.rb              Homebrew cask (this repository is its own tap)
- bucket/syllark.json           Scoop manifest (this repository is its own bucket)
- packaging/winget/<version>/   winget manifests, to submit to microsoft/winget-pkgs
- packaging/aur/PKGBUILD and .SRCINFO, to push to the AUR as syllark-bin

The release workflow runs it after building; commit the result together with
the release (docs/RELEASING.md).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/nas2077/syllark"
SUMMARY = "Readable transcripts from public TikTok clips and profiles, recognized locally"
DESCRIPTION = ("Syllark turns public TikTok videos and profiles into readable transcripts. "
               "Recognition runs locally with integrated Qwen and Whisper models.")


def checksums(path):
    sums = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", line.strip())
        if match:
            sums[match[2]] = match[1]
    return sums


def need(sums, name):
    if name not in sums:
        raise SystemExit(f"{name} is missing from the checksums")
    return sums[name]


def write(path, text):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    print("wrote", path.relative_to(ROOT).as_posix())


def homebrew(ver, sums):
    arm = need(sums, f"Syllark-{ver}-macos-arm64.dmg")
    intel = need(sums, f"Syllark-{ver}-macos-x64.dmg")
    write("Casks/syllark.rb", f'''# brew tap nas2077/syllark {REPO}
# brew install --cask syllark
cask "syllark" do
  arch arm: "arm64", intel: "x64"

  version "{ver}"
  sha256 arm:   "{arm}",
         intel: "{intel}"

  url "{REPO}/releases/download/v#{{version}}/Syllark-#{{version}}-macos-#{{arch}}.dmg"
  name "Syllark"
  desc "{SUMMARY}"
  homepage "{REPO}"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: ">= :big_sur"

  app "Syllark.app"

  zap trash: "~/Library/Application Support/Syllark"

  caveats <<~EOS
    Syllark is not signed with an Apple Developer ID. If macOS refuses to open
    it the first time, open System Settings > Privacy & Security and choose
    "Open Anyway" for Syllark.
  EOS
end
''')


def scoop(ver, sums):
    zip_hash = need(sums, f"Syllark-{ver}-windows-x64.zip")
    manifest = {
        "version": ver,
        "description": SUMMARY,
        "homepage": REPO,
        "license": "MIT",
        "notes": "Models download on first use into %LOCALAPPDATA%\\TikTok Transcriber.",
        "architecture": {"64bit": {
            "url": f"{REPO}/releases/download/v{ver}/Syllark-{ver}-windows-x64.zip",
            "hash": zip_hash,
        }},
        "extract_dir": "Syllark",
        "shortcuts": [["Syllark.exe", "Syllark"]],
        "checkver": {"github": REPO},
        "autoupdate": {
            "architecture": {"64bit": {
                "url": f"{REPO}/releases/download/v$version/Syllark-$version-windows-x64.zip",
            }},
            "hash": {"url": "$baseurl/SHA256SUMS.txt"},
        },
    }
    write("bucket/syllark.json", json.dumps(manifest, indent=4) + "\n")


def winget(ver, sums):
    setup = f"Syllark-{ver}-windows-x64-setup.exe"
    digest = need(sums, setup).upper()
    base = f"packaging/winget/{ver}/nas2077.Syllark"
    header = "# Created with dev/update_manifests.py\n"
    write(f"{base}.yaml", header + f"""PackageIdentifier: nas2077.Syllark
PackageVersion: {ver}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
""")
    write(f"{base}.installer.yaml", header + f"""PackageIdentifier: nas2077.Syllark
PackageVersion: {ver}
InstallerType: inno
Scope: user
InstallModes:
  - interactive
  - silent
  - silentWithProgress
UpgradeBehavior: install
MinimumOSVersion: 10.0.17763.0
Installers:
  - Architecture: x64
    InstallerUrl: {REPO}/releases/download/v{ver}/{setup}
    InstallerSha256: {digest}
ManifestType: installer
ManifestVersion: 1.6.0
""")
    write(f"{base}.locale.en-US.yaml", header + f"""PackageIdentifier: nas2077.Syllark
PackageVersion: {ver}
PackageLocale: en-US
Publisher: Nas
PublisherUrl: https://github.com/nas2077
PackageName: Syllark
PackageUrl: {REPO}
License: MIT
LicenseUrl: {REPO}/blob/v{ver}/LICENSE
ShortDescription: {SUMMARY}
Description: {DESCRIPTION}
Tags:
  - transcription
  - speech-recognition
  - whisper
  - tiktok
ReleaseNotesUrl: {REPO}/releases/tag/v{ver}
ManifestType: defaultLocale
ManifestVersion: 1.6.0
""")


def aur(ver, sums):
    x64 = need(sums, f"Syllark-{ver}-linux-x86_64.tar.gz")
    arm = need(sums, f"Syllark-{ver}-linux-aarch64.tar.gz")
    depends = ["nss", "alsa-lib", "libglvnd", "libxkbcommon", "fontconfig", "dbus"]
    write("packaging/aur/PKGBUILD", f"""# Maintainer: Nas <https://github.com/nas2077>
pkgname=syllark-bin
pkgver={ver}
pkgrel=1
pkgdesc="{SUMMARY}"
arch=('x86_64' 'aarch64')
url="{REPO}"
license=('MIT')
depends=({' '.join(f"'{d}'" for d in depends)})
provides=('syllark')
conflicts=('syllark')
options=('!strip' '!debug')
source_x86_64=("$pkgname-$pkgver-x86_64.tar.gz::$url/releases/download/v$pkgver/Syllark-$pkgver-linux-x86_64.tar.gz")
source_aarch64=("$pkgname-$pkgver-aarch64.tar.gz::$url/releases/download/v$pkgver/Syllark-$pkgver-linux-aarch64.tar.gz")
sha256sums_x86_64=('{x64}')
sha256sums_aarch64=('{arm}')

package() {{
  local id=io.github.nas2077.Syllark
  install -d "$pkgdir/opt/syllark" "$pkgdir/usr/bin"
  cp -a Syllark/. "$pkgdir/opt/syllark/"
  rm "$pkgdir/opt/syllark/$id.desktop" "$pkgdir/opt/syllark/$id.metainfo.xml" "$pkgdir/opt/syllark/$id.png"
  ln -s /opt/syllark/Syllark "$pkgdir/usr/bin/syllark"
  install -Dm644 "Syllark/$id.desktop" "$pkgdir/usr/share/applications/$id.desktop"
  install -Dm644 "Syllark/$id.metainfo.xml" "$pkgdir/usr/share/metainfo/$id.metainfo.xml"
  install -Dm644 "Syllark/$id.png" "$pkgdir/usr/share/icons/hicolor/512x512/apps/$id.png"
  install -Dm644 Syllark/_internal/licenses/LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}}
""")
    lines = ["pkgbase = syllark-bin", f"\tpkgdesc = {SUMMARY}", f"\tpkgver = {ver}", "\tpkgrel = 1",
             f"\turl = {REPO}", "\tarch = x86_64", "\tarch = aarch64", "\tlicense = MIT"]
    lines += [f"\tdepends = {d}" for d in depends]
    lines += ["\tprovides = syllark", "\tconflicts = syllark", "\toptions = !strip", "\toptions = !debug"]
    for arch, digest in (("x86_64", x64), ("aarch64", arm)):
        lines += [f"\tsource_{arch} = syllark-bin-{ver}-{arch}.tar.gz::{REPO}/releases/download/v{ver}/Syllark-{ver}-linux-{arch}.tar.gz",
                  f"\tsha256sums_{arch} = {digest}"]
    lines += ["", "pkgname = syllark-bin", ""]
    write("packaging/aur/.SRCINFO", "\n".join(lines))


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    ver, sums = sys.argv[1], checksums(sys.argv[2])
    homebrew(ver, sums)
    scoop(ver, sums)
    winget(ver, sums)
    aur(ver, sums)


if __name__ == "__main__":
    main()
