; Local3D installer (Inno Setup 6.7+). Thin on purpose: it installs the launcher, the app pack and a Start Menu entry.
; The ComfyUI runtime (~2 GB) and the AI models (~22 GB) are downloaded by Local3D on first start, never bundled.
;
;   ISCC.exe installer\Local3D.iss            (after: powershell -File scripts\build_launcher.ps1)

#define AppName "Local3D"
#define AppVersion "0.1.0"
#define AppPublisher "Arash Sajjadi"
#define AppURL "https://github.com/arashsajjadi/Local3D"

[Setup]
AppId={{C9E98C1E-27CB-44D7-BC0B-0FE93646F3A3}
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
VersionInfoCopyright=MIT License

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
; The one entry people look for. The AppUserModelID keeps the pinned tile and the running window together.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Local3D.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"; AppUserModelID: "Local3D.App"; Comment: "Turn a photo or a text prompt into a 3D model, locally"
Name: "{autoprograms}\Local3D tools\Prompt to 3D"; Filename: "{app}\Local3D.exe"; Parameters: "--app prompt"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"; AppUserModelID: "Local3D.App"
Name: "{autoprograms}\Local3D tools\Reference pictures"; Filename: "{app}\Local3D.exe"; Parameters: "--app reference"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"; AppUserModelID: "Local3D.App"
Name: "{autoprograms}\Local3D tools\Download more models"; Filename: "{app}\Local3D.exe"; Parameters: "--models"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"
Name: "{autoprograms}\Local3D tools\Diagnostics"; Filename: "{app}\Local3D.exe"; Parameters: "--diagnostics"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\icon.ico"

[Run]
Filename: "{app}\Local3D.exe"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[Code]
// Uninstall: keep the big downloads unless the person says otherwise.
function DataDirFromSettings(): String;
var
  Text: AnsiString;
  P, Q: Integer;
  S: String;
begin
  Result := ExpandConstant('{localappdata}\Local3D');
  if LoadStringFromFile(ExpandConstant('{localappdata}\Local3D\settings.json'), Text) then
  begin
    S := String(Text);
    P := Pos('"dataDir":"', S);
    if P > 0 then
    begin
      S := Copy(S, P + 11, Length(S));
      Q := Pos('"', S);
      if Q > 1 then
      begin
        Result := Copy(S, 1, Q - 1);
        StringChangeEx(Result, '\\', '\', True);
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Dir := DataDirFromSettings();
    if DirExists(Dir) and (UninstallSilent = False) then
      if MsgBox('Also delete the downloaded ComfyUI runtime, logs and settings in' + #13#10 + Dir + '?' + #13#10#13#10 +
                'Model files and your generated models are NOT deleted. Choose No to keep everything and make a reinstall instant.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Dir, True, True, True);
  end;
end;
