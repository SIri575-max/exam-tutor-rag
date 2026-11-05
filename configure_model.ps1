param([switch]$Check,[switch]$Test)
$ErrorActionPreference='Stop'
$taskPython=Join-Path $PSScriptRoot '.venv-rag/Scripts/python.exe'
$taskScript=Join-Path $PSScriptRoot 'configure_model.py'
if($Check){& $taskPython -X utf8 $taskScript --check}
elseif($Test){& $taskPython -X utf8 $taskScript --test}
else{& $taskPython -X utf8 $taskScript}
exit $LASTEXITCODE
