@echo off
echo.
echo ============================================================
echo Sound Multi Analysis System
echo 管理員帳戶初始化工具
echo ============================================================
echo.

cd /d "%~dp0"

REM 檢查 Python 環境
if exist "..\..\..\.venv\Scripts\python.exe" (
    set PYTHON_EXE=..\..\..\.venv\Scripts\python.exe
    echo 使用專案虛擬環境
) else (
    set PYTHON_EXE=python
    echo 使用系統 Python 環境
)

echo.
echo 啟動初始化工具...
echo.

%PYTHON_EXE% init_admin.py

echo.
pause