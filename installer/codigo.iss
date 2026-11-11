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
