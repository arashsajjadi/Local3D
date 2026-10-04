; Local3D installer (Inno Setup 6.7+). Thin on purpose: it installs the launcher, the app pack and a Start Menu entry.
; The ComfyUI runtime (~2 GB) and the AI models (15 to 36 GB depending on your GPU and choices) are downloaded by Local3D on first start, never bundled.
;
;   ISCC.exe installer\Local3D.iss            (after: powershell -File scripts\build_launcher.ps1)

#define AppName "Local3D"
#define AppVersion "0.1.1"
#define AppPublisher "Arash Sajjadi"
#define AppURL "https://github.com/arashsajjadi/Local3D"
#ifndef TEST_DATA_ANSWER
  #define TEST_DATA_ANSWER 0
#endif
#ifndef TEST_MODELS_ANSWER
  #define TEST_MODELS_ANSWER 0
#endif

[Setup]
#ifdef UNINSTALL_TEST
AppId={{0F1E2D3C-4B5A-4978-8695-A4B3C2D1E0F9}
#else
AppId={{C9E98C1E-27CB-44D7-BC0B-0FE93646F3A3}
#endif
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppMutex=Local3D.Launcher.v1
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=..\dist
OutputBaseFilename=Local3D-Setup-{#AppVersion}
SetupIconFile=..\assets\branding\icon.ico
UninstallDisplayIcon={app}\assets\branding\icon.ico
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
InfoBeforeFile=before-install.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} setup
VersionInfoCopyright=Copyright (c) 2026 Arash Sajjadi. MIT License.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\build\Local3D.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\local3d_pack\*"; DestDir: "{app}\local3d_pack"; Excludes: "__pycache__"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\data\models.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "..\data\runtime.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "..\data\frontend-settings.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "..\scripts\provision_models.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\assets\branding\icon.ico"; DestDir: "{app}\assets\branding"; Flags: ignoreversion
Source: "..\assets\examples\*"; DestDir: "{app}\assets\examples"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; The one entry people look for.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Local3D.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"; AppUserModelID: "Local3D.App"; Comment: "Turn a photo or a text prompt into a 3D model, locally"
Name: "{autoprograms}\Local3D tools\Prompt to 3D"; Filename: "{app}\Local3D.exe"; Parameters: "--app prompt"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"; AppUserModelID: "Local3D.App"
Name: "{autoprograms}\Local3D tools\Reference pictures"; Filename: "{app}\Local3D.exe"; Parameters: "--app reference"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"; AppUserModelID: "Local3D.App"
Name: "{autoprograms}\Local3D tools\Download more models"; Filename: "{app}\Local3D.exe"; Parameters: "--models"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"
Name: "{autoprograms}\Local3D tools\Diagnostics"; Filename: "{app}\Local3D.exe"; Parameters: "--diagnostics"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"

[Run]
Filename: "{app}\Local3D.exe"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[Code]
// Uninstall: never touch the generated models in Documents\Local3D, and keep the big model downloads unless the person says so.

// Reads one string value from settings.json. Accepts "D:\Models", "D:\Models" (a typo the launcher also tolerates) and "D:/Models".
function JsonSetting(const Text, Key: String): String;
var
  P, I: Integer;
begin
  Result := '';
  P := Pos('"' + Key + '"', Text);
  if P = 0 then Exit;
  I := P + Length(Key) + 2;
  while (I <= Length(Text)) and (Text[I] <> ':') do I := I + 1;
  I := I + 1;
  while (I <= Length(Text)) and (Text[I] <> '"') do I := I + 1;
  I := I + 1;
  while (I <= Length(Text)) and (Text[I] <> '"') do
  begin
    if (Text[I] = '\') and (I < Length(Text)) and (Text[I + 1] = '\') then I := I + 1;   // doubled backslash -> one
    Result := Result + Text[I];
    I := I + 1;
  end;
  StringChangeEx(Result, '/', '\', True);
end;

function SettingsText(): String;
var
  Raw: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(ExpandConstant('{localappdata}\Local3D\settings.json'), Raw) then Result := String(Raw);
end;

function DataDirectory(): String;
begin
  Result := JsonSetting(SettingsText(), 'dataDir');
  if Result = '' then Result := ExpandConstant('{localappdata}\Local3D');
end;

// Test hook (compiled only with /DUNINSTALL_TEST=1 /DTEST_DATA_ANSWER=0|1 /DTEST_MODELS_ANSWER=0|1): answers the two questions itself.
function Ask(const Msg: String; const TestAnswer: Boolean): Boolean;
begin
#ifdef UNINSTALL_TEST
  Result := TestAnswer;
#else
  Result := MsgBox(Msg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
#endif
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data, Models, DefaultModels, Msg: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
#ifndef UNINSTALL_TEST
  if UninstallSilent then Exit;
#endif
  Data := DataDirectory();
  if not DirExists(Data) then Exit;
  Models := JsonSetting(SettingsText(), 'modelsDir');
  DefaultModels := AddBackslash(Data) + 'models';
  if Models = '' then Models := DefaultModels;

  Msg := 'Also delete the ComfyUI runtime, logs and settings that Local3D stored in' + #13#10 + Data + ' ?' + #13#10#13#10 +
         'Your AI model files and the 3D models you generated (Documents\Local3D) are NOT deleted by this step. ' +
         'Choose No to keep everything; reinstalling is then quick.';
  if not Ask(Msg, ({#TEST_DATA_ANSWER} = 1)) then Exit;

  DelTree(AddBackslash(Data) + 'runtime', True, True, True);
  DelTree(AddBackslash(Data) + 'workspace', True, True, True);
  DelTree(AddBackslash(Data) + 'logs', True, True, True);
  DelTree(AddBackslash(Data) + 'browser-profile', True, True, True);
  DeleteFile(AddBackslash(Data) + 'session.json');
  DeleteFile(AddBackslash(Data) + 'vram-warned');
  DeleteFile(AddBackslash(Data) + 'prompt-pack-declined');
  DeleteFile(ExpandConstant('{localappdata}\Local3D\settings.json'));

  // The models are large and may be shared with other programs: ask separately, and only offer to delete the folder
  // Local3D itself created (inside its data folder), never a folder the person pointed it at.
  if SameText(RemoveBackslash(Models), RemoveBackslash(DefaultModels)) and DirExists(Models) then
    if Ask('Also delete the downloaded AI model files (15 GB or more) in' + #13#10 + Models + ' ?' + #13#10#13#10 +
           'Choose No to keep them; Local3D will not have to download them again if you reinstall.', ({#TEST_MODELS_ANSWER} = 1)) then
      DelTree(Models, True, True, True);

  RemoveDir(Data);                                // only succeeds when empty
  RemoveDir(ExpandConstant('{localappdata}\Local3D'));
end;
