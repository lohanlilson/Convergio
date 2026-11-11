# Instala a versão anterior, deixa o programa aberto, aplica a atualização pequena como o programa faz e
# confere: versão nova, pasta idêntica à do instalador completo e autoteste do programa instalado.
param([string]$Versao)
$ErrorActionPreference = "Stop"
$patch = Get-ChildItem "Saida\Convergio-Atualizacao-*-para-$Versao.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $patch) { Write-Host "Sem atualização pequena nesta versão."; exit 0 }
Write-Host ("Atualização pequena: {0} ({1:N1} MB); instalador completo: {2:N1} MB" -f $patch.Name, ($patch.Length/1MB), ((Get-Item "Saida\Convergio-Setup-$Versao.exe").Length/1MB))
$p = Start-Process .\anterior.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -PassThru; $p.WaitForExit()
Start-Sleep 6
$key = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3680703B-A357-4D95-B063-9D9D747F6B6F}_is1"
$dir = (Get-ItemProperty $key).InstallLocation
if (-not (Get-Process Convergio -ErrorAction SilentlyContinue)) { Start-Process (Join-Path $dir "Convergio.exe"); Start-Sleep 6 }
$log = "$env:TEMP\convergio-patch.log"
$p = Start-Process $patch.FullName -ArgumentList '/SILENT','/NORESTART','/CLOSEAPPLICATIONS',"/LOG=`"$log`"" -PassThru; $p.WaitForExit()
Start-Sleep 5; Get-Process Convergio -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2
$ver = (Get-ItemProperty $key).DisplayVersion
Write-Host "Código de saída: $($p.ExitCode) | versão instalada: $ver"
if ($p.ExitCode -ne 0 -or $ver -ne $Versao) { Get-Content $log | Select-Object -Last 40; throw "A atualização pequena não foi aplicada" }
python build.py --conferir "$dir"
if ($LASTEXITCODE -ne 0) { throw "A pasta depois da atualização pequena não está idêntica à do instalador completo" }
$s = Start-Process (Join-Path $dir "Convergio.exe") -ArgumentList "--selftest","selftest-patch.txt" -PassThru; $s.WaitForExit()
Get-Content selftest-patch.txt | Select-Object -Last 4
if ($s.ExitCode -ne 0) { throw "Autoteste depois da atualização pequena falhou" }
# a atualização pequena tem que recusar outra versão instalada
$p = Start-Process $patch.FullName -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -PassThru; $p.WaitForExit()
Write-Host "Aplicar de novo sobre a versão já atualizada: código $($p.ExitCode) (esperado: diferente de 0)"
if ($p.ExitCode -eq 0) { throw "A atualização pequena deveria recusar uma versão diferente da base" }
$p = Start-Process (Join-Path $dir "unins000.exe") -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES' -PassThru; $p.WaitForExit()
Start-Sleep 3
