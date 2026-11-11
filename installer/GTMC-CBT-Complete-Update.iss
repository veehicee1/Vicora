#define MyAppName "VICORA CBT Complete Update"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Veehicee Telecommunications and Services"

[Setup]
AppId={{B9E2A10A-6D77-4D3C-A45A-3E5B91C0A126}
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
OutputBaseFilename=VICORA-CBT-Complete-Update-Windows
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
Source: "..\dist-electron\VICORA-CBT-Examination-1.0.0-Windows.exe"; DestDir: "{app}"; DestName: "CBTExamination.exe"; Flags: ignoreversion
Source: "..\dist\CBTRestore.exe"; DestDir: "{app}\Tools"; Flags: ignoreversion
Source: "..\dist\CBTAdmin-Diagnostic.exe"; DestDir: "{app}\Diagnostics"; Flags: ignoreversion
Source: "..\dist\CBTExamination-Diagnostic.exe"; DestDir: "{app}\Diagnostics"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GTMC CBT\VICORA CBT Admin"; Filename: "{app}\CBTAdmin.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\GTMC CBT\VICORA CBT Examination"; Filename: "{app}\CBTExamination.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\GTMC CBT\Restore CBT Backup"; Filename: "{app}\Tools\CBTRestore.exe"; WorkingDir: "{app}\Tools"
Name: "{autoprograms}\GTMC CBT\Diagnostics\Admin Diagnostic"; Filename: "{app}\Diagnostics\CBTAdmin-Diagnostic.exe"; WorkingDir: "{app}\Diagnostics"
Name: "{autoprograms}\GTMC CBT\Diagnostics\Examination Diagnostic"; Filename: "{app}\Diagnostics\CBTExamination-Diagnostic.exe"; WorkingDir: "{app}\Diagnostics"
Name: "{commondesktop}\VICORA CBT Admin"; Filename: "{app}\CBTAdmin.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\VICORA CBT Examination"; Filename: "{app}\CBTExamination.exe"; WorkingDir: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  InstallDir: String;
begin
  InstallDir := ExpandConstant('{autopf}\GTMC CBT');
  if not (FileExists(InstallDir + '\CBTAdmin.exe') or FileExists(InstallDir + '\CBTExamination.exe') or DirExists(ExpandConstant('{commonappdata}\CBTSystem'))) then
  begin
    MsgBox('No existing GTMC CBT installation or school data was found. Use the separate Admin and Examination Fresh Installation files for a new installation.', mbError, MB_OK);
    Result := False;
  end
  else
    Result := MsgBox('COMPLETE UPDATE' + #13#10 + #13#10 +
      'This installer updates BOTH Admin and Examination applications.' + #13#10 +
      'It will close GTMC CBT applications on this computer.' + #13#10 +
      'Continue only when no examination is in progress and all users have exited the CBT apps.' + #13#10 + #13#10 +
      'The school data folder will be backed up before application files are replaced.' + #13#10 +
      'Continue with the update?', mbConfirmation, MB_YESNO) = IDYES;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  DataDir, BackupRoot, BackupDir, CommandLine: String;
  ResultCode: Integer;
begin
  Result := '';
  NeedsRestart := False;
  DataDir := ExpandConstant('{commonappdata}\CBTSystem');
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTAdmin.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTExamination.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTAdmin-Diagnostic.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTExamination-Diagnostic.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if not DirExists(DataDir) then
  begin
    Log('No CBTSystem data folder exists; application update can continue without a data backup.');
    exit;
  end;

  BackupRoot := ExpandConstant('{commonappdata}\GTMC CBT Backups');
  BackupDir := BackupRoot + '\PreUpdate-' + GetDateTimeString('yyyymmdd-hhnnss', '', '');
  if not ForceDirectories(BackupDir) then
  begin
    Result := 'Could not create the pre-update backup folder. No application files have been replaced.';
    exit;
  end;

  CommandLine := '"' + DataDir + '" "' + BackupDir + '" /E /COPY:DAT /R:2 /W:1';
  if not Exec(ExpandConstant('{sys}\robocopy.exe'), CommandLine, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Could not start the data backup process. Update cancelled.';
    exit;
  end;
  if ResultCode > 7 then
  begin
    Result := 'The automatic data backup failed (robocopy exit code ' + IntToStr(ResultCode) + '). Update cancelled. Existing application files have not been replaced.';
    exit;
  end;
  Log('GTMC CBT pre-update data backup completed: ' + BackupDir);
end;

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""VICORA CBT School Host"" dir=in action=allow protocol=TCP localport=8000 profile=private"; Flags: runhidden; StatusMsg: "Allowing student devices to reach the school host on the private network..."

[UninstallDelete]
; Never delete the school database, backups, or user settings.
