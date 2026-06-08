@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONPATH=

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
set "BATCH_PRO_PY=%SCRIPT_DIR%autosub_batch_pro.py"

echo [AutoSub] 正在启动 Batch Pro 1.0...
python "%BATCH_PRO_PY%" %*

if %ERRORLEVEL% neq 0 (
    echo [错误] 程序异常退出 (Code: %ERRORLEVEL%)
    pause
)