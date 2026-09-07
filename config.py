"""
Configuration module for Jarvis AI Agent.
Handles Ollama model settings, system prompts, and environment constants.
"""

import os
from pathlib import Path

# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

# Ollama model to use (choose one)
OLLAMA_MODEL = "qwen3.5:9b"  # Primary model
# OLLAMA_MODEL = "qwen2.5-coder:7b"  # Alternative
# OLLAMA_MODEL = "qwen2.5:7b"      # Alternative

# Ollama server configuration
OLLAMA_BASE_URL = "http://localhost:11434"

# Model parameters
MODEL_TEMPERATURE = 0.7
MODEL_TOP_P = 0.9
MODEL_MAX_TOKENS = 2048

# ============================================================================
# WORKSPACE CONFIGURATION
# ============================================================================

# Base directory for the project
BASE_DIR = Path(__file__).parent.absolute()

# Workspace directory where agent can safely operate
WORKSPACE_DIR = BASE_DIR / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True)

# ============================================================================
# SAFETY CONFIGURATION
# ============================================================================

# Commands that require explicit approval
DANGEROUS_COMMAND_KEYWORDS = [
    "rm -rf",
    "format",
    "del /f",
    "rmdir /s",
    "dd if=",
    "mkfs",
    "> /dev/",
    "chmod 777",
    "chmod -R 777",
    ":(){ :|:& };:",  # Fork bomb
    "mv /* ",
    "rm -r /",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
]

# File extensions that require approval for modification
SENSITIVE_EXTENSIONS = [
    ".exe", ".dll", ".so", ".dylib",
    ".sh", ".bat", ".cmd", ".ps1",
    ".sys", ".ini", ".conf", ".config"
]

# Maximum file size for reading (in bytes)
MAX_FILE_READ_SIZE = 10 * 1024 * 1024  # 10 MB

# Maximum command output length (in characters)
MAX_OUTPUT_LENGTH = 5000

# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SYSTEM_PROMPT = """You are Jarvis, an advanced AI assistant with the ability to interact with the local system.

You have access to the following capabilities:
1. **Terminal Access**: Execute shell commands on the local system
2. **File System Operations**: Read, write, and manage files
3. **Web Search**: Search the internet using DuckDuckGo
4. **Web Scraping**: Fetch and parse content from websites

## Core Principles:
- Always think step-by-step before taking action
- Ask for clarification when instructions are ambiguous
- Prioritize safety and data integrity
- Explain your reasoning before executing critical operations
- Work within the designated workspace directory when possible

## Safety Guidelines:
- ALWAYS request approval before executing terminal commands
- ALWAYS request approval before modifying or deleting files
- Never execute obviously destructive commands
- Inform the user about potential risks of operations
- Stay within the workspace directory unless explicitly instructed otherwise

## Response Format:
When solving tasks, follow this pattern:
1. **Thought**: Explain what you're going to do and why
2. **Action**: Use the appropriate tool
3. **Observation**: Analyze the result
4. **Repeat** until the task is complete

Be concise but thorough. Prioritize accuracy and safety over speed.
"""

AGENT_DESCRIPTION = """Jarvis - Your Local AI Assistant

Powered by: {model}
Workspace: {workspace}

Available Commands:
- /help     - Show available commands
- /reset    - Clear conversation history
- /workspace - Show workspace directory
- /exit     - Exit Jarvis

Type your request or ask me anything!
"""

# ============================================================================
# UI CONFIGURATION
# ============================================================================

# Color codes for terminal output (if colorama is used)
COLORS = {
    "jarvis": "\033[94m",      # Blue
    "user": "\033[92m",        # Green
    "warning": "\033[93m",     # Yellow
    "error": "\033[91m",       # Red
    "info": "\033[96m",        # Cyan
    "reset": "\033[0m",        # Reset
}

# CLI prompts
CLI_PROMPT_USER = "You: "
CLI_PROMPT_JARVIS = "Jarvis: "

# ============================================================================
# WEB SEARCH CONFIGURATION
# ============================================================================

# DuckDuckGo search settings
SEARCH_MAX_RESULTS = 5
SEARCH_REGION = "wt-wt"  # Worldwide
SEARCH_SAFESEARCH = "moderate"

# Web scraping settings
REQUEST_TIMEOUT = 10  # seconds
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Global approval callback (set by GUI)
_approval_callback = None

def set_approval_callback(callback):
    """
    Set the global approval callback function.
    This should be called by the GUI to register its approval dialog.
    
    Args:
        callback: Function that takes (operation, details) and returns bool
    """
    global _approval_callback
    _approval_callback = callback

def get_approval_callback():
    """
    Get the current approval callback function.
    
    Returns:
        Approval callback function or None
    """
    return _approval_callback

def get_workspace_path(relative_path: str = "") -> Path:
    """
    Convert a relative path to an absolute path within the workspace.
    
    Args:
        relative_path: Path relative to workspace directory
        
    Returns:
        Absolute Path object
    """
    if relative_path:
        return (WORKSPACE_DIR / relative_path).resolve()
    return WORKSPACE_DIR

def is_safe_path(path: Path) -> bool:
    """
    Check if a path is within the workspace directory.
    
    Args:
        path: Path to check
        
    Returns:
        True if path is within workspace, False otherwise
    """
    try:
        path = Path(path).resolve()
        workspace = WORKSPACE_DIR.resolve()
        return str(path).startswith(str(workspace))
    except Exception:
        return False
