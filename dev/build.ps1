param([switch]$Quiet, [switch]$NoZip, [switch]$SkipSetup, [switch]$Installer)
$ErrorActionPreference = 'Stop'
$DevelopmentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $DevelopmentRoot
$EnvironmentPython = Join-Path $DevelopmentRoot '.venv\Scripts\python.exe'
if (-not $SkipSetup) {
    & (Join-Path $DevelopmentRoot 'setup.ps1') -Quiet
    if ($LASTEXITCODE -ne 0) { throw 'Environment preparation failed.' }
}
if (-not (Test-Path -LiteralPath $EnvironmentPython)) { throw 'Run dev\setup.ps1 first.' }
& $EnvironmentPython (Join-Path $DevelopmentRoot 'collect_licenses.py')
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
& $EnvironmentPython -m PyInstaller --noconfirm --clean --log-level WARN --distpath (Join-Path $DevelopmentRoot 'build\dist') --workpath (Join-Path $DevelopmentRoot 'build\work') (Join-Path $DevelopmentRoot 'build.spec')
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
$Distribution = Join-Path $DevelopmentRoot 'build\dist\TikTok Transcriber'
if (-not (Test-Path -LiteralPath (Join-Path $Distribution 'TikTok Transcriber.exe'))) { throw 'Executable is missing.' }
$Version = (Select-String -Path (Join-Path $ProjectRoot 'src\tiktok_core.py') -Pattern '^APP_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $NoZip) {
    $ReleaseZip = Join-Path $DevelopmentRoot "dist\TikTok-Transcriber-$Version-windows-x64.zip"
    New-Item -ItemType Directory -Force -Path (Split-Path $ReleaseZip) | Out-Null
    & $EnvironmentPython (Join-Path $DevelopmentRoot 'package_release.py') $Distribution $ReleaseZip
    if ($LASTEXITCODE -ne 0) { throw 'Release ZIP verification failed.' }
}
if ($Installer) {
    # Inno Setup 6: a per-user installer, no administrator rights needed
    $Compiler = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $Compiler) { throw 'Inno Setup 6 is required for -Installer.' }
    & $Compiler /Qp "/DAppVersion=$Version" "/DSourceDir=$Distribution" "/DOutputDir=$(Join-Path $DevelopmentRoot 'dist')" (Join-Path $ProjectRoot 'packaging\windows\tiktok-transcriber.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
}
Write-Host "Built TikTok Transcriber in $Distribution"
