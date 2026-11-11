; Instalador do Convergio (Inno Setup 6)
#define AppName   "Convergio"
#define AppExe    "Convergio.exe"
#define AppGuid   "3680703B-A357-4D95-B063-9D9D747F6B6F"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Lohan Lilson S. Lopes"
#endif
#ifndef AppEmail
  #define AppEmail ""
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Convergio"
#endif

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppContact={#AppEmail}
AppSupportURL=https://github.com/lohanlilson/Convergio
AppPublisherURL=https://github.com/lohanlilson/Convergio
AppCopyright=© 2026 {#AppPublisher}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=© 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\convergio.ico
WizardImageFile=..\assets\wizard.bmp
WizardSmallImageFile=..\assets\wizard_small.bmp
OutputDir=..\Saida
OutputBaseFilename=Convergio-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=force
RestartApplications=no
AppMutex=Convergio_Running
MinVersion=10.0
SetupLogging=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; extensão do navegador (Chrome, Edge, Brave, Opera): "Carregar sem compactação" nesta pasta
Source: "..\extensao\*"; DestDir: "{app}\extensao"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; arquivos de versões anteriores (o PyInstaller pode mudar nomes de bibliotecas entre versões)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Convergio.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Convergio.App"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey
; protocolo convergio:<link> — permite que o navegador (ou uma extensão) envie downloads para o programa
Root: HKA; Subkey: "Software\Classes\convergio"; ValueType: string; ValueName: ""; ValueData: "URL:Convergio"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\convergio"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\convergio\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\convergio\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

; o programa grava "iniciar com o Windows" nesta chave; a desinstalação remove
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Convergio"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o Convergio agora"; Flags: nowait postinstall skipifsilent
; atualização automática (instalação silenciosa): reabre o programa ao terminar
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
; encerra o Convergio que estiver na bandeja antes de remover os arquivos
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "EncerrarConvergio"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\extensao"
