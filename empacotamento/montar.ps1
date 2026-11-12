# Monta o pacote completo do Fácil em dist\Facil-<versão>\ e o compacta em dist\Facil-<versão>.zip.
# Uso, na raiz do projeto: powershell -ExecutionPolicy Bypass -File empacotamento\montar.ps1 [-Tipo teste|oficial]
# O pacote leva Python, bibliotecas, Chromium e ffmpeg, e roda sem instalação nem acesso à internet.
# O tipo "oficial" é o do build feito nos servidores do GitHub (.github\workflows\build.yml): grava no
# build.json o hash do conjunto do código, que a ferramenta confere a cada coleta. O tipo "teste" é o
# padrão, para pacotes montados no computador do desenvolvedor.
param([ValidateSet("teste", "oficial")][string]$Tipo = "teste")

$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$versao = (Select-String -Path "coletor\__init__.py" -Pattern 'VERSAO = "(.+)"').Matches[0].Groups[1].Value
$pythonBase = (Get-Content ".venv\pyvenv.cfg" | Where-Object { $_ -match '^home = ' }) -replace '^home = ', ''
$ffmpeg = if (Test-Path "componentes\ffmpeg\ffmpeg.exe") { "componentes\ffmpeg\ffmpeg.exe" }
          elseif ($Tipo -eq "oficial") { throw "O build oficial exige componentes\ffmpeg\ffmpeg.exe, com hash conferido." }
          else { (Get-Command ffmpeg).Source }
$commit = (git rev-parse HEAD).Trim()
if (git status --porcelain -- coletor) { throw "Ha alteracoes nao registradas em coletor\. Faca o commit antes de montar o pacote." }

$nome = "Facil-$versao"
$destino = Join-Path $raiz "dist\$nome"
if (Test-Path $destino) { Remove-Item $destino -Recurse -Force }
New-Item -ItemType Directory -Force $destino | Out-Null

function Copiar($origem, $alvo, [string[]]$extras) {
    robocopy $origem $alvo /E /NFL /NDL /NJH /NJS /NP @extras | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar $origem (robocopy $LASTEXITCODE)" }
}

Write-Host "Python $pythonBase"
$py = Join-Path $destino "python"
New-Item -ItemType Directory -Force $py | Out-Null
foreach ($f in "python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt") {
    Copy-Item (Join-Path $pythonBase $f) $py
}
Copiar (Join-Path $pythonBase "DLLs") (Join-Path $py "DLLs") @("/XF", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll")
Copiar (Join-Path $pythonBase "Lib") (Join-Path $py "Lib") @("/XD", "site-packages", "test", "idlelib", "tkinter", "turtledemo")
Copiar ".venv\Lib\site-packages" (Join-Path $py "Lib\site-packages") @(
    "/XD", "pytest", "_pytest", "pytest-*", "pluggy", "pluggy-*", "iniconfig", "iniconfig-*", "pip", "pip-*",
    "/XF", "py.py")

# O arquivo ._pth isola o Python do pacote: ignora PYTHONPATH, PYTHONHOME e qualquer outro Python instalado.
# Sem "import site", também não entram as bibliotecas pessoais do usuário (AppData\Roaming\Python).
$pth = "Lib`r`nDLLs`r`nLib\site-packages`r`n..`r`n"
[IO.File]::WriteAllText((Join-Path $py "python312._pth"), $pth, (New-Object Text.UTF8Encoding $false))

Write-Host "Código do aplicativo"
Copiar "coletor" (Join-Path $destino "coletor") @("/XD", "__pycache__")

Write-Host "Componentes"
Copiar "componentes\chrome-win64" (Join-Path $destino "componentes\chrome-win64") @()
New-Item -ItemType Directory -Force (Join-Path $destino "componentes\ffmpeg") | Out-Null
Copy-Item $ffmpeg (Join-Path $destino "componentes\ffmpeg\ffmpeg.exe")

$ffmpegVersao = (& $ffmpeg -hide_banner -version | Select-Object -First 1)
$chromeVersao = (Get-Item "componentes\chrome-win64\chrome.exe").VersionInfo.ProductVersion
# O hash do conjunto do código é calculado pelo Python do próprio pacote, com a mesma função que a
# ferramenta usa na coleta (-B: sem gravar __pycache__ no pacote).
$hashCodigo = (& (Join-Path $py "python.exe") -B -c "from coletor.nucleo import ferramenta; print(ferramenta.hash_do_codigo())").Trim()
if ($LASTEXITCODE -ne 0 -or $hashCodigo.Length -ne 64) { throw "Falha ao calcular o hash do codigo" }
$build = [ordered]@{
    versao = $versao; commit = $commit
    tipo = if ($Tipo -eq "oficial") { "oficial" } else { "teste, sem assinatura digital" }
    hash_codigo = $hashCodigo
    montado_em = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    python = (& (Join-Path $py "python.exe") -c "import sys; print(sys.version.split()[0])")
    chromium = $chromeVersao; ffmpeg = $ffmpegVersao
}
[IO.File]::WriteAllText((Join-Path $destino "build.json"), ($build | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))

Write-Host "Atalhos e textos"
$iniciar = "@echo off`r`nrem Inicia o Facil: Coletor de Evidencias Digitais Intuitivo.`r`ncd /d `"%~dp0`"`r`nstart `"`" `"%~dp0python\pythonw.exe`" -m coletor`r`n"
$verificar = "@echo off`r`nrem Arraste a pasta COLETA_... sobre este arquivo para conferir a integridade da coleta.`r`ncd /d `"%~dp0`"`r`nif `"%~1`"==`"`" (`r`n  echo Arraste a pasta da coleta sobre este arquivo.`r`n  pause`r`n  exit /b`r`n)`r`n`"%~dp0python\python.exe`" -m coletor.verificar `"%~1`"`r`npause`r`n"
[IO.File]::WriteAllText((Join-Path $destino "Iniciar Facil.bat"), $iniciar, [Text.Encoding]::ASCII)
[IO.File]::WriteAllText((Join-Path $destino "Verificar coleta.bat"), $verificar, [Text.Encoding]::ASCII)
Copy-Item "README.md", "LICENSE" $destino
$terceiros = Get-Content (Join-Path $PSScriptRoot "LICENCAS-TERCEIROS.txt") -Raw -Encoding UTF8
$terceiros = $terceiros.Replace("{CHROMIUM}", $chromeVersao).Replace("{FFMPEG}", $ffmpegVersao).Replace("{PYTHON}", $build.python)
[IO.File]::WriteAllText((Join-Path $destino "LICENCAS-TERCEIROS.txt"), $terceiros, (New-Object Text.UTF8Encoding $true))

Write-Host "Compactando"
$zip = Join-Path $raiz "dist\$nome.zip"
& ".venv\Scripts\python.exe" -I (Join-Path $PSScriptRoot "zipar.py") $destino $zip
if ($LASTEXITCODE -ne 0) { throw "Falha ao compactar" }

$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
$tamanho = "{0:N0} MB" -f ((Get-Item $zip).Length / 1MB)
"$hash  $nome.zip" | Set-Content (Join-Path $raiz "dist\$nome.zip.sha256") -Encoding ASCII
Write-Host "Pronto: $zip ($tamanho)"
Write-Host "SHA-256: $hash"
Write-Host "Commit: $commit"
Write-Host "Hash do codigo: $hashCodigo"
Write-Host "Tipo: $Tipo"
