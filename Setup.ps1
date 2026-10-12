$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python could not create the virtual environment.' }
$studioPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $studioPython -m pip install --upgrade 'pip>=26.2,<27'
if ($LASTEXITCODE -ne 0) { throw 'Could not update pip. Check network access and run Setup.ps1 again.' }
& $studioPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $studioPython -m src.doctor
if ($LASTEXITCODE -ne 0) { throw 'Install FFmpeg and FFprobe, add their bin folder to PATH, then run Setup.ps1 again.' }
Write-Output 'Ready. Run .\Start-Studio.ps1 to open the studio.'
