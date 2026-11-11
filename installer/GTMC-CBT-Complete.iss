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
OutputBaseFilename=GTMC-CBT-Update-Installation-Windows
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
  InstallDir: String;
begin
  InstallDir := ExpandConstant('{autopf}\GTMC CBT');
  if not (FileExists(InstallDir + '\CBTAdmin.exe') or FileExists(InstallDir + '\CBTExamination.exe') or DirExists(ExpandConstant('{commonappdata}\CBTSystem'))) then
  begin
    MsgBox('No existing GTMC CBT desktop installation was found in the standard installation folder.' + #13#10 + #13#10 +
      'Use GTMC-CBT-Fresh-Installation-Windows.exe for a new installation.',
      mbError, MB_OK);
    Result := False;
  end
  else
  begin
    Result := MsgBox('UPDATE INSTALLATION' + #13#10 + #13#10 +
      'This update will close GTMC CBT desktop applications on this computer.' + #13#10 +
      'Only continue when no examination is in progress and all users have exited the CBT apps.' + #13#10 + #13#10 +
      'The existing school data folder will be backed up before application files are replaced.' + #13#10 +
      'Continue with the update?',
      mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  DataDir, BackupRoot, BackupDir, CommandLine: String;
  ResultCode: Integer;
begin
  Result := '';
  NeedsRestart := False;
  DataDir := ExpandConstant('{commonappdata}\CBTSystem');
  if not DirExists(DataDir) then
    exit;

  { Close all CBT desktop processes before copying the SQLite database and WAL files. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTAdmin.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTExamination.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTAdmin-Diagnostic.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTExamination-Diagnostic.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM CBTServer.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

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
  { Robocopy exit codes 0 through 7 indicate success or success with differences. }
  if ResultCode > 7 then
  begin
    Result := 'The automatic data backup failed (robocopy exit code ' + IntToStr(ResultCode) + '). Update cancelled. Your existing installation has not been replaced.';
    exit;
  end;
  Log('GTMC CBT pre-update data backup completed: ' + BackupDir);
end;

[UninstallDelete]
; Never delete the school database, backups, or user settings.
