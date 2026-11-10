; Inno Setup script for the MPC Mapper Windows installer.
; Built in CI:  ISCC /DAppVersion=<version> /DSrcRoot=<repo> packaging\windows\installer.iss
; Installs per user (no admin rights needed) to %LOCALAPPDATA%\Programs\MPC Mapper.

#ifndef AppVersion
  #define AppVersion "dev"
#endif
#ifndef SrcRoot
  #define SrcRoot "..\.."
#endif

[Setup]
AppId={{6B1E3C1A-5D7E-4C2B-9A41-3F0D2E8B7C55}
AppName=MPC Mapper
AppVersion={#AppVersion}
AppVerName=MPC Mapper {#AppVersion}
AppPublisher=MPC Mapper
AppComments=Akai APC mini mk2 and Behringer X-Touch Compact for grandMA3
DefaultDirName={autopf}\MPC Mapper
DefaultGroupName=MPC Mapper
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#SrcRoot}
OutputBaseFilename=MPC-Mapper-Setup-Windows
SetupIconFile={#SrcRoot}\mpc_mapper\assets\icon.ico
UninstallDisplayIcon={app}\MPC Mapper.exe
UninstallDisplayName=MPC Mapper
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SrcRoot}\dist\MPC Mapper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcRoot}\pkg\grandMA3-Plugin\*"; DestDir: "{app}\grandMA3-Plugin"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcRoot}\packaging\Anleitung.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\mappings\demo.json"; DestDir: "{app}"; DestName: "Demo-Layout.json"; Flags: ignoreversion

[Icons]
Name: "{group}\MPC Mapper"; Filename: "{app}\MPC Mapper.exe"
Name: "{group}\Anleitung"; Filename: "{app}\Anleitung.html"
Name: "{group}\grandMA3-Plugin (Ordner)"; Filename: "{app}\grandMA3-Plugin"
Name: "{group}\MPC Mapper deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MPC Mapper"; Filename: "{app}\MPC Mapper.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MPC Mapper.exe"; Description: "{cm:LaunchProgram,MPC Mapper}"; Flags: nowait postinstall skipifsilent
