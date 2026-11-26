@echo off
REM Halcyon in a window (python -m ui). Extra arguments are passed on, for example --demo.
setlocal
cd /d "%~dp0"
title Halcyon

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    pause
    exit /b 1
)

if exist "venv\Scriptsctivate.bat" call "venv\Scriptsctivate.bat"

python -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo ERROR: the window needs pywebview. Install the requirements first:
    echo     pip install -r requirements.txt
    pause
    exit /b 1
)

ollama list >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama is not running or not installed: https://ollama.com
    echo.
)

python -m ui %*
if errorlevel 1 pause
