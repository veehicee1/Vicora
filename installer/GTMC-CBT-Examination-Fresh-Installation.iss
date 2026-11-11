#define MyAppName "VICORA CBT Examination"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Veehicee Telecommunications and Services"

[Setup]
AppId={{6D8C3C72-43B1-4A91-8D6C-000000000002}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GTMC CBT
DefaultGroupName=VICORA CBT
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist-installer
OutputBaseFilename=VICORA-CBT-Examination-Fresh-Installation-Windows
Compression=none
SolidCompression=no
WizardStyle=modern
UninstallDisplayIcon={app}\CBTExamination.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{app}\Diagnostics"

[Files]
Source: "..\dist-electron\VICORA-CBT-Examination-1.0.0-Windows.exe"; DestDir: "{app}"; DestName: "CBTExamination.exe"; Flags: ignoreversion
Source: "..\dist\CBTExamination-Diagnostic.exe"; DestDir: "{app}\Diagnostics"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GTMC CBT\VICORA CBT Examination"; Filename: "{app}\CBTExamination.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\GTMC CBT\Diagnostics\Examination Diagnostic"; Filename: "{app}\Diagnostics\CBTExamination-Diagnostic.exe"; WorkingDir: "{app}\Diagnostics"
Name: "{commondesktop}\VICORA CBT Examination"; Filename: "{app}\CBTExamination.exe"; WorkingDir: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  InstallDir: String;
begin
  InstallDir := ExpandConstant('{autopf}\GTMC CBT');
  if FileExists(InstallDir + '\CBTExamination.exe') then
  begin
    MsgBox('VICORA CBT Examination is already installed. Use the Complete Update installer to update both applications safely.', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;

[UninstallDelete]
; Do not delete shared school data, backups, or user settings.
