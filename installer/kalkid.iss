; Installateur de Kalkid Rétro (Inno Setup 6)
; Compilation : iscc /DAppVersion=0.4.0 installer\kalkid.iss   (l'exe doit être dans dist\Kalkid-Retro.exe)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Kalkid Rétro"
#define AppExe "Kalkid-Retro.exe"
#define AppUrl "https://github.com/KalDT13/Kalkid-Retro"

[Setup]
AppId={{6B0E5C2A-3D1F-4C57-9A6E-0B7D2C41E5F9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=KalDT13
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
; Installation par utilisateur : aucun droit administrateur, et l'application peut se mettre à jour seule
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Kalkid Retro
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\kalkid.ico
OutputDir=..\dist
OutputBaseFilename=Kalkid-Retro-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Windows 10 1607 minimum (API de lecture des notifications), 64 bits
MinVersion=10.0.14393
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le &Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked
Name: "startupicon"; Description: "Lancer {#AppName} au &démarrage de Windows (réduit dans la zone de notification)"; GroupDescription: "Démarrage :"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autoprograms}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"

[Registry]
; même valeur que l'interrupteur « Lancer avec Windows » de l'application
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --hidden"; Tasks: startupicon; Flags: uninsdeletevalue

[Run]
Filename: "ms-settings:notifications"; Description: "Ouvrir les paramètres de notifications de Windows (nécessaire à l'autofocus)"; Flags: shellexec postinstall skipifsilent unchecked; Check: ToastsDisabled
Filename: "{app}\{#AppExe}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CheckPage: TOutputMsgMemoWizardPage;

function ToastsDisabled: Boolean;
var
  Value: Cardinal;
begin
  Result := RegQueryDWordValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\PushNotifications',
    'ToastEnabled', Value) and (Value = 0);
end;

function DofusRetroFound: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Ankama\Retro\Dofus Retro.exe'));
end;

function BuildReport: String;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := '';

  Result := Result + '[OK]  Windows compatible (version ' + IntToStr(Version.Major) + '.' +
    IntToStr(Version.Minor) + ', build ' + IntToStr(Version.Build) + ').' + #13#10#13#10;

  if Is64BitInstallMode then
    Result := Result + '[OK]  Système 64 bits.' + #13#10#13#10
  else
    Result := Result + '[!]  Système 32 bits : non pris en charge.' + #13#10#13#10;

  if ToastsDisabled then
    Result := Result + '[!]  Les notifications Windows sont désactivées. L''autofocus ne fonctionnera pas ' +
      'tant qu''elles ne sont pas activées (Paramètres > Système > Notifications). ' +
      'Une case à cocher à la fin de l''installation ouvre ce réglage.' + #13#10#13#10
  else
    Result := Result + '[OK]  Notifications Windows activées.' + #13#10#13#10;

  if DofusRetroFound then
    Result := Result + '[OK]  Dofus Rétro détecté sur ce PC.' + #13#10#13#10
  else
    Result := Result + '[i]  Dofus Rétro n''a pas été trouvé à l''emplacement habituel. Ce n''est pas bloquant : ' +
      'Kalkid Rétro détecte les fenêtres du jeu au lancement.' + #13#10#13#10;

  Result := Result + 'À activer dans le jeu pour l''autofocus : Options > Général > « Notification en ' +
    'arrière-plan ». L''onglet Prérequis de l''application le vérifie ensuite pour vous.';
end;

procedure InitializeWizard;
begin
  CheckPage := CreateOutputMsgMemoPage(wpWelcome, 'Vérification de votre PC',
    '{#AppName} contrôle que votre ordinateur est prêt.', 'Résultat des vérifications :', BuildReport);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Supprimer aussi vos réglages et vos icônes personnalisées de {#AppName} ?',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\KalkidRetro'), True, True, True);
end;
