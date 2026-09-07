#!/bin/bash
# Jarvis AI Agent Launcher for Linux/macOS
# This script starts the Jarvis agent with proper checks

echo "========================================"
echo "   JARVIS AI AGENT LAUNCHER"
echo "========================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Python version: $PYTHON_VERSION"

# Check if virtual environment exists
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "WARNING: No virtual environment found"
    echo "Consider creating one with: python3 -m venv venv"
    echo
fi

# Check if dependencies are installed
python3 -c "import langchain" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Dependencies not installed"
    echo "Please run: pip install -r requirements.txt"
    exit 1
fi

# Check if Ollama is running
ollama list &> /dev/null
if [ $? -ne 0 ]; then
    echo "WARNING: Ollama is not running or not installed"
    echo "Please start Ollama or install it from https://ollama.ai"
    echo
    read -p "Press Enter to continue anyway..."
fi

# Launch Jarvis
echo "Starting Jarvis..."
echo
python3 agent.py
