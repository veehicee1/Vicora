#define MyAppName "VICORA CBT Admin"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Veehicee Telecommunications and Services"

[Setup]
AppId={{6D8C3C72-43B1-4A91-8D6C-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VICORA CBT
DefaultGroupName=VICORA CBT
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist-installer
OutputBaseFilename=VICORA-CBT-Admin-Fresh-Installation-Windows
Compression=none
SolidCompression=no
WizardStyle=modern
UninstallDisplayIcon={app}\CBTAdmin.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{commonappdata}\\CBTSystem"; Permissions: users-modify
Name: "{commonappdata}\\CBTSystem\\backups"; Permissions: users-modify
Name: "{app}\Diagnostics"
Name: "{app}\Tools"

[Files]
Source: "..\dist-admin-electron\VICORA-CBT-Admin-1.0.0-Windows.exe"; DestDir: "{app}"; DestName: "CBTAdmin.exe"; Flags: ignoreversion
Source: "..\dist\CBTAdmin-Diagnostic.exe"; DestDir: "{app}\Diagnostics"; Flags: ignoreversion
Source: "..\dist\CBTRestore.exe"; DestDir: "{app}\Tools"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\VICORA CBT\VICORA CBT Admin"; Filename: "{app}\CBTAdmin.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\VICORA CBT\Diagnostics\Admin Diagnostic"; Filename: "{app}\Diagnostics\CBTAdmin-Diagnostic.exe"; WorkingDir: "{app}\Diagnostics"
Name: "{autoprograms}\VICORA CBT\Restore CBT Backup"; Filename: "{app}\Tools\CBTRestore.exe"; WorkingDir: "{app}\Tools"
Name: "{commondesktop}\VICORA CBT Admin"; Filename: "{app}\CBTAdmin.exe"; WorkingDir: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  InstallDir: String;
begin
  InstallDir := ExpandConstant('{autopf}\VICORA CBT');
  if FileExists(InstallDir + '\CBTAdmin.exe') then
  begin
    MsgBox('VICORA CBT Admin is already installed. Use the Complete Update installer to update both applications safely.', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""VICORA CBT School Host"" dir=in action=allow protocol=TCP localport=8000 profile=private"; Flags: runhidden; StatusMsg: "Allowing student devices to reach the school host on the private network..."

[UninstallDelete]
; Do not delete shared school data, backups, or user settings.
