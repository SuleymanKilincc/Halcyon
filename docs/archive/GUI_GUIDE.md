# Jarvis GUI - Iron Man Interface Guide

Welcome to Phase 2: The futuristic desktop interface for Jarvis!

## 🎨 Visual Features

### Iron Man / Stark Industries Theme
- **Color Scheme**: Dark Blue / Neon Cyan (Arc Reactor inspired)
- **Typography**: Futuristic fonts (Orbitron, Courier New)
- **Animations**: Smooth, cyberpunk-style effects
- **Layout**: Clean, modern, professional

### Interface Components

#### 1. Header Section
```
⚡ J.A.R.V.I.S ⚡
Just A Rather Very Intelligent System
```
- Prominent title with neon cyan glow effect
- Subtitle with technical styling

#### 2. Status Indicator
Shows current system status:
- ⏳ Initializing... (Orange)
- ✅ Neural Network Online (Green)
- ❌ Error State (Red)

#### 3. Audio Waveform Visualization
- **Animated bars** that pulse when Jarvis is thinking/speaking
- **Color gradients** from cyan to white based on intensity
- **Arc Reactor style** - represents neural activity
- **20 bars** animating in sine wave pattern

#### 4. Conversation Log
- **Scrollable chat display** with color-coded messages:
  - `[SYSTEM]` - Gray (system notifications)
  - `[YOU]` - Cyan (your messages)
  - `[JARVIS]` - Green (AI responses)
- Dark background for eye comfort
- Monospace font for technical feel

#### 5. Input Area
- **Text field** with placeholder text
- **Press Enter** to send
- Glowing border on focus

#### 6. Control Panel
Four main buttons:
- 🎤 **VOICE INPUT** - Blue (activate/deactivate voice)
- 📤 **SEND** - Green (send text message)
- 🗑️ **CLEAR** - Orange (clear conversation)
- ⚡ **EXIT** - Red (close application)

## 🎤 Voice Capabilities

### Speech Recognition (STT)
**Technology**: Google Speech Recognition API (via speech_recognition library)

**How to Use**:
1. Click "🎤 VOICE INPUT" button
2. Wait for "LISTENING..." status
3. Speak your command clearly
4. Jarvis will process your speech automatically

**Features**:
- Automatic ambient noise adjustment
- 5-second timeout for listening
- 10-second phrase time limit
- Real-time status updates

**Tips**:
- Speak clearly and at normal pace
- Minimize background noise
- Wait for "LISTENING..." before speaking
- Keep phrases under 10 seconds

### Text-to-Speech (TTS)
**Technology**: pyttsx3 (local, offline TTS)

**Features**:
- 🆕 **Multi-language support**: Turkish & English automatic detection
- 🆕 **Dynamic voice switching**: Changes voice based on language
- **Male voice** (when available)
- **175 WPM** speaking rate (natural pace)
- **90% volume** for clarity
- **Runs in background** - doesn't block UI

**Language Detection** 🆕:
- Automatically detects Turkish or English text
- Uses `langdetect` library with regex fallback
- Switches to appropriate system voice
- Seamless transitions between languages

**Customization**:
Edit in `gui.py`:
```python
self.tts_engine.setProperty('rate', 175)  # Speed
self.tts_engine.setProperty('volume', 0.9)  # Volume
```

**Turkish Voice Setup** (Windows):
1. Settings → Time & Language → Language
2. Add Turkish (Türkçe) language
3. Check "Text-to-speech" during install
4. Restart computer
5. Test with: `python test_multilang_tts.py`

See [MULTILANG_GUIDE.md](MULTILANG_GUIDE.md) for detailed multi-language documentation.

## 🚀 Installation & Setup

### 1. Install Dependencies

```bash
# Install all required packages
pip install -r requirements.txt
```

**New GUI Dependencies**:
- `customtkinter` - Modern GUI framework
- `pillow` - Image processing
- `SpeechRecognition` - Voice input
- `pyaudio` - Audio capture
- `pyttsx3` - Text-to-speech
- `langdetect` - 🆕 Multi-language detection

### 2. Windows-Specific Setup

**For PyAudio** (required for microphone):
```bash
# If pip install fails, download wheel from:
# https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

# Then install:
pip install PyAudio-0.2.13-cp310-cp310-win_amd64.whl
```

### 3. Verify Installation

```bash
python -c "import customtkinter, speech_recognition, pyttsx3; print('✓ All GUI dependencies installed')"
```

## 🎯 Launching the GUI

### Windows
```bash
# Easy launch
start_jarvis_gui.bat

# Or directly
python gui.py
```

### Linux/Mac
```bash
# Make executable
chmod +x start_jarvis_gui.sh

# Launch
./start_jarvis_gui.sh

# Or directly
python3 gui.py
```

## 💡 Usage Examples

### Text Input
1. Type your command in the input field
2. Press Enter or click "📤 SEND"
3. Watch the waveform animate while Jarvis thinks
4. Read and hear the response

### Voice Input
1. Click "🎤 VOICE INPUT"
2. Wait for "🔴 LISTENING..." indicator
3. Speak: "Create a Python file called hello.py"
4. Jarvis processes speech → text → command → response
5. Listen to spoken response

### Example Commands
```
"List files in the workspace"
"Search the web for Python tutorials"
"Create a file called test.txt with some content"
"What's 2 plus 2?"
"Read the contents of config.py"
```

## ⚙️ Architecture

### Component Hierarchy
```
JarvisGUI (Main Application)
├── CTkWindow (Main Window)
├── AudioWaveform (Custom Widget)
├── JarvisAgent (AI Brain - from agent.py)
├── SpeechRecognizer (STT)
└── TTS Engine (Text-to-Speech)
```

### Threading Model
- **Main Thread**: GUI event loop
- **Agent Thread**: AI processing (non-blocking)
- **Voice Thread**: Speech recognition (non-blocking)
- **TTS Thread**: Speech synthesis (non-blocking)
- **Animation Thread**: Waveform animation (continuous)

### Data Flow
```
User Input (Text/Voice)
    ↓
GUI Thread
    ↓
Agent Processing Thread
    ↓
JarvisAgent.chat()
    ↓
Response Queue
    ↓
GUI Update + TTS Output
```

## 🎨 Customization

### Change Color Scheme

Edit `COLORS` dictionary in `gui.py`:
```python
COLORS = {
    'bg_dark': '#0a0e27',        # Background
    'accent_cyan': '#00d9ff',     # Primary accent
    'accent_blue': '#0080ff',     # Secondary accent
    # ... more colors
}
```

### Adjust Window Size
```python
WINDOW_WIDTH = 1000   # Width in pixels
WINDOW_HEIGHT = 700   # Height in pixels
```

### Modify Waveform
```python
WAVEFORM_BARS = 20         # Number of bars
ANIMATION_SPEED = 0.05     # Speed (lower = faster)
```

### Change Voice Settings
```python
# In _setup_tts() method:
self.tts_engine.setProperty('rate', 175)     # Speaking speed
self.tts_engine.setProperty('volume', 0.9)   # Volume (0.0 to 1.0)
```

## 🔧 Troubleshooting

### "No module named 'customtkinter'"
```bash
pip install customtkinter
```

### "Could not find PyAudio"
**Windows**: Download wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

**Mac**: 
```bash
brew install portaudio
pip install pyaudio
```

**Linux**:
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

### "Microphone not working"
1. Check system microphone permissions
2. Verify microphone is not used by another app
3. Test with: `python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"`

### "TTS voice is robotic/wrong language"
Edit `_setup_tts()` to list and select voices:
```python
voices = self.tts_engine.getProperty('voices')
for i, voice in enumerate(voices):
    print(f"{i}: {voice.name}")
# Then set: self.tts_engine.setProperty('voice', voices[INDEX].id)
```

### "GUI is laggy"
1. Close other GPU-intensive applications
2. Reduce waveform bars: `WAVEFORM_BARS = 10`
3. Increase animation speed: `ANIMATION_SPEED = 0.1`

### "Agent initialization fails"
1. Ensure Ollama is running: `ollama list`
2. Check model is installed: `ollama pull qwen3.5:9b`
3. Review console for error messages

## 📊 Performance Notes

### Resource Usage
- **GUI**: ~50-100 MB RAM
- **Agent**: ~6-8 GB RAM (model loaded)
- **CPU**: Moderate during inference
- **GPU**: Used by Ollama for model inference

### Optimization Tips
1. Keep conversation history reasonable (use CLEAR button)
2. Close GUI when not in use to free GPU
3. Reduce waveform complexity on older machines
4. Disable TTS if not needed (comment out `_speak()` calls)

## 🎓 Advanced Features

### Keyboard Shortcuts
- **Enter**: Send message
- **Alt+F4**: Close window

### Future Enhancements (Ideas)
1. Multiple voice profiles
2. Conversation history save/load
3. Screenshot analysis (vision input)
4. Hotkey activation (wake word detection)
5. Minimize to system tray
6. Multiple themes (light mode, Matrix theme, etc.)
7. Plugin system for custom tools
8. Voice wake word ("Hey Jarvis")

## 🔐 Privacy & Security

### Local Processing
- ✅ **AI Model**: Runs locally (Ollama)
- ✅ **TTS**: Runs locally (pyttsx3)
- ⚠️ **STT**: Uses Google API (requires internet)

### Alternative for Fully Local STT
For 100% offline operation, replace Google STT with local Whisper:

```bash
pip install openai-whisper
```

Then modify `_listen_for_voice()` to use Whisper instead of `recognize_google()`.

## 📝 Notes

- GUI runs the same `JarvisAgent` from Phase 1 - all tools work identically
- Voice is an addition, not a replacement - text input still works
- Agent approval prompts work via console (approve via terminal when needed)
- Waveform is purely visual - not actual audio analysis

## 🎉 Enjoy Your Iron Man Experience!

You now have a fully functional, voice-enabled, futuristic AI assistant interface!

**Sir, Jarvis is at your service.**
