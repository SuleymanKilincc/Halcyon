# Troubleshooting Guide

Common issues and their solutions.

## Installation Issues

### ❌ "Ollama not found"

**Problem**: The `ollama` command is not recognized.

**Solution**:
1. Install Ollama from https://ollama.ai/download
2. Restart your terminal after installation
3. Verify with: `ollama --version`

### ❌ "Model not found"

**Problem**: The specified model hasn't been downloaded.

**Solution**:
```bash
# Pull the required model
ollama pull qwen2.5-coder:7b

# Verify it's installed
ollama list
```

### ❌ Module Import Errors

**Problem**: `ModuleNotFoundError: No module named 'langchain'`

**Solution**:
```bash
# Make sure you're in the project directory
cd /path/to/jarvis

# Install all dependencies
pip install -r requirements.txt

# If using a virtual environment, activate it first:
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
```

## Runtime Issues

### ❌ "Connection refused" to Ollama

**Problem**: Jarvis can't connect to Ollama server.

**Solution**:
```bash
# Start Ollama server (if not running)
ollama serve

# Or on some systems it starts automatically
# Check if it's running:
ollama list
```

### ❌ Slow Response Times

**Problem**: Jarvis takes a long time to respond.

**Causes & Solutions**:

1. **First run is always slower** (model loading)
   - Wait for the first response to complete
   - Subsequent responses will be faster

2. **Large model on limited hardware**
   - Use a smaller model:
     ```bash
     ollama pull qwen2.5:3b  # Smaller, faster
     ```
   - Update `config.py`:
     ```python
     OLLAMA_MODEL = "qwen2.5:3b"
     ```

3. **GPU not being utilized**
   - Check GPU availability: `ollama ps`
   - Ollama should automatically use GPU if available

### ❌ "Max iterations reached"

**Problem**: Agent stops with "Agent stopped due to max iterations."

**Cause**: Complex task requires too many steps.

**Solutions**:
1. Break the task into smaller steps
2. Increase max iterations in `agent.py`:
   ```python
   self.agent_executor = AgentExecutor(
       agent=agent,
       tools=tools,
       max_iterations=20,  # Increase from 15
   )
   ```

### ❌ Tool Execution Errors

**Problem**: "Error executing command" or "Error writing file"

**Solutions**:

1. **Permission issues**:
   - Run with appropriate permissions
   - Check workspace directory permissions

2. **Path issues**:
   - Use relative paths from workspace
   - Or specify full absolute paths

3. **Command not found**:
   - Ensure the command exists on your system
   - Use full path to executable if needed

## Web Search Issues

### ❌ "Search error: rate limit"

**Problem**: Too many searches in a short time.

**Solution**:
- Wait a few minutes before searching again
- DuckDuckGo has rate limits to prevent abuse

### ❌ "Timeout fetching webpage"

**Problem**: Website didn't respond in time.

**Solutions**:
1. Try again (website might be temporarily down)
2. Increase timeout in `config.py`:
   ```python
   REQUEST_TIMEOUT = 20  # Increase from 10 seconds
   ```

### ❌ "Error parsing webpage"

**Problem**: Website has unusual HTML structure.

**Solution**:
- Some websites block scrapers
- Try a different URL or source
- The tool works best with standard HTML pages

## Memory and Performance

### ❌ "Out of memory"

**Problem**: System runs out of RAM.

**Solutions**:
1. Use a smaller model:
   ```bash
   ollama pull qwen2.5:3b
   ```

2. Reduce context window in `config.py`:
   ```python
   MODEL_MAX_TOKENS = 1024  # Reduce from 2048
   ```

3. Clear conversation history:
   ```
   /reset
   ```

### ❌ Agent becomes unresponsive

**Problem**: Jarvis stops responding.

**Solutions**:
1. Press `Ctrl+C` to interrupt
2. Restart Jarvis
3. Check Ollama is still running: `ollama list`

## Approval Prompt Issues

### ❌ Can't approve operations

**Problem**: Approval prompt doesn't accept input.

**Solution**:
- Make sure you're typing `Y` or `N` (case insensitive)
- Press Enter after typing
- Check your terminal supports interactive input

### ❌ Too many approval prompts

**Problem**: Getting approval request for every action.

**Note**: This is by design for safety!

**To reduce prompts**:
- Modify safety settings in `config.py`
- **Warning**: Only do this if you understand the risks

## Configuration Issues

### ❌ "Config file not found"

**Problem**: Can't find `config.py`.

**Solution**:
- Make sure you're running from the project directory
- Check that `config.py` exists
- Don't rename or move config files

### ❌ Changes to config.py not taking effect

**Problem**: Modified settings aren't being used.

**Solution**:
1. Restart Jarvis after config changes
2. Check for syntax errors in config.py
3. Python caches modules - delete `__pycache__` folder

## Windows-Specific Issues

### ❌ "Access denied" errors

**Solution**:
- Run terminal as Administrator (for system operations)
- Check Windows Defender isn't blocking
- Verify workspace folder permissions

### ❌ Path issues with backslashes

**Solution**:
- Python handles both `/` and `\\` in paths
- Use forward slashes or raw strings: `r"C:\path\to\file"`

## Linux/Mac-Specific Issues

### ❌ Permission denied on scripts

**Solution**:
```bash
# Make scripts executable
chmod +x script.py

# Or run with python directly
python script.py
```

### ❌ "python: command not found"

**Solution**:
```bash
# Use python3 instead
python3 agent.py

# Or create an alias
alias python=python3
```

## Still Having Issues?

If you're still experiencing problems:

1. **Run the setup verification**:
   ```bash
   python test_setup.py
   ```

2. **Check versions**:
   ```bash
   python --version  # Should be 3.8+
   ollama --version
   pip list | grep langchain
   ```

3. **Review logs**:
   - Look for error messages in terminal output
   - Check Ollama logs: `ollama logs`

4. **Minimal reproduction**:
   - Try a simple command: "What is 2+2?"
   - If this works, the issue is task-specific

5. **Clean reinstall**:
   ```bash
   # Remove virtual environment
   rm -rf venv  # or 'rmdir /s venv' on Windows
   
   # Create fresh environment
   python -m venv venv
   source venv/bin/activate  # or 'venv\Scripts\activate' on Windows
   
   # Reinstall dependencies
   pip install -r requirements.txt
   ```

## Debug Mode

For detailed debugging information:

1. Enable verbose mode in `agent.py` (already enabled):
   ```python
   AgentExecutor(verbose=True, ...)
   ```

2. Add print statements to track execution:
   ```python
   print(f"Debug: {variable}")
   ```

3. Check tool outputs:
   - Each tool returns detailed error messages
   - Read them carefully for clues

## Getting Help

If nothing works:
1. Check the GitHub issues (if project is on GitHub)
2. Verify you followed all setup steps in QUICKSTART.md
3. Make sure your hardware meets requirements (8GB+ RAM recommended)

## System Requirements Reminder

**Minimum**:
- Python 3.8+
- 8GB RAM
- 10GB disk space
- Internet connection (for web tools)

**Recommended**:
- Python 3.10+
- 16GB RAM
- GPU with 4GB+ VRAM (for faster inference)
- SSD storage

Remember: The model runs locally, so performance depends on your hardware!
