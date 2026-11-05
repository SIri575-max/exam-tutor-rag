$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv-rag/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '请指定可用的 Python 3.12 路径。' }
& $taskPython -X utf8 patch_local_ocr.py
if ($LASTEXITCODE -ne 0) { throw 'OCR兼容处理失败，请先检查本地环境版本。' }
& $taskPython -X utf8 process_full_book.py --workers 2 --batch-size 12
if ($LASTEXITCODE -ne 0) { throw '仍有OCR失败页；进度已保存，检查data/private/full-book/progress.json后可续跑。' }
& $taskPython -X utf8 organize_full_book.py
if ($LASTEXITCODE -ne 0) { throw '整理导出失败，请查看终端日志。' }
& $taskPython -X utf8 verify_full_book.py
if ($LASTEXITCODE -ne 0) { throw '覆盖或文件完整性检查未通过，查看coverage-audit.json。' }
Write-Host '全书整理完成。入口：data/private/full-book/exports/开始阅读.md；公式与表格仍需校对。'
