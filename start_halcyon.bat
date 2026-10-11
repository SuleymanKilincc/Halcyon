@echo off
REM Halcyon launcher for Windows: checks the basics, then starts the voice assistant.
REM Extra arguments are passed on, for example:  start_halcyon.bat --profile battery
setlocal
cd /d "%~dp0"
title Halcyon

echo ========================================
echo   HALCYON - local voice assistant
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    pause
    exit /b 1
)

if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat

REM Looks for the modules without importing them, so the check is instant.
python -c "import importlib.util as u, sys; sys.exit(any(u.find_spec(m) is None for m in ('faster_whisper','sounddevice','silero_vad','piper','ollama','torch')))" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Voice dependencies are missing.
    echo Install them with:  pip install -r requirements.txt
    pause
    exit /b 1
)

ollama list >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not running or not installed. Start Ollama first.
    pause
    exit /b 1
)

echo Use headphones: there is no echo cancellation yet.
echo Just talk. Press Ctrl+C to quit.
echo.
python -m voice.cli --llm %*

if errorlevel 1 (
    echo.
    echo Halcyon stopped with an error.
    pause
)
