param([int]$Port=8771)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython=Join-Path $PSScriptRoot '.venv-rag/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv-rag and install requirements-retrieval.txt first; see README.' }
Write-Host "Open http://127.0.0.1:$Port/"
& $taskPython -X utf8 app.py --port $Port
