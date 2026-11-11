#define MyAppName "GTMC CBT Desktop Suite"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Greater Tomorrow Model College"

[Setup]
AppId={{B9E2A10A-6D77-4D3C-A45A-3E5B91C0A126}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GTMC CBT
DefaultGroupName=GTMC CBT
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist-installer
OutputBaseFilename=GTMC-CBT-Fresh-Installation-Windows
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\CBTAdmin.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcuts for Admin and Examination"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Dirs]
Name: "{app}\Diagnostics"
Name: "{app}\Tools"

[Files]
Source: "..\\dist\CBTAdmin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\\dist\CBTExamination.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\\dist\CBTRestore.exe"; DestDir: "{app}\Tools"; Flags: ignoreversion
Source: "..\\dist\CBTAdmin-Diagnostic.exe"; DestDir: "{app}\Diagnostics"; Flags: ignoreversion
Source: "..\\dist\CBTExamination-Diagnostic.exe"; DestDir: "{app}\Diagnostics"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GTMC CBT\GTMC CBT Admin"; Filename: "{app}\CBTAdmin.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\GTMC CBT\GTMC CBT Examination"; Filename: "{app}\CBTExamination.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\GTMC CBT\Restore CBT Backup"; Filename: "{app}\Tools\CBTRestore.exe"; WorkingDir: "{app}\Tools"
Name: "{autoprograms}\GTMC CBT\Diagnostics\Admin Diagnostic"; Filename: "{app}\Diagnostics\CBTAdmin-Diagnostic.exe"; WorkingDir: "{app}\Diagnostics"
Name: "{autoprograms}\GTMC CBT\Diagnostics\Examination Diagnostic"; Filename: "{app}\Diagnostics\CBTExamination-Diagnostic.exe"; WorkingDir: "{app}\Diagnostics"
Name: "{commondesktop}\GTMC CBT Admin"; Filename: "{app}\CBTAdmin.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{commondesktop}\GTMC CBT Examination"; Filename: "{app}\CBTExamination.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Code]
function InitializeSetup(): Boolean;
var
  DataDir, InstallDir: String;
begin
  DataDir := ExpandConstant('{commonappdata}\CBTSystem');
  InstallDir := ExpandConstant('{autopf}\GTMC CBT');
  if DirExists(DataDir) or FileExists(InstallDir + '\CBTAdmin.exe') or FileExists(InstallDir + '\CBTExamination.exe') then
  begin
    MsgBox('An existing GTMC CBT installation or data folder was found.' + #13#10 + #13#10 +
      'For an existing school system, use the separate UPDATE INSTALLATION file. This fresh installer will not overwrite existing data.',
      mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;

[UninstallDelete]
; Never delete the school database, backups, or user settings.
