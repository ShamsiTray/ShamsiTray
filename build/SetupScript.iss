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
VersionInfoCopyright=Copyright (C) 2026 ShamsiTray
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} - Persian calendar for the system tray
VersionInfoProductName={#MyAppName}
UninstallDisplayName={#MyAppName}
AppCopyright=Copyright (C) 2026 ShamsiTray
AppPublisherURL=https://github.com/ShamsiTray/ShamsiTray
AppSupportURL=https://github.com/ShamsiTray/ShamsiTray/issues
AppUpdatesURL=https://github.com/ShamsiTray/ShamsiTray/releases/latest
; • install location and icons
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; PySide6 6.x and Python 3.12 need Windows 10 1809 or newer; without this the
; installer happily offers itself on releases that cannot run the payload. A
; bare "10.0" accepts pre-1809 builds of Windows 10, so pin the 1809 build.
MinVersion=10.0.17763
; Paths are relative to this script (build/): PyInstaller output and the repo tree.
OutputDir=..\output
OutputBaseFilename=ShamsiTraySetup-{#MyAppVersion}
SetupIconFile=..\assets\images\icons\icon.ico
SolidCompression=yes
Compression=lzma2/ultra64
WizardStyle=dynamic
WizardSizePercent=100
WizardImageFile=..\assets\images\wizard\WizardImage.png
WizardImageFileDynamicDark=..\assets\images\wizard\WizardImage.png
WizardImageBackColor=#fb2a4e
WizardImageBackColorDynamicDark=#D52D4A
WizardSmallImageFile=..\assets\images\wizard\WizardSmallImage.png
WizardSmallImageFileDynamicDark=..\assets\images\wizard\WizardSmallImage.png

DisableWelcomePage=no
; The start-menu group is fixed in [Icons], so this page could only ever be
; answered "create" - one more click for a tray app.
DisableProgramGroupPage=yes
; Upgrading over a running tray instance is the one path the process check in
; InitializeUninstall cannot see, because that runs on uninstall only.
; Restart Manager finds ShamsiTray.exe on its own; RestartApplications=no stops
; it relaunching the app behind the tray after the upgrade. No AppMutex: the
; app's single-instance guard is a QLockFile (src/main.py), so a named mutex
; would never match it.
CloseApplications=yes
RestartApplications=no
; The stock install-scope dialog is the one ask a standard (non-admin) account
; can pass through. It implies the /ALLUSERS-/CURRENTUSER switches, so silent
; runs keep picking a scope explicitly, and an existing install is detected
; rather than re-asked (UsePreviousPrivileges).
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
      GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller one-folder output (contents_directory "." puts the payload beside the exe).
Source: "..\output\ShamsiTray\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\output\ShamsiTray\*";               DestDir: "{app}"; \
        Flags: ignoreversion recursesubdirs createallsubdirs

; Seed the holiday store in %LOCALAPPDATA%\ShamsiTray (the app's USER_DATA_DIR).
; onlyifdoesntexist: reinstalls/upgrades must never clobber an updated holiday file;
; uninsneveruninstall: user data survives uninstall (the uninstaller's
; "Remove user settings and data" checkbox removes it explicitly).
Source: "..\assets\data\holidays.json"; DestDir: "{localappdata}\ShamsiTray"; \
        Flags: onlyifdoesntexist uninsneveruninstall

Source: "..\assets\images\wizard\WizardUninstallImage.png"; DestDir: "{app}\assets\images\wizard"; Flags: ignoreversion

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

; There is deliberately no [InstallDelete] on {app}: Name: {app} there resolves to
; whatever directory the user browsed to on the destination page, so it deletes
; that folder's entire contents - a profile or tools directory would be wiped
; before the install even starts. It was also redundant: Flags: ignoreversion
; already replaces stale payload files, and the uninstaller removes the
; directories it installed if they are left empty.

[Code]
var
  UninstallPage: TNewNotebookPage;
  UninstallUninstallButton: TNewButton;
  RemoveSettingsCheckbox: TNewCheckBox;
  KillSucceeded: Boolean;

const
  GWL_EXSTYLE = -20;
  WS_EX_COMPOSITED = $02000000;
  WM_CHANGEUISTATE = $0127;
  UIS_SET = 1;
  UISF_HIDEFOCUS = 1;
  VK_SPACE = $20;
  // AppProcessProbe's answer base: a find reads as this value plus the
  // count, so no incidental exit code of powershell.exe itself (1 on a
  // script error) can ever land in the found range and lie "running".
  APPPROC_BASE = 100;

function GetWindowLongW(Wnd: Longint; Index: Integer): Longint;
  external 'GetWindowLongW@user32.dll stdcall';
function SetWindowLongW(Wnd: Longint; Index: Integer; NewLong: Longint): Longint;
  external 'SetWindowLongW@user32.dll stdcall';
function SendMessageW(Wnd: Longint; Msg: Integer; WParam: Longint;
  LParam: Longint): Longint;
  external 'SendMessageW@user32.dll stdcall';
function GetKeyState(VKey: Integer): Integer;
  external 'GetKeyState@user32.dll stdcall';

procedure RemoveSettingsClick(Sender: TObject);
begin
  // The style hook's dotted focus ring ignores the UI state entirely
  // (film: the ring holds while the checkbox stays focused, after either
  // click), so a mouse click can only lose the ring by losing focus: hand
  // it back to the Uninstall button, whose accent ring is the open look.
  // Skip for Space: keyboard users keep the ring until the next click.
  if (GetKeyState(VK_SPACE) and $8000) <> 0 then
    Exit;
  UninstallProgressForm.ActiveControl := UninstallUninstallButton;
  SendMessageW(UninstallProgressForm.Handle, WM_CHANGEUISTATE,
    UIS_SET or (UISF_HIDEFOCUS shl 16), 0);
end;

// The app creates no named mutex or window class we can rely on, so detect a
// running instance via process enumeration. tasklist cannot do it honestly
// from here: IMAGENAME matches any user's ShamsiTray.exe, so a per-user
// uninstaller would see - and then fail to kill - another session's tray,
// and the piped find only ever reported find's own exit code, so a failed
// probe was indistinguishable from an empty one. The probe instead runs
// PowerShell and answers in its exit code (stdout of a decoupled console
// tool would arrive with another encoding puzzle on non-ASCII install
// paths, and Inno has no pipe to read through anyway):
//   0                nothing of THIS {app} copy runs
//   >= APPPROC_BASE  that many of its instances run
//   anything else    the probe itself failed - there is no verdict here
// The install path rides INSIDE the -Command text, as one single-quoted
// literal the filter compares each process .Path against (case-insensitive,
// like Windows paths): PowerShell re-joins every native argument after
// -Command with a space and keeps none of the OS-level quoting, so a quoted
// path argument would arrive split at its first space and silently compare
// against the wrong half. A process whose .Path is unreadable (another
// session's tray) cannot match this install's directory either, so it is
// reported absent - which is also the one this uninstaller could never have
// closed.
function AppProcessProbe(KillToo: Boolean): Integer;
var
  Literal: String;
  KillRule: String;
  Spawned: Boolean;
  ResultCode: Integer;
begin
  // PS string escaping needs no backslash work, only doubled apostrophes;
  // a target with an apostrophe is a legal install directory, so the path
  // is regenerated runtime from {app} rather than assuming one spelling.
  // StringChangeEx edits its var parameter in place, so the path is
  // escaped first and quoted after - and SupportDBCS=True is the docs'
  // requirement for path strings, so double-byte filenames survive.
  Literal := ExpandConstant('{app}\{#MyAppExeName}');
  StringChangeEx(Literal, '''', '''''', True);
  Literal := '''' + Literal + '''';
  if KillToo then
    KillRule := '; foreach ($x in $a) { try { $x.Kill() } catch { } }'
  else
    KillRule := '';
  Spawned := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "& { $a = @(Get-Process -Name ' +
    '''{#MyAppName}'' -ErrorAction SilentlyContinue | Where-Object { ' +
    '$_.Path -eq ' + Literal + ' })' + KillRule +
    '; if ($a.Count -eq 0) { exit 0 }; exit ' + IntToStr(APPPROC_BASE) +
    ' + $a.Count }"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := -1;
  if not Spawned then Exit;
  if ResultCode = 0 then
    Result := 0
  else if ResultCode >= APPPROC_BASE then
    Result := ResultCode - APPPROC_BASE;
end;

// A kill needs verification: poll until the probe counts zero instead of
// sleeping out a fixed window along the way. Each probe already blocks for
// the ~half second PowerShell needs, so 300 ms between polls is as tight as
// this check can get, and the caller moves the moment the tray is verifiably
// dead. The final Sleep ends with one closing probe, so an app killed during
// that window still reports success. An inconclusive probe is not absence:
// there is nothing verifiable to report, so the poll keeps saying open.
function PollUntilClosed(): Boolean;
var
  Poll: Integer;
begin
  Result := False;
  for Poll := 1 to 3 do
  begin
    if AppProcessProbe(False) = 0 then
    begin
      Result := True;
      Exit;
    end;
    Sleep(300);
  end;
  Result := (AppProcessProbe(False) = 0);
end;

// There is no graceful close to attempt: WM_CLOSE, what a gentle kill
// posts, is absorbed by this app by design (setQuitOnLastWindowClosed(False)
// in src/main.py - dismissing every window leaves the tray process running),
// so the close is TerminateProcess ($x.Kill()) and the probe afterwards -
// not the kill itself - is the proof it worked. The Uninstall button runs
// this synchronously on every click, so the dance only starts behind a live
// tray: an idle tray costs one probe and returns immediately, and a probe
// that cannot be read may not bless the close either - its answer is a
// failed round, which costs the caller's retry and nothing on disk.
function TryCloseApp(): Boolean;
var
  Seen: Integer;
begin
  Seen := AppProcessProbe(True);
  if Seen = 0 then
  begin
    Result := True;
    Exit;
  end;
  if Seen < 0 then
  begin
    Result := False;
    Exit;
  end;
  Result := PollUntilClosed();
end;

function InitializeUninstall(): Boolean;
var
  Seen: Integer;
begin
  Result := True;
  // The interactive flow closes the app from the Uninstall button (below),
  // so a user who cancels on that page never loses the running tray. Silent
  // mode shows no page and closes the app here instead, because no prompt is
  // possible there (/VERYSILENT would block forever, and Inno does not
  // suppress a plain MsgBox for /SUPPRESSMSGBOXES either); on a probe that
  // cannot be read at all - or a process that survives the kill - it logs
  // and continues, removing what the file lock allows.
  if not UninstallSilent then
    Exit;
  Seen := AppProcessProbe(False);
  if Seen < 0 then
  begin
    Log('{#MyAppName} process probe failed; continuing the silent uninstall.');
    Exit;
  end;
  if Seen = 0 then
    Exit;
  if not TryCloseApp() then
    Log('{#MyAppName} could not be closed; continuing the silent uninstall.');
end;

// The Uninstall button is created with ModalResult mrNone, so the click can
// never end the page by itself: the kill runs first (TryCloseApp), and only a
// verified-closed app may end the wizard - on a stubborn process the page
// stays up for a retry, with the single error box as the verdict.
procedure UninstallClick(Sender: TObject);
begin
  if not TryCloseApp() then
  begin
    MsgBox('{#MyAppName} could not be closed. Close it from the tray, then press Uninstall to try again.',
           mbError, MB_OK);
    Exit;
  end;
  // End the modal from the script: Close on the modal progress form makes
  // ShowModal return mrCancel - a user Cancel ends the modal with the same
  // value, so the gate below reads KillSucceeded to tell the two apart. The
  // button itself carries mrNone, so nothing here depends on when the VCL
  // copies which control's ModalResult: the scripted Close is the only
  // ender of a successful run.
  KillSucceeded := True;
  UninstallProgressForm.Close;
end;

procedure UseLogoInUninstaller();
var
  Img: TBitmapImage;
  Png: String;
  NewSize: Integer;
begin
  Png := ExpandConstant('{app}\assets\images\wizard\WizardUninstallImage.png');
  if not FileExists(Png) then Exit;
  try
    Img := UninstallProgressForm.WizardSmallBitmapImage;
    Img.PngImage.LoadFromFile(Png);
    Img.Stretch := True;
    NewSize := ScaleX(45);
    Img.Left := Img.Left + Img.Width - NewSize + ScaleX(18);
    Img.Top := Img.Top - (NewSize - Img.Height) div 2 + ScaleY(4);
    Img.Width := NewSize;
    Img.Height := NewSize;
  except
  end;
end;

procedure InitializeUninstallProgressForm();
var
  PageText: TNewStaticText;
  PageNameLabel: string;
  PageDescriptionLabel: string;
  CancelButtonEnabled: Boolean;
  CancelButtonModalResult: Integer;
  ModalOutcome: Integer;
begin
  if not UninstallSilent then
  begin
    UseLogoInUninstaller();
    KillSucceeded := False;

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
    RemoveSettingsCheckbox.OnClick := @RemoveSettingsClick;
    
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
    // mrNone, not mrOK: this click must never close the page on its own - the
    // UninstallClick handler runs the kill first and decides below.
    UninstallUninstallButton.ModalResult := mrNone;
    UninstallUninstallButton.OnClick := @UninstallClick;
    UninstallUninstallButton.TabOrder := UninstallProgressForm.CancelButton.TabOrder;
    
    // Fix Cancel button tab order
    UninstallProgressForm.CancelButton.TabOrder := UninstallUninstallButton.TabOrder + 1;
    
    // The wizard's static/button/checkbox children keep their default
    // clWindow brush, so each one's first erase paints white in the
    // un-manifested process (film: two full-width white bars + a white Cancel
    // across the reveal frames). WS_EX_COMPOSITED makes Windows paint the
    // whole window tree in one buffer, so no child ever flashes its own erase;
    // ParentBackground is the engine's own lever for custom-page backgrounds,
    // layered on for whatever a dark system presents these controls against.
    PageText.ParentBackground := True;
    RemoveSettingsCheckbox.ParentBackground := True;
    UninstallProgressForm.PageNameLabel.ParentBackground := True;
    UninstallProgressForm.PageDescriptionLabel.ParentBackground := True;
    UninstallProgressForm.StatusLabel.ParentBackground := True;
    UninstallProgressForm.BeveledLabel.ParentBackground := True;
    UninstallUninstallButton.ParentBackground := True;
    UninstallProgressForm.CancelButton.ParentBackground := True;

    // Catch-all for the first frames: WS_EX_COMPOSITED makes Windows paint the
    // whole window tree into one buffer, so no child can briefly show its own
    // white erase. Set once, before the form is ever shown.
    SetWindowLongW(UninstallProgressForm.Handle, GWL_EXSTYLE,
      GetWindowLongW(UninstallProgressForm.Handle, GWL_EXSTYLE) or
      WS_EX_COMPOSITED);

    // Hide the dotted focus ring form-wide: BUTTON-classed controls draw the
    // ring while focused and re-assert it whenever focus arrives, so the
    // checkbox's own click handler (RemoveSettingsClick) re-sends this state.
    // UISF_HIDEFOCUS keeps the ring for keyboard navigation, as in system
    // dialogs; DefWindowProc carries the state to every child.
    SendMessageW(UninstallProgressForm.Handle, WM_CHANGEUISTATE,
      UIS_SET or (UISF_HIDEFOCUS shl 16), 0);

    // Park initial focus on the Uninstall button: left to VCL it lands on the
    // checkbox, whose BUTTON class re-asserts visible focus (the dotted ring).
    UninstallProgressForm.ActiveControl := UninstallUninstallButton;

    // Temporarily modify Cancel button behavior
    CancelButtonEnabled := UninstallProgressForm.CancelButton.Enabled;
    CancelButtonModalResult := UninstallProgressForm.CancelButton.ModalResult;
    UninstallProgressForm.CancelButton.Enabled := True;
    UninstallProgressForm.CancelButton.ModalResult := mrCancel;
    
    // Show the form. Uninstall, Cancel and the scripted Close all end the
    // modal here; only a flag-less mrCancel is a verdict to abort on.
    ModalOutcome := UninstallProgressForm.ShowModal;
    if (ModalOutcome = mrCancel) and (not KillSucceeded) then
      Abort;
    
    // Restore Cancel button
    UninstallProgressForm.CancelButton.Enabled := CancelButtonEnabled;
    UninstallProgressForm.CancelButton.ModalResult := CancelButtonModalResult;
    
    // Restore original page labels and page
    UninstallProgressForm.PageNameLabel.Caption := PageNameLabel;
    UninstallProgressForm.PageDescriptionLabel.Caption := PageDescriptionLabel;
    UninstallProgressForm.InnerNotebook.ActivePage := UninstallProgressForm.InstallingPage;
    // The engine re-Shows this hidden form for the progress phase; without
    // this the ask page's Uninstall button would stay next to Cancel above
    // the progress bar.
    UninstallUninstallButton.Visible := False;
  end;
end;

// Function to check if user wants to remove settings
function ShouldRemoveSettings(): Boolean;
begin
  // The checkbox only exists when not UninstallSilent, but this is reached from
  // CurUninstallStepChanged(usPostUninstall) in silent mode too - where
  // dereferencing it raises, skipping the DelTree below. That failure is SILENT:
  // the exit code stays 0, so unattended uninstalls report success while
  // leaving %LOCALAPPDATA%\ShamsiTray behind. Never trust the exit code to
  // reveal this class of error.
  Result := Assigned(RemoveSettingsCheckbox) and RemoveSettingsCheckbox.Checked;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
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

    // Clean up the installation directory without erasing anything the
    // uninstaller does not own: by this point Inno has already removed every
    // file it installed, so whatever is still in {app} was placed there by the
    // user (a custom destination can hold unrelated files) and a recursive
    // force-delete would destroy it. Drop the empty subdirectories Inno left
    // behind, then the directory itself only if that left it empty.
    if DirExists(ExpandConstant('{app}')) then
    begin
      DelTree(ExpandConstant('{app}\*'), False, False, True);
      RemoveDir(ExpandConstant('{app}'));
    end;
  end;

end;