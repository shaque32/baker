; Mabillon installer for Windows (Inno Setup 6). Built in CI by .github/workflows/windows-installer.yml
; from the folder packaging/windows/stage.py writes. See docs/install.md.
;
; Per-user install, no administrator rights: %LOCALAPPDATA%\Programs\Mabillon. An update over an
; install made when the product was called Baker (same AppId) stays in %LOCALAPPDATA%\Programs\Baker.
; Picks the model runtime at install time: the CUDA build when the PC has an NVIDIA driver
; (nvidia-smi.exe in System32), else the CPU build. /RUNTIME=cpu or /RUNTIME=cuda overrides.
;
; The model file (about 9 GB) is not inside the installer. Setup looks for it, in this order:
;   1. already installed at %LOCALAPPDATA%\Mabillon\models\<file> (a reinstall, or the speed test),
;      or at %LOCALAPPDATA%\Baker\models\<file> from the Baker installer (used where it is)
;   2. next to Setup.exe (offline install: copy both files from a USB drive)
;   3. downloaded from Hugging Face, only if the person ticks that box (or /MERGETASKS=downloadmodel)
; Every copy is checked against the pinned SHA-256 before Mabillon is told about it. Mabillon is
; offline by default; the only other network use is a case the expert opts in to cloud AI.

#ifndef Stage
  #define Stage "..\..\build\stage"
#endif
#ifndef AppVersion
  #define AppVersion "0.0.1"
#endif
#ifndef ModelFile
  #error ModelFile, ModelUrl, ModelSha256, ModelName, ModelSizeGB and ModelNCtx come from pins.json (see the workflow)
#endif

[Setup]
AppId={{6F0B3C1E-6A57-4D5B-9B9E-3C1A0B7E2D41}
AppName=Mabillon
AppVersion={#AppVersion}
AppPublisher=Mabillon
AppComments=Audits government claims about phone evidence. Offline by default; cloud AI only for a case you opt in.
DefaultDirName={localappdata}\Programs\Mabillon
DefaultGroupName=Mabillon
; An update moves the Start-menu shortcuts out of an earlier "Baker" group (see [InstallDelete]).
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=Mabillon-Setup-{#AppVersion}
Compression=lzma2/normal
SolidCompression=yes
LZMANumBlockThreads=4
ChangesEnvironment=yes
WizardStyle=modern
; Artwork in the app's look (warm paper, ink mark, serif wordmark); art/make_art.py draws it.
WizardImageFile=art\wizard-100.bmp,art\wizard-150.bmp,art\wizard-200.bmp
WizardSmallImageFile=art\wizard-small-100.bmp,art\wizard-small-150.bmp,art\wizard-small-200.bmp
SetupIconFile=art\mabillon.ico
SetupLogging=yes
UninstallDisplayName=Mabillon {#AppVersion}

[Tasks]
Name: addtopath; Description: "Add the mabillon command to PATH"
Name: downloadmodel; Description: "Download the AI model {#ModelName} ({#ModelSizeGB} GB) from Hugging Face. Skip this on an offline computer and put the model file next to Setup instead."; Check: not ModelAvailable

[InstallDelete]
; A reinstall replaces Mabillon and the runtime whole, so no file from an older version stays behind.
Type: filesandordirs; Name: "{app}\baker"
Type: filesandordirs; Name: "{app}\python"
; The Start-menu shortcuts the Baker installer made, and their group once it is empty.
Type: files; Name: "{userprograms}\Baker\Baker command prompt.lnk"
Type: files; Name: "{userprograms}\Baker\Uninstall Baker.lnk"
Type: dirifempty; Name: "{userprograms}\Baker"

[Files]
Source: "{#Stage}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Stage}\baker\*"; DestDir: "{app}\baker"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Stage}\runtime\cpu\*"; DestDir: "{app}\python\Lib\site-packages"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: not UseCuda
Source: "{#Stage}\runtime\cuda\*"; DestDir: "{app}\python\Lib\site-packages"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: UseCuda
Source: "{#Stage}\baker.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\mabillon.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\BUILD_INFO.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Mabillon command prompt"; Filename: "{cmd}"; Parameters: "/k ""{app}\mabillon.cmd"" --help"; WorkingDir: "{userdocs}"
Name: "{group}\Uninstall Mabillon"; Filename: "{uninstallexe}"

[UninstallDelete]
; Case databases and the model stay: they are the person's files, not the program's.
Type: filesandordirs; Name: "{app}\baker"
Type: filesandordirs; Name: "{app}\python"

[Code]
const
  ModelFile = '{#ModelFile}';
  ModelUrl = '{#ModelUrl}';
  ModelSha256 = '{#ModelSha256}';
  ModelName = '{#ModelName}';
  ModelNCtx = '{#ModelNCtx}';
  ConfigMarker = 'written by Mabillon setup';
  OldConfigMarker = 'written by Baker setup';

var
  DownloadPage: TDownloadWizardPage;
  ModelReady: Boolean;
  RuntimeName: String;
  ChosenModelDir: String;

// A model the Baker installer placed stays where it is (PlaceModel checks it like any other).
// The folder is chosen once, so removing a model that fails its check does not move the target.
function ModelDir(): String;
begin
  if ChosenModelDir = '' then
  begin
    ChosenModelDir := ExpandConstant('{localappdata}\Mabillon\models');
    if not FileExists(ChosenModelDir + '\' + ModelFile) and
      FileExists(ExpandConstant('{localappdata}\Baker\models\') + ModelFile) then
      ChosenModelDir := ExpandConstant('{localappdata}\Baker\models');
  end;
  Result := ChosenModelDir;
end;

function ModelTarget(): String;
begin
  Result := ModelDir() + '\' + ModelFile;
end;

function ConfigFile(): String;
begin
  Result := ExpandConstant('{%USERPROFILE}\.mabillon\model.json');
end;

// Mabillon reads it while there is no ConfigFile().
function OldConfigFile(): String;
begin
  Result := ExpandConstant('{%USERPROFILE}\.baker\model.json');
end;

function HashMatches(const Path: String): Boolean;
var
  Digest: String;
begin
  Result := False;
  if not FileExists(Path) then
    Exit;
  Log('Checking SHA-256 of ' + Path);
  try
    Digest := GetSHA256OfFile(Path);
  except
    Log('Could not hash ' + Path + ': ' + GetExceptionMessage);
    Exit;
  end;
  Result := CompareText(Digest, ModelSha256) = 0;
  if not Result then
    Log('SHA-256 mismatch for ' + Path + ': ' + Digest);
end;

function NextToSetup(): String;
begin
  Result := ExpandConstant('{src}\') + ModelFile;
end;

// True when no download is needed. Hash checks run later; this only decides whether to offer one.
function ModelAvailable(): Boolean;
begin
  Result := FileExists(ModelTarget()) or FileExists(NextToSetup());
end;

function UseCuda(): Boolean;
var
  Choice: String;
begin
  Choice := Lowercase(ExpandConstant('{param:RUNTIME|auto}'));
  if Choice = 'cuda' then
    Result := True
  else if Choice = 'cpu' then
    Result := False
  else
    Result := FileExists(ExpandConstant('{sys}\nvidia-smi.exe'));
  if Result then
    RuntimeName := 'cuda'
  else
    RuntimeName := 'cpu';
end;

procedure InitializeWizard();
begin
  DownloadPage := CreateDownloadPage('Downloading the AI model',
    'About 9 GB. You can cancel and install it later from a USB drive.', nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsTaskSelected('downloadmodel') then
  begin
    DownloadPage.Clear;
    DownloadPage.Add(ModelUrl, ModelFile, ModelSha256);
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        // A failed or cancelled download is not fatal: Mabillon installs, the model comes later.
        Log('Model download did not finish: ' + GetExceptionMessage);
        SuppressibleMsgBox('The model was not downloaded (' + GetExceptionMessage + ').'#13#10 +
          'Mabillon will install now. See "Install the model later" in the install guide.',
          mbInformation, MB_OK, IDOK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

function JsonPath(const Path: String): String;
begin
  Result := Path;
  StringChangeEx(Result, '\', '/', True);
end;

// True for a model config the person wrote: one no Setup, Mabillon's or Baker's, wrote.
function PersonsOwnConfig(const Path: String): Boolean;
var
  Existing: AnsiString;
begin
  Result := FileExists(Path) and LoadStringFromFile(Path, Existing) and
    (Pos(ConfigMarker, String(Existing)) = 0) and (Pos(OldConfigMarker, String(Existing)) = 0);
end;

// Points Mabillon at the model unless the person already set up a model config of their own.
procedure WriteModelConfig();
var
  Json: String;
begin
  if PersonsOwnConfig(ConfigFile()) then
  begin
    Log('Leaving ' + ConfigFile() + ' as it is: it was not written by Setup.');
    Exit;
  end;
  if not FileExists(ConfigFile()) and PersonsOwnConfig(OldConfigFile()) then
  begin
    Log('Leaving ' + OldConfigFile() + ' as it is: it was not written by Setup, and Mabillon reads it.');
    Exit;
  end;
  ForceDirectories(ExtractFileDir(ConfigFile()));
  Json := '{' + #13#10 +
    '  "name": "' + ModelName + '",' + #13#10 +
    '  "path": "' + JsonPath(ModelTarget()) + '",' + #13#10 +
    '  "sha256": "' + Lowercase(ModelSha256) + '",' + #13#10 +
    '  "n_ctx": ' + ModelNCtx + ',' + #13#10 +
    '  "note": "' + ConfigMarker + ' {#AppVersion}; runtime ' + RuntimeName + '"' + #13#10 +
    '}' + #13#10;
  if SaveStringToFile(ConfigFile(), Json, False) then
    Log('Wrote ' + ConfigFile())
  else
    Log('Could not write ' + ConfigFile());
end;

procedure PlaceModel();
var
  Downloaded: String;
begin
  ModelReady := False;
  ForceDirectories(ModelDir());
  if HashMatches(ModelTarget()) then
  begin
    Log('Model already installed and verified.');
    ModelReady := True;
    Exit;
  end;
  if FileExists(ModelTarget()) then
  begin
    Log('Removing a model file that failed the SHA-256 check.');
    DeleteFile(ModelTarget());
  end;
  if HashMatches(NextToSetup()) then
  begin
    Log('Copying the model from next to Setup.');
    if FileCopy(NextToSetup(), ModelTarget(), False) and HashMatches(ModelTarget()) then
      ModelReady := True;
    Exit;
  end;
  if WizardIsTaskSelected('downloadmodel') then
  begin
    Downloaded := ExpandConstant('{tmp}\') + ModelFile;
    // A silent install never shows the download page, so it downloads here, with no progress.
    if WizardSilent and not FileExists(Downloaded) then
    begin
      try
        DownloadTemporaryFile(ModelUrl, ModelFile, ModelSha256, nil);
      except
        Log('Model download failed: ' + GetExceptionMessage);
      end;
    end;
    // DownloadTemporaryFile and the download page check the SHA-256 before keeping a file.
    if FileExists(Downloaded) then
    begin
      if RenameFile(Downloaded, ModelTarget()) or FileCopy(Downloaded, ModelTarget(), False) then
        ModelReady := HashMatches(ModelTarget());
    end;
  end;
end;

// Adds {app} to the user's PATH once.
procedure AddToPath();
var
  Path: String;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Path) then
    Path := '';
  if Pos(';' + Uppercase(ExpandConstant('{app}')) + ';', ';' + Uppercase(Path) + ';') > 0 then
    Exit;
  if (Path <> '') and (Copy(Path, Length(Path), 1) <> ';') then
    Path := Path + ';';
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Path + ExpandConstant('{app}'));
end;

procedure RemoveFromPath();
var
  Path: String;
  P: Integer;
  App: String;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Path) then
    Exit;
  App := ExpandConstant('{app}');
  P := Pos(';' + Uppercase(App) + ';', ';' + Uppercase(Path) + ';');
  if P = 0 then
    Exit;
  Delete(Path, P, Length(App) + 1);
  if (Length(Path) > 0) and (Copy(Path, Length(Path), 1) = ';') then
    Delete(Path, Length(Path), 1);
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Path);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    UseCuda();
    Log('Model runtime installed: ' + RuntimeName);
    if WizardIsTaskSelected('addtopath') then
      AddToPath();
    PlaceModel();
    if ModelReady then
      WriteModelConfig()
    else
      Log('No verified model file yet; Mabillon runs everything except the model steps.');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath();
end;
