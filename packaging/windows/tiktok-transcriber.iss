; TikTok Transcriber per-user installer (Inno Setup 6). Built by dev\build.ps1 -Installer.
; It installs the same folder as the ZIP into %LOCALAPPDATA%\Programs\TikTok Transcriber,
; adds Start menu (and optional desktop) shortcuts and an uninstaller.
; Settings, the model cache and transcripts are not touched on uninstall.

#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<folder with TikTok Transcriber.exe>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
AppId={{6B0E3C8A-5D2F-4E61-9C0B-7A3F1E2D4B59}
AppName=TikTok Transcriber
AppVersion={#AppVersion}
AppVerName=TikTok Transcriber {#AppVersion}
AppPublisher=Nas
AppPublisherURL=https://github.com/nas2077/tiktok-transcriber
AppSupportURL=https://github.com/nas2077/tiktok-transcriber/issues
AppUpdatesURL=https://github.com/nas2077/tiktok-transcriber/releases
DefaultDirName={localappdata}\Programs\TikTok Transcriber
DefaultGroupName=TikTok Transcriber
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=TikTok-Transcriber-{#AppVersion}-windows-x64-setup
SetupIconFile={#SourceDir}\runtime\icon.ico
UninstallDisplayIcon={app}\TikTok Transcriber.exe
UninstallDisplayName=TikTok Transcriber
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
LicenseFile={#SourceDir}\runtime\licenses\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; a new version replaces the old runtime instead of mixing files from both
Type: filesandordirs; Name: "{app}\runtime"

[Icons]
; the same AppUserModelID the app gives its window: a shortcut pinned to the
; taskbar and the running window share one button instead of two
Name: "{autoprograms}\TikTok Transcriber"; Filename: "{app}\TikTok Transcriber.exe"; AppUserModelID: "tiktok-transcriber"
Name: "{autodesktop}\TikTok Transcriber"; Filename: "{app}\TikTok Transcriber.exe"; AppUserModelID: "tiktok-transcriber"; Tasks: desktopicon

[Run]
Filename: "{app}\TikTok Transcriber.exe"; Description: "{cm:LaunchProgram,TikTok Transcriber}"; Flags: nowait postinstall skipifsilent
