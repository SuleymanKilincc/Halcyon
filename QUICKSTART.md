# Jarvis Quick Start Guide

Get your local AI assistant running in minutes!

## Prerequisites

1. **Python 3.8+** installed on your system
2. **Ollama** installed and running

## Step 1: Install Ollama

### Windows
```bash
# Download and install from: https://ollama.ai/download
```

### Linux / macOS
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

## Step 2: Pull the AI Model

```bash
# Pull the recommended model (7B parameters)
ollama pull qwen2.5-coder:7b

# Alternative: Larger model for better performance (requires more RAM)
# ollama pull qwen2.5:7b
```

Verify the model is installed:
```bash
ollama list
```

## Step 3: Install Python Dependencies

Create a virtual environment (recommended):
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Step 4: Launch Jarvis

```bash
python agent.py
```

You should see the Jarvis welcome banner and be ready to interact!

## First Commands to Try

1. **Explore the workspace:**
   ```
   List files in the current directory
   ```

2. **Create a simple file:**
   ```
   Create a Python file called hello.py that prints "Hello from Jarvis!"
   ```

3. **Search the web:**
   ```
   Search the web for Python async programming best practices
   ```

4. **Run a command:**
   ```
   Run the command "python --version"
   ```

## Built-in Commands

- `/help` - Show available commands
- `/reset` - Clear conversation history
- `/workspace` - Show workspace directory
- `/tools` - List all available tools
- `/exit` - Exit Jarvis

## Safety Features

Jarvis will **always ask for approval** before:
- Executing terminal commands
- Creating or modifying files
- Deleting files
- Any potentially destructive operation

Simply respond with `Y` or `N` when prompted.

## Troubleshooting

### "Connection refused" error
- Make sure Ollama is running: `ollama serve`

### "Model not found" error
- Pull the model: `ollama pull qwen2.5-coder:7b`

### "Module not found" error
- Install dependencies: `pip install -r requirements.txt`

### Slow responses
- The model is running inference on your GPU/CPU
- First response might be slower (model loading)
- Consider using a smaller model if needed

## Configuration

Edit `config.py` to customize:
- Model selection (change `OLLAMA_MODEL`)
- Temperature and creativity settings
- Safety filters and file size limits
- System prompts and behavior

## Workspace

All file operations default to the `workspace/` directory for safety. This keeps your system files protected while giving Jarvis a sandbox to work in.

## Next Steps

Try combining capabilities:
- "Search for Python sorting algorithms, then create a file with examples"
- "List all Python files in this directory and show me the contents of the largest one"
- "Create a README.md file explaining what this project does"

Have fun with your local AI assistant! 🚀
