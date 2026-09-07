# Jarvis - Local AI Agent Framework

A fully local, open-source AI Agent framework powered by Ollama and LangChain with a futuristic Iron Man-inspired GUI and voice capabilities.

## ✨ Features

### 🎨 Phase 2: Iron Man GUI (NEW!)
- 🖥️ **Futuristic Desktop Interface**: Dark Blue/Neon Cyan theme (Stark Industries inspired)
- 🎤 **Voice Input**: Speak commands naturally using speech recognition
- 🔊 **Voice Output**: Jarvis speaks responses using local text-to-speech
- 🌍 **Multi-Language TTS**: 🆕 Automatic Turkish & English detection with voice switching
- 📊 **Animated Waveform**: Visual "Arc Reactor" that pulses during AI thinking
- 💬 **Real-time Chat**: Color-coded conversation log
- 🛡️ **GUI-Based Approvals**: 🆕 Beautiful popups for all security approvals (no terminal needed!)
- ⚡ **One-Click Launch**: Easy startup with batch/shell scripts

### 🤖 Phase 1: Core Agent System
- 🧠 **Local LLM**: Runs entirely on your machine using Ollama (qwen3.5:9b)
- 🔧 **Tool Binding**: Function calling capabilities for executing complex tasks
- 🛡️ **Human-in-the-Loop**: Approval mechanism for critical operations
- 💻 **Terminal Access**: Safe command execution with built-in filters
- 📁 **File System Manager**: Read, write, and manage files in workspace
- 🌐 **Web Search & Scraping**: DuckDuckGo search and webpage parsing
- 🌍 **Web Automation**: 🆕 Playwright-based browser control for JavaScript sites
- 📥 **File Downloader**: 🆕 Download files directly from URLs
- 📦 **Archive Handler**: 🆕 Extract ZIP, TAR, 7Z files automatically

## 🚀 Quick Start

### Installation

1. **Install Ollama and pull the model:**
```bash
ollama pull qwen3.5:9b
```

2. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

3. **Verify setup:**
```bash
# For CLI
python test_setup.py

# For GUI
python setup_gui.py
```

### Launch Options

#### 🖥️ GUI Mode (Recommended)
```bash
# Windows
start_jarvis_gui.bat

# Linux/Mac
./start_jarvis_gui.sh

# Or directly
python gui.py
```

#### ⌨️ CLI Mode (Terminal)
```bash
# Windows
start_jarvis.bat

# Linux/Mac
./start_jarvis.sh

# Or directly
python agent.py
```

## 📚 Documentation

- **[GUI_GUIDE.md](GUI_GUIDE.md)** - Complete GUI usage and customization guide
- **[PHASE2_SUMMARY.md](PHASE2_SUMMARY.md)** - Phase 2 technical summary
- **[QUICKSTART.md](QUICKSTART.md)** - Detailed installation guide
- **[EXAMPLES.md](EXAMPLES.md)** - Usage examples and commands
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture details
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions

## 🎯 Usage Examples

### GUI Voice Commands
```
🎤 "List files in the workspace"
🎤 "Search the web for Python tutorials"
🎤 "Create a file called hello.py with print hello world"
🎤 "Read the contents of config.py"
```

### Text Commands (GUI or CLI)
```
Create a Python script that calculates fibonacci numbers
Search for the latest AI news and summarize
Run the command "python --version"
List all files in the current directory
```

## 🏗️ Project Structure

```
jarvis/
├── gui.py              # 🆕 Futuristic GUI interface
├── agent.py            # Main agent orchestrator
├── config.py           # Configuration and prompts
├── tools.py            # Custom tools (terminal, files, web)
├── requirements.txt    # Python dependencies
├── workspace/          # Agent's working directory
│
├── start_jarvis_gui.bat    # 🆕 GUI launcher (Windows)
├── start_jarvis_gui.sh     # 🆕 GUI launcher (Linux/Mac)
├── start_jarvis.bat        # CLI launcher (Windows)
├── start_jarvis.sh         # CLI launcher (Linux/Mac)
│
├── setup_gui.py       # 🆕 GUI setup checker
├── test_setup.py      # CLI setup checker
│
└── docs/
    ├── GUI_GUIDE.md        # 🆕 GUI documentation
    ├── PHASE2_SUMMARY.md   # 🆕 Phase 2 summary
    ├── QUICKSTART.md
    ├── EXAMPLES.md
    └── ...
```

## 🎨 GUI Screenshots

### Main Interface
- **Header**: Glowing "J.A.R.V.I.S" title with Arc Reactor styling
- **Status Bar**: Real-time system status with color indicators
- **Waveform**: 20 animated bars that pulse during AI processing
- **Chat Log**: Scrollable conversation with color-coded messages
- **Input Area**: Large text field with glowing borders
- **Controls**: Voice, Send, Clear, and Exit buttons

### Color Scheme
- Deep Space Blue background
- Neon Cyan accents (Arc Reactor glow)
- Green success messages
- Orange warnings
- Red errors

## 🔧 Capabilities

| Feature | GUI | CLI |
|---------|-----|-----|
| AI Processing | ✅ | ✅ |
| All Tools (8) | ✅ | ✅ |
| Voice Input | ✅ | ❌ |
| Voice Output | ✅ | ❌ |
| Visual Feedback | ✅ | ❌ |
| Animated Waveform | ✅ | ❌ |
| Text Input | ✅ | ✅ |

## 🛡️ Safety Features

- Multi-layer command validation
- Human approval for critical operations
- Sandboxed workspace directory
- Command blacklist (blocks dangerous operations)
- Resource limits (timeouts, file sizes)
- Path traversal prevention

## 📊 System Requirements

**Minimum**:
- Python 3.8+
- 8GB RAM
- 10GB disk space
- Microphone (for voice input)

**Recommended**:
- Python 3.10+
- 16GB RAM
- GPU with 4GB+ VRAM
- SSD storage

## 🎓 Technologies Used

- **AI**: Ollama, LangChain, LangGraph
- **GUI**: CustomTkinter, Tkinter Canvas
- **Voice**: SpeechRecognition (STT), pyttsx3 (TTS)
- **Web**: DuckDuckGo, BeautifulSoup, Requests
- **Threading**: Python threading and queues

## 📝 License

MIT License - Free and Open Source

## 🙏 Acknowledgments

- Inspired by Marvel's J.A.R.V.I.S from Iron Man
- Built with ❤️ for local AI enthusiasts
- Powered by open-source communities

## 🔮 Roadmap

### Phase 3 (Future)
- [ ] Wake word detection ("Hey Jarvis")
- [ ] System tray integration
- [ ] Global hotkey activation
- [ ] Multiple theme options
- [ ] Conversation history save/load
- [ ] Screenshot analysis (vision)
- [ ] Plugin system
- [ ] Mobile app remote control

## 📞 Support

Having issues? Check:
1. [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. [GUI_GUIDE.md](GUI_GUIDE.md) - GUI-specific help
3. Run `setup_gui.py` for diagnostics

---

**"Sir, Jarvis is at your service."** 🤖⚡
