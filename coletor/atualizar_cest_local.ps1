# Atualiza só o Convênio ICMS 142/2018 (CEST) a partir de um PC no Brasil e publica se mudou.
# O site do CONFAZ recusa conexões de fora do Brasil, então o GitHub Actions (EUA) pula
# essa base; as demais são atualizadas lá todo dia.
#
# Roda pela tarefa agendada "Ficha Fiscal - atualizar CEST" (semanal). Registro em
# %LOCALAPPDATA%\Ficha Fiscal\atualizar_cest.log
param([string]$Python = "python")

$ErrorActionPreference = "Continue"  # stderr do git não deve virar exceção (PowerShell 5.1)
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA "Ficha Fiscal"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "atualizar_cest.log"

function Registrar($texto) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm') $texto" | Out-File $log -Append -Encoding utf8 }

try {
    Set-Location $repo
    git pull --quiet --rebase 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git pull falhou" }

    $env:PULAR = "cat68,ncm,monofasico,ibscbs"
    $env:PYTHONIOENCODING = "utf-8"
    $saida = & $Python coletor\atualizar.py 2>&1 | Out-String
    $codigo = $LASTEXITCODE
    # status.json é da execução diária na nuvem: não sobrescreve com esta execução parcial
    git checkout -- status.json 2>&1 | Out-Null
    if ($codigo -ne 0) { throw "falha ao ler o CONFAZ:`n$saida" }

    git add dados/base_cest.csv dados/base_cest.json manifest.json bases.json.gz
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) { Registrar "CEST sem mudanças."; exit 0 }
    $versao = (Get-Content manifest.json -Raw | ConvertFrom-Json).versao
    git commit --quiet -m "Bases normativas $versao (CEST atualizado pelo CONFAZ)"
    git push --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git push falhou" }
    Registrar "CEST atualizado e publicado: $versao"
} catch {
    Registrar "ERRO: $_"
    exit 1
}
