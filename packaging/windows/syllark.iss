; Syllark per-user installer (Inno Setup 6). Built by dev\build.ps1 -Installer.
; It installs the same folder as the ZIP into %LOCALAPPDATA%\Programs\Syllark,
; adds Start menu (and optional desktop) shortcuts and an uninstaller.
; Settings, the model cache and transcripts are not touched on uninstall.

#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<folder with Syllark.exe>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
AppId={{6B0E3C8A-5D2F-4E61-9C0B-7A3F1E2D4B59}
AppName=Syllark
AppVersion={#AppVersion}
AppVerName=Syllark {#AppVersion}
AppPublisher=Nas
AppPublisherURL=https://github.com/nas2077/syllark
AppSupportURL=https://github.com/nas2077/syllark/issues
AppUpdatesURL=https://github.com/nas2077/syllark/releases
DefaultDirName={localappdata}\Programs\Syllark
DefaultGroupName=Syllark
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Syllark-{#AppVersion}-windows-x64-setup
SetupIconFile={#SourceDir}\runtime\icon.ico
UninstallDisplayIcon={app}\Syllark.exe
UninstallDisplayName=Syllark
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
Name: "{autoprograms}\Syllark"; Filename: "{app}\Syllark.exe"
Name: "{autodesktop}\Syllark"; Filename: "{app}\Syllark.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Syllark.exe"; Description: "{cm:LaunchProgram,Syllark}"; Flags: nowait postinstall skipifsilent
