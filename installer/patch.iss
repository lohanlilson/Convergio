; Atualização pequena do Convergio: contém só os arquivos que mudaram desde a versão BaseVersion.
; Gerado pelo build.py (python build.py --base-dir <pasta da versão anterior> --base-versao X.Y.Z).
#define AppName   "Convergio"
#define AppExe    "Convergio.exe"
#define AppGuid   "3680703B-A357-4D95-B063-9D9D747F6B6F"
#ifndef AppPublisher
  #define AppPublisher "Lohan Lilson S. Lopes"
#endif

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\convergio.ico
WizardSmallImageFile=..\assets\wizard_small.bmp
OutputDir=..\Saida
OutputBaseFilename=Convergio-Atualizacao-{#BaseVersion}-para-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=force
RestartApplications=no
MinVersion=10.0
SetupLogging=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#include "..\build\patch_remover.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o Convergio agora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

#include "codigo.iss"

[Code]
// só aplica sobre a versão exata para a qual foi gerada
function InitializeSetup(): Boolean;
var
  V: String;
begin
  Result := True;
  if not RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + '{#AppGuid}' + '}_is1',
                             'DisplayVersion', V) then
    V := '';
  if V <> '{#BaseVersion}' then
  begin
    Log('Atualização pequena recusada: versão instalada "' + V + '", esperada {#BaseVersion}');
    SuppressibleMsgBox('Esta atualização serve só para o Convergio {#BaseVersion}. Baixe o instalador completo em github.com/lohanlilson/Convergio.',
                       mbError, MB_OK, IDOK);
    Result := False;
  end;
end;
