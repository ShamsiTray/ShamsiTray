#define MyAppName      "ShamsiTray"
#define MyAppVersion   "1.4.0"
#define MyAppPublisher "ShamsiTray"
#define MyAppExeName   "ShamsiTray.exe"

[Setup]
; • basic metadata
AppId={{0A346829-B64E-488A-84B0-9D4D97BDBE84}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoCopyright="Copyright © 2026 - ShamsiTray"
; • install location and icons
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Paths are relative to this script (build/): PyInstaller output and the repo tree.
OutputDir=..\output
OutputBaseFilename=ShamsiTraySetup-{#MyAppVersion}
SetupIconFile=..\assets\images\icons\icon.ico
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
; PyInstaller one-folder output (contents_directory "." puts the payload beside the exe).
Source: "..\dist\ShamsiTray\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ShamsiTray\*";               DestDir: "{app}"; \
        Flags: ignoreversion recursesubdirs createallsubdirs

; Seed the holiday store in %LOCALAPPDATA%\ShamsiTray (the app's USER_DATA_DIR).
; onlyifdoesntexist: reinstalls/upgrades must never clobber an updated holiday file;
; uninsneveruninstall: user data survives uninstall (the uninstaller's
; "Remove user settings and data" checkbox removes it explicitly).
Source: "..\assets\data\holidays.json"; DestDir: "{localappdata}\ShamsiTray"; \
        Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}";                       Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                 Filename: "{app}\{#MyAppExeName}"; \
      Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Autostart is owned by the app itself (tray-menu toggle persisted in settings.json
; and validated/repaired at every startup), so the installer deliberately does NOT
; write the HKCU Run key: it would silently re-enable autostart on upgrades for
; users who had turned it off.

[InstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  UninstallPage: TNewNotebookPage;
  UninstallUninstallButton: TNewButton;
  RemoveSettingsCheckbox: TNewCheckBox;

function InitializeUninstall(): Boolean;
var
  ErrorCode: Integer;
  AppRunning: Boolean;
begin
  Result := True;
  // The app creates no named mutex or window class we can rely on, so detect a
  // running instance via tasklist. The pipe needs a shell, hence cmd.exe /C.
  AppRunning := False;
  if Exec('cmd.exe', '/C tasklist /FI "IMAGENAME eq {#MyAppExeName}" /FO CSV | find /I "{#MyAppExeName}"', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode) then
    AppRunning := (ErrorCode = 0);
  
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

procedure InitializeUninstallProgressForm();
var
  PageText: TNewStaticText;
  PageNameLabel: string;
  PageDescriptionLabel: string;
  CancelButtonEnabled: Boolean;
  CancelButtonModalResult: Integer;
begin
  if not UninstallSilent then
  begin
    // Save original labels
    PageNameLabel := UninstallProgressForm.PageNameLabel.Caption;
    PageDescriptionLabel := UninstallProgressForm.PageDescriptionLabel.Caption;
    
    UninstallPage := TNewNotebookPage.Create(UninstallProgressForm);
    UninstallPage.Notebook := UninstallProgressForm.InnerNotebook;
    UninstallPage.Parent := UninstallProgressForm.InnerNotebook;
    UninstallPage.Align := alClient;
    
    // Add static text
    PageText := TNewStaticText.Create(UninstallProgressForm);
    PageText.Parent := UninstallPage;
    PageText.Top := UninstallProgressForm.StatusLabel.Top;
    PageText.Left := UninstallProgressForm.StatusLabel.Left;
    PageText.Width := UninstallProgressForm.StatusLabel.Width;
    PageText.Height := UninstallProgressForm.StatusLabel.Height;
    PageText.AutoSize := False;
    PageText.ShowAccelChar := False;
    PageText.Caption := 'Press Uninstall to proceed with uninstallation.';
    
    // Create checkbox for removing all settings
    RemoveSettingsCheckbox := TNewCheckBox.Create(UninstallProgressForm);
    RemoveSettingsCheckbox.Parent := UninstallPage;
    RemoveSettingsCheckbox.Top := PageText.Top + PageText.Height + ScaleY(20);
    RemoveSettingsCheckbox.Left := PageText.Left;
    RemoveSettingsCheckbox.Width := PageText.Width;
    RemoveSettingsCheckbox.Height := ScaleY(17);
    RemoveSettingsCheckbox.Caption := 'Remove user settings and data';
    RemoveSettingsCheckbox.Checked := False; // Default to unchecked
    
    // Set the page active
    UninstallProgressForm.InnerNotebook.ActivePage := UninstallPage;
    
    // Set page labels
    UninstallProgressForm.PageNameLabel.Caption := 'Uninstall {#MyAppName}';
    UninstallProgressForm.PageDescriptionLabel.Caption :=
      'Choose whether to remove user settings and data along with the application.';
    
    // Create only one button: Uninstall
    UninstallUninstallButton := TNewButton.Create(UninstallProgressForm);
    UninstallUninstallButton.Parent := UninstallProgressForm;
    UninstallUninstallButton.Left :=
      UninstallProgressForm.CancelButton.Left -
      UninstallProgressForm.CancelButton.Width -
      ScaleX(10);
    UninstallUninstallButton.Top := UninstallProgressForm.CancelButton.Top;
    UninstallUninstallButton.Width := UninstallProgressForm.CancelButton.Width;
    UninstallUninstallButton.Height := UninstallProgressForm.CancelButton.Height;
    UninstallUninstallButton.Caption := 'Uninstall';
    UninstallUninstallButton.ModalResult := mrOK;  // Ends the wizard
    UninstallUninstallButton.TabOrder := UninstallProgressForm.CancelButton.TabOrder;
    
    // Fix Cancel button tab order
    UninstallProgressForm.CancelButton.TabOrder := UninstallUninstallButton.TabOrder + 1;
    
    // Temporarily modify Cancel button behavior
    CancelButtonEnabled := UninstallProgressForm.CancelButton.Enabled;
    CancelButtonModalResult := UninstallProgressForm.CancelButton.ModalResult;
    UninstallProgressForm.CancelButton.Enabled := True;
    UninstallProgressForm.CancelButton.ModalResult := mrCancel;
    
    // Show the form (Uninstall or Cancel)
    if UninstallProgressForm.ShowModal = mrCancel then Abort;
    
    // Restore Cancel button
    UninstallProgressForm.CancelButton.Enabled := CancelButtonEnabled;
    UninstallProgressForm.CancelButton.ModalResult := CancelButtonModalResult;
    
    // Restore original page labels and page
    UninstallProgressForm.PageNameLabel.Caption := PageNameLabel;
    UninstallProgressForm.PageDescriptionLabel.Caption := PageDescriptionLabel;
    UninstallProgressForm.InnerNotebook.ActivePage := UninstallProgressForm.InstallingPage;
  end;
end;

// Function to check if user wants to remove settings
function ShouldRemoveSettings(): Boolean;
begin
  Result := RemoveSettingsCheckbox.Checked;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ErrorCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // The exe is gone, so a leftover autostart entry (created by the app's own
    // tray toggle) must never survive the uninstall.
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');

    // Check if user wants to remove settings and data
    if ShouldRemoveSettings() then
    begin
      // Legacy registry location (pre-1.4 QSettings data)
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\ShamsiTray');
      // Current user data: JSON settings, events, holiday store, logs
      DelTree(ExpandConstant('{localappdata}\ShamsiTray'), True, True, True);
    end;
    
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