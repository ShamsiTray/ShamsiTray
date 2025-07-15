#define MyAppName      "ShamsiTray"
#define MyAppVersion   "1.1"
#define MyAppPublisher "RaySoft"
#define MyAppExeName   "ShamsiTray.exe"

[Setup]
; • basic metadata
AppId={{0A346829-B64E-488A-84B0-9D4D97BDBE84}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

; • install location and icons
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=D:\Output\Installer
OutputBaseFilename=ShamsiTraySetup-{#MyAppVersion}
SetupIconFile=D:\Output\ShamsiTray\res\icons\icon.ico
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=100
DisableWelcomePage=no

PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
      GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "D:\Output\ShamsiTray\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Output\ShamsiTray\*";          DestDir: "{app}"; \
        Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";                       Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                 Filename: "{app}\{#MyAppExeName}"; \
      Tasks: desktopicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\RaySoft"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
      ValueName: "{#MyAppName}"; ValueType: string; \
      ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

      
      
[InstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeUninstall(): Boolean;
var
  ErrorCode: Integer;
  AppRunning: Boolean;
begin
  Result := True;
  AppRunning := CheckForMutexes('{#MyAppName}Mutex');
  
  if not AppRunning then
    AppRunning := FindWindowByClassName('YourAppWindowClass') <> 0;
  
  if not AppRunning then
  begin
    if Exec('tasklist', '/FI "IMAGENAME eq {#MyAppExeName}" /FO CSV | find /I "{#MyAppExeName}"', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode) then
      AppRunning := (ErrorCode = 0);
  end;
  
  if AppRunning then
  begin
    if MsgBox('The application {#MyAppName} is currently running. ' +
              'Do you want to close it and continue with the uninstallation?', 
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      // Try to close gracefully first
      if not Exec('taskkill', '/IM "{#MyAppExeName}" /T', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode) then
      begin
        // Force close if graceful close fails
        Exec('taskkill', '/F /IM "{#MyAppExeName}" /T', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
      end;
      
      // Wait a moment for the process to close
      Sleep(2000);
    end
    else
    begin
      Result := False;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ErrorCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Additional cleanup - force kill any remaining processes
    Exec('taskkill', '/F /IM "{#MyAppExeName}" /T', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
    
    // Wait a bit and then try to remove any remaining files
    Sleep(1000);
    
    // Force delete the installation directory if it still exists
    if DirExists(ExpandConstant('{app}')) then
    begin
      DelTree(ExpandConstant('{app}'), True, True, True);
    end;
  end;
end;