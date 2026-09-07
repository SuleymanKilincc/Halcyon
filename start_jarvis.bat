@echo off
REM Jarvis AI Agent Launcher for Windows
REM This script starts the Jarvis agent with proper checks

echo ========================================
echo   JARVIS AI AGENT LAUNCHER
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo WARNING: No virtual environment found
    echo Consider creating one with: python -m venv venv
    echo.
)

REM Check if dependencies are installed
python -c "import langchain" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Dependencies not installed
    echo Please run: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check if Ollama is running
ollama list >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama is not running or not installed
    echo Please start Ollama or install it from https://ollama.ai
    echo.
    pause
)

REM Launch Jarvis
echo Starting Jarvis...
echo.
python agent.py

pause
