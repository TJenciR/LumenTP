$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.venv')) {
    py -3 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .

Write-Host 'Environment ready.'
Write-Host 'Activate with: .\.venv\Scripts\Activate.ps1'
Write-Host 'Then use: lumentp ping --host 127.0.0.1 --port 8091'
