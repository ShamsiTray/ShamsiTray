#define MyAppName      "ShamsiTray"
#define MyAppVersion   "1.3"
#define MyAppPublisher "ShamsiTray"
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
OutputDir=D:\ShamsiTray-main\Installer
OutputBaseFilename=ShamsiTraySetup-{#MyAppVersion}
SetupIconFile=D:\ShamsiTray-main\assets\images\icons\icon.ico
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
Source: "D:\ShamsiTray-main\output\ShamsiTray\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\ShamsiTray-main\output\ShamsiTray\*";          DestDir: "{app}"; \
        Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";                       Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                 Filename: "{app}\{#MyAppExeName}"; \
      Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
      ValueName: "{#MyAppName}"; ValueType: string; \
      ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

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
    // Check if user wants to remove settings (registry data)
    if ShouldRemoveSettings() then
    begin
      // Remove the entire RaySoft registry key and all subkeys
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\ShamsiTray');
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