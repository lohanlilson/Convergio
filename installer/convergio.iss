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
Type: files; Name: "{app}\*.antigo"
Type: filesandordirs; Name: "{app}\extensao"

[Code]
// Antes de copiar os arquivos:
//  1. encerra o Convergio e qualquer outro processo rodando de dentro da pasta do programa;
//  2. arquivos que continuam em uso (processo preso, antivírus, DLL carregada por outro programa)
//     são renomeados para *.antigo (o Windows permite renomear arquivos em uso) e os novos são
//     gravados no lugar. As sobras *.antigo são apagadas na próxima atualização ou ao abrir o programa.
// Assim a instalação não é desfeita por "arquivo em uso".

function ArquivoTravado(const Nome: String): Boolean;
var
  S: TFileStream;
begin
  Result := False;
  try
    S := TFileStream.Create(Nome, fmOpenReadWrite or fmShareExclusive);
    S.Free;
  except
    Result := True;
  end;
end;

procedure LiberarArquivos(const Pasta: String);
var
  R: TFindRec;
  Caminho: String;
  Tentativa: Integer;
begin
  if FindFirst(Pasta + '\*', R) then
  try
    repeat
      if (R.Name <> '.') and (R.Name <> '..') then
      begin
        Caminho := Pasta + '\' + R.Name;
        if (R.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          LiberarArquivos(Caminho)
        else if CompareText(ExtractFileExt(Caminho), '.antigo') = 0 then
          DeleteFile(Caminho)
        else
        begin
          Tentativa := 0;
          while ArquivoTravado(Caminho) and (Tentativa < 6) do
          begin
            if RenameFile(Caminho, Caminho + '.' + GetDateTimeString('yyyymmddhhnnsszzz', #0, #0) + '.antigo') then
            begin
              Log('Arquivo em uso foi renomeado para liberar a atualização: ' + Caminho);
              Break;
            end;
            Log('Arquivo em uso, aguardando: ' + Caminho);
            Sleep(500);
            Tentativa := Tentativa + 1;
          end;
        end;
      end;
    until not FindNext(R);
  finally
    FindClose(R);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Pasta, Cmd: String;
begin
  Result := '';
  Pasta := ExpandConstant('{app}');
  // pede para fechar; depois força o Convergio e qualquer processo executado de dentro da pasta
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Convergio.exe', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Sleep(2000);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM Convergio.exe', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Cmd := '-NoProfile -ExecutionPolicy Bypass -Command "Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith(''' +
         Pasta + '\'', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force"';
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Sleep(1000);
  if DirExists(Pasta) then
    LiberarArquivos(Pasta);
end;
