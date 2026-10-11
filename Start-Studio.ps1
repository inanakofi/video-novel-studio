param([string]$Workspace = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$studioPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) {
    $studioPython = (Get-Command python -ErrorAction Stop).Source
}
& $studioPython -m src.app --workspace $Workspace
if ($LASTEXITCODE -ne 0) { throw 'Video Novel Studio stopped with an error. Run python -m src.doctor to check the environment.' }
