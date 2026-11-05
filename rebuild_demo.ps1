$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython=Join-Path $PSScriptRoot '.venv-rag/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Install requirements-retrieval.txt into .venv-rag first.' }
if (-not (Test-Path -LiteralPath 'data/private/embedding-bootstrap.json')) {
    & $taskPython -X utf8 download_embedding.py
    if ($LASTEXITCODE -ne 0) { throw 'Embedding model download failed.' }
}
foreach ($taskScript in @('course_data.py','vector_index.py','export_reference_adapters.py')) {
    & $taskPython -X utf8 $taskScript
    if ($LASTEXITCODE -ne 0) { throw "Failed: $taskScript" }
}
Write-Host 'Preview corpus, semantic index and optional adapter exports rebuilt.'
