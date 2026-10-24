# TikTok Transcriber installer for Windows.
#
#   irm https://raw.githubusercontent.com/nas2077/tiktok-transcriber/main/install.ps1 | iex
#
# Downloads the per-user installer from the latest release, checks its SHA-256
# and runs it silently: no administrator rights. TikTok Transcriber then appears in the
# Start menu and in Settings > Apps, where it can be uninstalled.
# $env:TIKTOK_TRANSCRIBER_VERSION = '0.2.2' installs that version instead of the latest.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $Repository = 'https://github.com/nas2077/tiktok-transcriber'

    if (-not [Environment]::Is64BitOperatingSystem) { throw 'TikTok Transcriber needs 64-bit Windows 10 or 11.' }
    $Version = $env:TIKTOK_TRANSCRIBER_VERSION
    if (-not $Version) {
        $Release = Invoke-RestMethod -Uri 'https://api.github.com/repos/nas2077/tiktok-transcriber/releases/latest' -UseBasicParsing
        $Version = $Release.tag_name
    }
    $Version = $Version.TrimStart('v')
    $Name = "TikTok-Transcriber-$Version-windows-x64-setup.exe"
    $Folder = Join-Path ([IO.Path]::GetTempPath()) ("tiktok-transcriber-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $Folder | Out-Null
    try {
        Write-Host "Installing TikTok Transcriber $Version"
        $Base = "$Repository/releases/download/v$Version"
        Invoke-WebRequest -Uri "$Base/SHA256SUMS.txt" -OutFile (Join-Path $Folder 'SHA256SUMS.txt') -UseBasicParsing
        Invoke-WebRequest -Uri "$Base/$Name" -OutFile (Join-Path $Folder $Name) -UseBasicParsing
        $Line = Get-Content (Join-Path $Folder 'SHA256SUMS.txt') | Where-Object { $_ -match ("\s\*?" + [Regex]::Escape($Name) + '$') }
        if (-not $Line) { throw "$Name is not in the checksums." }
        $Expected = ($Line -split '\s+')[0]
        $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Folder $Name)).Hash
        if ($Actual -ne $Expected.ToUpperInvariant()) { throw "Checksum mismatch for ${Name}: the download is damaged." }
        $Setup = Start-Process -FilePath (Join-Path $Folder $Name) -Wait -PassThru `
            -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER'
        if ($Setup.ExitCode -ne 0) { throw "The installer stopped with code $($Setup.ExitCode)." }
        Write-Host ''
        Write-Host "TikTok Transcriber $Version is installed. Open it from the Start menu."
    } finally {
        Remove-Item -LiteralPath $Folder -Recurse -Force -ErrorAction SilentlyContinue
    }
}
