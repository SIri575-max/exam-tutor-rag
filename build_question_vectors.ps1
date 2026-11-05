$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython=Join-Path $PSScriptRoot '.venv-rag/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv-rag and install requirements-retrieval.txt; use the cached local BGE model described in README.' }
& $taskPython -X utf8 exercise_vectors.py
if ($LASTEXITCODE -ne 0) { throw 'Question vector build failed' }
& $taskPython -X utf8 verify_question_vectors.py
if ($LASTEXITCODE -ne 0) { throw 'Question vector integrity verification failed' }
& $taskPython -X utf8 question_knowledge.py
if ($LASTEXITCODE -ne 0) { throw 'Question knowledge graph build failed' }
& $taskPython -X utf8 verify_question_graph.py
if ($LASTEXITCODE -ne 0) { throw 'Question graph verification failed' }
& $taskPython -X utf8 problem_feedback.py
if ($LASTEXITCODE -ne 0) { throw 'Review queue export failed' }
& $taskPython -X utf8 evaluate_question_vectors.py
if ($LASTEXITCODE -ne 0) { throw 'Question source-location checks failed' }
Write-Host 'Ready: run ./start_demo.ps1 and open http://127.0.0.1:8771/problems'
