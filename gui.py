"""
Jarvis AI Agent - Futuristic GUI Interface
Iron Man / Stark Industries inspired desktop interface with voice capabilities
"""

import customtkinter as ctk
import threading
import queue
import subprocess
import time
import math
from typing import Optional
import speech_recognition as sr
import pyttsx3
from langdetect import detect, LangDetectException

from agent import JarvisAgent
import config
from database import db_manager

# ============================================================================
# GUI CONFIGURATION
# ============================================================================

# Color Scheme - Stark Industries / Arc Reactor Theme
COLORS = {
    'bg_dark': '#0a0e27',           # Deep space blue
    'bg_medium': '#1a1f3a',          # Medium dark blue
    'bg_light': '#252b4a',           # Lighter blue panel
    'accent_cyan': '#00d9ff',        # Neon cyan (Arc Reactor)
    'accent_blue': '#0080ff',        # Electric blue
    'text_primary': '#e0f7ff',       # Light cyan text
    'text_secondary': '#8ab4c9',     # Muted cyan
    'success': '#00ff88',            # Success green
    'warning': '#ffaa00',            # Warning orange
    'error': '#ff3366',              # Error red
    'glow': '#00ffff',               # Glow effect
}

# Window Configuration
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
WINDOW_TITLE = "J.A.R.V.I.S - Just A Rather Very Intelligent System"

# Sidebar Configuration
SIDEBAR_WIDTH = 280

# Animation Settings
WAVEFORM_BARS = 20
ANIMATION_SPEED = 0.05

# ============================================================================
# AUDIO WAVEFORM WIDGET
# ============================================================================

class AudioWaveform(ctk.CTkCanvas):
    """Animated audio waveform / Arc Reactor visualization."""
    
    def __init__(self, parent, width=800, height=100, **kwargs):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=COLORS['bg_dark'],
            highlightthickness=0,
            **kwargs
        )
        
        self.width = width
        self.height = height
        self.bars = []
        self.is_active = False
        self.animation_thread = None
        self.running = False
        
        # Initialize bars
        self.bar_width = width // WAVEFORM_BARS
        for i in range(WAVEFORM_BARS):
            x = i * self.bar_width + self.bar_width // 2
            bar = self.create_rectangle(
                x - 3, self.height // 2,
                x + 3, self.height // 2,
                fill=COLORS['accent_cyan'],
                outline=COLORS['glow']
            )
            self.bars.append(bar)
    
    def start_animation(self):
        """Start the waveform animation."""
        if not self.running:
            self.running = True
            self.is_active = True
            self.animation_thread = threading.Thread(target=self._animate, daemon=True)
            self.animation_thread.start()
    
    def stop_animation(self):
        """Stop the waveform animation."""
        self.is_active = False
        self.running = False
        self._reset_bars()
    
    def _animate(self):
        """Animation loop for the waveform."""
        phase = 0
        while self.running:
            if self.is_active:
                for i, bar in enumerate(self.bars):
                    # Calculate wave height
                    wave = math.sin(phase + i * 0.5) * 0.5 + 0.5
                    height = int(wave * (self.height * 0.4)) + 5
                    
                    # Update bar
                    x = i * self.bar_width + self.bar_width // 2
                    y1 = (self.height // 2) - height
                    y2 = (self.height // 2) + height
                    
                    self.coords(bar, x - 3, y1, x + 3, y2)
                    
                    # Color gradient based on height
                    intensity = int(wave * 255)
                    color = f'#{intensity:02x}{255:02x}{255:02x}'
                    self.itemconfig(bar, fill=color)
                
                phase += 0.2
            
            time.sleep(ANIMATION_SPEED)
    
    def _reset_bars(self):
        """Reset all bars to neutral position."""
        for i, bar in enumerate(self.bars):
            x = i * self.bar_width + self.bar_width // 2
            self.coords(bar, x - 3, self.height // 2 - 2, x + 3, self.height // 2 + 2)
            self.itemconfig(bar, fill=COLORS['accent_blue'])

# ============================================================================
# APPROVAL DIALOG
# ============================================================================

class ApprovalDialog(ctk.CTkToplevel):
    """Custom approval dialog with Iron Man theme."""
    
    def __init__(self, parent, operation: str, details: str):
        super().__init__(parent)
        
        self.result = None
        self.operation = operation
        self.details = details
        
        # Window setup
        self.title("⚠️ Approval Required")
        self.geometry("600x400")
        self.resizable(False, False)
        
        # Make it modal
        self.transient(parent)
        self.grab_set()
        
        # Configure colors
        self.configure(fg_color=COLORS['bg_dark'])
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (600 // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (400 // 2)
        self.geometry(f"600x400+{x}+{y}")
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create dialog widgets."""
        # Main container
        main_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS['bg_dark']
        )
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Warning icon and title
        header_frame = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        header_frame.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            header_frame,
            text="⚠️ SECURITY APPROVAL REQUIRED ⚠️",
            font=("Courier New", 18, "bold"),
            text_color=COLORS['warning']
        )
        title.pack(pady=15)
        
        # Operation info
        info_frame = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        info_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Operation label
        op_label = ctk.CTkLabel(
            info_frame,
            text="OPERATION:",
            font=("Courier New", 12, "bold"),
            text_color=COLORS['accent_cyan'],
            anchor="w"
        )
        op_label.pack(fill="x", padx=15, pady=(15, 5))
        
        # Operation value
        op_value = ctk.CTkLabel(
            info_frame,
            text=self.operation,
            font=("Courier New", 14),
            text_color=COLORS['text_primary'],
            anchor="w",
            wraplength=550
        )
        op_value.pack(fill="x", padx=15, pady=(0, 10))
        
        # Details label
        details_label = ctk.CTkLabel(
            info_frame,
            text="DETAILS:",
            font=("Courier New", 12, "bold"),
            text_color=COLORS['accent_cyan'],
            anchor="w"
        )
        details_label.pack(fill="x", padx=15, pady=(10, 5))
        
        # Details text box
        details_box = ctk.CTkTextbox(
            info_frame,
            font=("Consolas", 11),
            fg_color=COLORS['bg_dark'],
            text_color=COLORS['text_primary'],
            corner_radius=8,
            height=120,
            wrap="word"
        )
        details_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        details_box.insert("1.0", self.details)
        details_box.configure(state="disabled")
        
        # Warning message
        warning_msg = ctk.CTkLabel(
            main_frame,
            text="⚡ This operation requires your explicit approval ⚡",
            font=("Courier New", 10),
            text_color=COLORS['text_secondary']
        )
        warning_msg.pack(pady=(0, 15))
        
        # Buttons frame
        button_frame = ctk.CTkFrame(
            main_frame,
            fg_color="transparent"
        )
        button_frame.pack(fill="x")
        
        # Decline button (left)
        decline_btn = ctk.CTkButton(
            button_frame,
            text="❌ DECLINE",
            command=self._on_decline,
            font=("Courier New", 14, "bold"),
            fg_color=COLORS['error'],
            hover_color="#cc2244",
            corner_radius=8,
            height=50,
            width=250
        )
        decline_btn.pack(side="left", padx=5)
        
        # Approve button (right)
        approve_btn = ctk.CTkButton(
            button_frame,
            text="✅ APPROVE",
            command=self._on_approve,
            font=("Courier New", 14, "bold"),
            fg_color=COLORS['success'],
            hover_color="#00cc70",
            corner_radius=8,
            height=50,
            width=250
        )
        approve_btn.pack(side="right", padx=5)
        
        # Bind keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_approve())
        self.bind("<Escape>", lambda e: self._on_decline())
        self.bind("<y>", lambda e: self._on_approve())
        self.bind("<Y>", lambda e: self._on_approve())
        self.bind("<n>", lambda e: self._on_decline())
        self.bind("<N>", lambda e: self._on_decline())
    
    def _on_approve(self):
        """Handle approve button."""
        self.result = True
        self.grab_release()
        self.destroy()
    
    def _on_decline(self):
        """Handle decline button."""
        self.result = False
        self.grab_release()
        self.destroy()
    
    def get_result(self) -> bool:
        """
        Wait for user decision and return result.
        
        Returns:
            True if approved, False if declined
        """
        self.wait_window()
        return self.result if self.result is not None else False

# ============================================================================
# MAIN GUI APPLICATION
# ============================================================================

class JarvisGUI:
    """Main GUI application for Jarvis AI Agent."""
    
    def __init__(self):
        # Initialize agent
        self.agent = None
        self.agent_ready = False
        
        # Voice components
        self.recognizer = sr.Recognizer()
        self.tts_engine = None
        self.microphone = None
        
        # Multi-language voice lists
        self.turkish_voices = []
        self.english_voices = []
        
        # Threading
        self.response_queue = queue.Queue()
        self.approval_queue = queue.Queue()  # For thread-safe approval
        self.is_listening = False
        self.is_speaking = False
        
        # Session management
        self.current_session_id = None
        self.session_list = []
        
        # Voice configuration
        self.use_whisper_stt = False  # Set to True to use local Whisper
        self.use_advanced_tts = False  # Set to True to use advanced TTS
        
        # Setup GUI
        self._setup_window()
        self._setup_components()
        self._setup_tts()
        
        # Register approval callback
        self._register_approval_callback()
        
        # Initialize agent in background
        self._initialize_agent()
        
        # Load sessions
        self._load_sessions()
    
    def _setup_window(self):
        """Setup main window."""
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Create window
        self.root = ctk.CTk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(fg_color=COLORS['bg_dark'])
        
        # Center window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (WINDOW_WIDTH // 2)
        y = (self.root.winfo_screenheight() // 2) - (WINDOW_HEIGHT // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
    
    def _setup_components(self):
        """Setup all GUI components."""
        # Main container with sidebar
        self.main_container = ctk.CTkFrame(
            self.root,
            fg_color=COLORS['bg_dark']
        )
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Sidebar
        self._create_sidebar()
        
        # Main content area
        self.main_frame = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS['bg_dark']
        )
        self.main_frame.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=0)
        
        # Header
        self._create_header()
        
        # Status indicator
        self._create_status()
        
        # Audio waveform
        self._create_waveform()
        
        # Chat display
        self._create_chat_display()
        
        # Input area
        self._create_input_area()
        
        # Control buttons
        self._create_controls()
    
    def _create_sidebar(self):
        """Create sidebar for chat session management."""
        # Sidebar frame
        self.sidebar = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS['bg_medium'],
            corner_radius=10,
            width=SIDEBAR_WIDTH
        )
        self.sidebar.pack(side="left", fill="y", padx=(0, 10), pady=0)
        self.sidebar.pack_propagate(False)
        
        # Sidebar header
        sidebar_header = ctk.CTkFrame(
            self.sidebar,
            fg_color=COLORS['bg_light'],
            corner_radius=8
        )
        sidebar_header.pack(fill="x", padx=10, pady=(10, 10))
        
        # Title
        title = ctk.CTkLabel(
            sidebar_header,
            text="💬 CHAT SESSIONS",
            font=("Courier New", 14, "bold"),
            text_color=COLORS['accent_cyan']
        )
        title.pack(pady=10)
        
        # New chat button
        new_chat_btn = ctk.CTkButton(
            sidebar_header,
            text="➕ NEW CHAT",
            command=self._create_new_session,
            font=("Courier New", 12, "bold"),
            fg_color=COLORS['success'],
            hover_color="#00cc70",
            corner_radius=6,
            height=35
        )
        new_chat_btn.pack(fill="x", padx=10, pady=(0, 10))
        
        # Session list scrollable frame
        self.sessions_frame = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color=COLORS['bg_medium'],
            corner_radius=8,
            label_text=""
        )
        self.sessions_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Hardware monitoring section
        hardware_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color=COLORS['bg_light'],
            corner_radius=8
        )
        hardware_frame.pack(fill="x", padx=10, pady=(10, 10))
        
        hw_title = ctk.CTkLabel(
            hardware_frame,
            text="🖥️ HARDWARE",
            font=("Courier New", 12, "bold"),
            text_color=COLORS['accent_cyan']
        )
        hw_title.pack(pady=(10, 5))
        
        # System stats button
        stats_btn = ctk.CTkButton(
            hardware_frame,
            text="📊 SYSTEM STATS",
            command=self._show_system_stats,
            font=("Courier New", 10),
            fg_color=COLORS['accent_blue'],
            hover_color=COLORS['accent_cyan'],
            corner_radius=6,
            height=30
        )
        stats_btn.pack(fill="x", padx=10, pady=5)
    
    def _create_header(self):
        """Create header section."""
        header_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        header_frame.pack(fill="x", pady=(0, 15))
        
        # Title
        title = ctk.CTkLabel(
            header_frame,
            text="⚡ J.A.R.V.I.S ⚡",
            font=("Orbitron", 32, "bold"),
            text_color=COLORS['accent_cyan']
        )
        title.pack(pady=15)
        
        # Subtitle
        subtitle = ctk.CTkLabel(
            header_frame,
            text="Just A Rather Very Intelligent System",
            font=("Courier New", 12),
            text_color=COLORS['text_secondary']
        )
        subtitle.pack(pady=(0, 10))
    
    def _create_status(self):
        """Create status indicator."""
        status_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        status_frame.pack(fill="x", pady=(0, 10))
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="⏳ Initializing Neural Network...",
            font=("Courier New", 11),
            text_color=COLORS['warning']
        )
        self.status_label.pack(pady=8)
    
    def _create_waveform(self):
        """Create audio waveform visualization."""
        waveform_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        waveform_frame.pack(fill="x", pady=(0, 15))
        
        # Label
        label = ctk.CTkLabel(
            waveform_frame,
            text="NEURAL ACTIVITY",
            font=("Courier New", 10),
            text_color=COLORS['text_secondary']
        )
        label.pack(pady=(10, 5))
        
        # Waveform canvas
        self.waveform = AudioWaveform(
            waveform_frame,
            width=WINDOW_WIDTH - 80,
            height=80
        )
        self.waveform.pack(pady=(0, 10))
        self.waveform.start_animation()
    
    def _create_chat_display(self):
        """Create chat display area."""
        chat_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        chat_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Label
        label = ctk.CTkLabel(
            chat_frame,
            text="CONVERSATION LOG",
            font=("Courier New", 10),
            text_color=COLORS['text_secondary']
        )
        label.pack(pady=(10, 5), anchor="w", padx=15)
        
        # Text display
        self.chat_display = ctk.CTkTextbox(
            chat_frame,
            font=("Consolas", 11),
            fg_color=COLORS['bg_dark'],
            text_color=COLORS['text_primary'],
            corner_radius=8,
            wrap="word"
        )
        self.chat_display.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Welcome message
        self._add_system_message("System initialized. Awaiting agent startup...")
    
    def _create_input_area(self):
        """Create input area."""
        input_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS['bg_medium'],
            corner_radius=10
        )
        input_frame.pack(fill="x", pady=(0, 10))
        
        # Input field
        self.input_field = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type your command or use voice input...",
            font=("Courier New", 12),
            fg_color=COLORS['bg_dark'],
            text_color=COLORS['text_primary'],
            placeholder_text_color=COLORS['text_secondary'],
            border_color=COLORS['accent_blue'],
            border_width=2,
            corner_radius=8,
            height=40
        )
        self.input_field.pack(fill="x", padx=15, pady=15)
        self.input_field.bind("<Return>", lambda e: self._send_text_message())
    
    def _create_controls(self):
        """Create control buttons."""
        control_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="transparent"
        )
        control_frame.pack(fill="x")
        
        # Voice button
        self.voice_btn = ctk.CTkButton(
            control_frame,
            text="🎤 VOICE INPUT",
            command=self._toggle_voice_input,
            font=("Courier New", 13, "bold"),
            fg_color=COLORS['accent_blue'],
            hover_color=COLORS['accent_cyan'],
            corner_radius=8,
            height=45,
            width=200
        )
        self.voice_btn.pack(side="left", padx=5)
        
        # Send button
        self.send_btn = ctk.CTkButton(
            control_frame,
            text="📤 SEND",
            command=self._send_text_message,
            font=("Courier New", 13, "bold"),
            fg_color=COLORS['success'],
            hover_color="#00cc70",
            corner_radius=8,
            height=45,
            width=150
        )
        self.send_btn.pack(side="left", padx=5)
        
        # Clear button
        self.clear_btn = ctk.CTkButton(
            control_frame,
            text="🗑️ CLEAR",
            command=self._clear_chat,
            font=("Courier New", 13, "bold"),
            fg_color=COLORS['warning'],
            hover_color="#dd9900",
            corner_radius=8,
            height=45,
            width=150
        )
        self.clear_btn.pack(side="left", padx=5)
        
        # Exit button
        self.exit_btn = ctk.CTkButton(
            control_frame,
            text="⚡ EXIT",
            command=self._exit_app,
            font=("Courier New", 13, "bold"),
            fg_color=COLORS['error'],
            hover_color="#cc2244",
            corner_radius=8,
            height=45,
            width=150
        )
        self.exit_btn.pack(side="right", padx=5)
    
    def _setup_tts(self):
        """Setup text-to-speech engine with multi-language support."""
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 175)  # Speed
            self.tts_engine.setProperty('volume', 0.9)  # Volume
            
            # Get all available voices
            voices = self.tts_engine.getProperty('voices')
            
            # Categorize voices by language
            self.turkish_voices = []
            self.english_voices = []
            
            for voice in voices:
                voice_name = voice.name.lower()
                voice_id = voice.id.lower()
                
                # Turkish voice detection
                if any(keyword in voice_name or keyword in voice_id 
                       for keyword in ['turkish', 'turk', 'tr_tr', 'tolga', 'hazel']):
                    self.turkish_voices.append(voice)
                
                # English voice detection
                elif any(keyword in voice_name or keyword in voice_id 
                         for keyword in ['english', 'en_us', 'en_gb', 'david', 'zira', 'mark']):
                    self.english_voices.append(voice)
                
                # Fallback: male voices as general English
                elif 'male' in voice_name and 'female' not in voice_name:
                    self.english_voices.append(voice)
            
            # Set default voice (English)
            if self.english_voices:
                self.tts_engine.setProperty('voice', self.english_voices[0].id)
                self._add_system_message(f"✓ TTS initialized: {len(self.turkish_voices)} Turkish, {len(self.english_voices)} English voices")
            else:
                self._add_system_message("⚠️ TTS initialized but no English voices found")
            
            # Log available voices for debugging
            print("\n=== Available TTS Voices ===")
            print(f"Turkish voices: {len(self.turkish_voices)}")
            for v in self.turkish_voices:
                print(f"  - {v.name} ({v.id})")
            print(f"English voices: {len(self.english_voices)}")
            for v in self.english_voices:
                print(f"  - {v.name} ({v.id})")
            print("===========================\n")
            
        except Exception as e:
            self._add_system_message(f"⚠️ TTS initialization warning: {str(e)}")
            self.tts_engine = None
    
    def _initialize_agent(self):
        """Initialize Jarvis agent in background."""
        def init():
            try:
                self.agent = JarvisAgent()
                self.agent_ready = True
                self.root.after(0, self._on_agent_ready)
            except Exception as e:
                self.root.after(0, lambda: self._on_agent_error(str(e)))
        
        thread = threading.Thread(target=init, daemon=True)
        thread.start()
    
    def _register_approval_callback(self):
        """Register GUI approval callback with config."""
        config.set_approval_callback(self._approval_callback)
    
    def _approval_callback(self, operation: str, details: str) -> bool:
        """
        Approval callback called from agent threads.
        Uses queue to safely communicate with GUI thread.
        
        Args:
            operation: Operation name
            details: Operation details
            
        Returns:
            True if approved, False if declined
        """
        # Pause waveform during approval
        self.waveform.stop_animation()
        
        # Add system message
        self.root.after(0, lambda: self._add_system_message(
            f"⚠️ Approval required: {operation}"
        ))
        
        # Create a result container
        result_container = {'result': None, 'ready': False}
        
        # Request approval on GUI thread
        def show_approval_dialog():
            try:
                dialog = ApprovalDialog(self.root, operation, details)
                result_container['result'] = dialog.get_result()
                result_container['ready'] = True
                
                # Log result
                if result_container['result']:
                    self._add_system_message(f"✅ Approved: {operation}")
                else:
                    self._add_system_message(f"❌ Declined: {operation}")
                
            except Exception as e:
                print(f"Approval dialog error: {e}")
                result_container['result'] = False
                result_container['ready'] = True
        
        # Schedule on GUI thread
        self.root.after(0, show_approval_dialog)
        
        # Wait for result (with timeout)
        timeout = 300  # 5 minutes
        start_time = time.time()
        while not result_container['ready']:
            time.sleep(0.1)
            if time.time() - start_time > timeout:
                print("Approval timeout - declining by default")
                self.root.after(0, lambda: self._add_system_message(
                    "⚠️ Approval timeout - operation declined"
                ))
                return False
        
        # Resume waveform if approved
        if result_container['result']:
            self.waveform.start_animation()
        
        return result_container['result']
    
    def _on_agent_ready(self):
        """Called when agent is ready."""
        self.status_label.configure(
            text="✅ Neural Network Online | Voice Recognition Active",
            text_color=COLORS['success']
        )
        self._add_system_message("J.A.R.V.I.S is online and ready for commands, sir.")
        self._speak("Jarvis online. All systems operational.")
    
    def _on_agent_error(self, error: str):
        """Called when agent initialization fails."""
        self.status_label.configure(
            text=f"❌ Neural Network Error: {error}",
            text_color=COLORS['error']
        )
        self._add_system_message(f"⚠️ Error: {error}")
    
    # ========================================================================
    # MESSAGE HANDLING
    # ========================================================================
    
    def _add_system_message(self, message: str):
        """Add system message to chat."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"\n[SYSTEM] {message}\n", "system")
        self.chat_display.tag_config("system", foreground=COLORS['text_secondary'])
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")
    
    def _add_user_message(self, message: str):
        """Add user message to chat."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"\n[YOU] {message}\n", "user")
        self.chat_display.tag_config("user", foreground=COLORS['accent_cyan'])
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")
        # Save to database
        self._save_message_to_session("user", message)
    
    def _add_jarvis_message(self, message: str):
        """Add Jarvis message to chat."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"\n[JARVIS] {message}\n", "jarvis")
        self.chat_display.tag_config("jarvis", foreground=COLORS['success'])
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")
        # Save to database
        self._save_message_to_session("assistant", message)
    
    # ========================================================================
    # TEXT INPUT
    # ========================================================================
    
    def _send_text_message(self):
        """Send text message to agent."""
        if not self.agent_ready:
            self._add_system_message("⚠️ Please wait for agent to initialize.")
            return
        
        message = self.input_field.get().strip()
        if not message:
            return
        
        self.input_field.delete(0, "end")
        self._add_user_message(message)
        self._process_message(message)
    
    # ========================================================================
    # VOICE INPUT (STT)
    # ========================================================================
    
    def _toggle_voice_input(self):
        """Toggle voice input listening."""
        if self.is_listening:
            self.is_listening = False
            self.voice_btn.configure(
                text="🎤 VOICE INPUT",
                fg_color=COLORS['accent_blue']
            )
        else:
            self._start_voice_input()
    
    def _start_voice_input(self):
        """Start listening for voice input."""
        if not self.agent_ready:
            self._add_system_message("⚠️ Please wait for agent to initialize.")
            return
        
        self.is_listening = True
        self.voice_btn.configure(
            text="🔴 LISTENING...",
            fg_color=COLORS['error']
        )
        self._add_system_message("🎤 Listening... Speak now.")
        
        thread = threading.Thread(target=self._listen_for_voice, daemon=True)
        thread.start()
    
    def _listen_for_voice(self):
        """Listen for voice input."""
        try:
            with sr.Microphone() as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                # Recognize
                self.root.after(0, lambda: self._add_system_message("🔄 Processing speech..."))
                
                # Use Whisper or Google based on configuration
                if self.use_whisper_stt:
                    text = self._recognize_with_whisper(audio)
                else:
                    text = self.recognizer.recognize_google(audio)
                
                # Process
                self.root.after(0, lambda: self._on_voice_recognized(text))
                
        except sr.WaitTimeoutError:
            self.root.after(0, lambda: self._add_system_message("⚠️ No speech detected. Timeout."))
            self.root.after(0, self._stop_voice_input)
        except sr.UnknownValueError:
            self.root.after(0, lambda: self._add_system_message("⚠️ Could not understand audio."))
            self.root.after(0, self._stop_voice_input)
        except Exception as e:
            self.root.after(0, lambda: self._add_system_message(f"❌ Voice error: {str(e)}"))
            self.root.after(0, self._stop_voice_input)
    
    def _recognize_with_whisper(self, audio):
        """
        Recognize speech using local Whisper model.
        
        This is a hook for local Whisper STT. To enable:
        1. Install: pip install openai-whisper torch
        2. Set self.use_whisper_stt = True in __init__
        3. This will use local Whisper instead of Google Speech Recognition
        
        Args:
            audio: Audio data from speech_recognition
            
        Returns:
            Recognized text string
        """
        try:
            import whisper
            
            # Convert audio to WAV format for Whisper
            import io
            import wave
            
            # Get audio data
            wav_data = audio.get_wav_data()
            
            # Load Whisper model (use 'base' for speed, 'small'/'medium' for accuracy)
            model = whisper.load_model("base")
            
            # Save audio to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(wav_data)
                temp_path = temp_file.name
            
            # Transcribe
            result = model.transcribe(temp_path)
            text = result["text"].strip()
            
            # Clean up temp file
            import os
            os.unlink(temp_path)
            
            return text
            
        except ImportError:
            self._add_system_message("⚠️ Whisper not installed. Falling back to Google Speech Recognition.")
            self.use_whisper_stt = False
            return self.recognizer.recognize_google(audio)
        except Exception as e:
            print(f"Whisper error: {e}")
            self._add_system_message("⚠️ Whisper error. Falling back to Google Speech Recognition.")
            self.use_whisper_stt = False
            return self.recognizer.recognize_google(audio)
    
    def _on_voice_recognized(self, text: str):
        """Called when voice is recognized."""
        self._stop_voice_input()
        self._add_user_message(f"🎤 {text}")
        self._process_message(text)
    
    def _stop_voice_input(self):
        """Stop voice input."""
        self.is_listening = False
        self.voice_btn.configure(
            text="🎤 VOICE INPUT",
            fg_color=COLORS['accent_blue']
        )
    
    # ========================================================================
    # MESSAGE PROCESSING
    # ========================================================================
    
    def _process_message(self, message: str):
        """Process message with agent."""
        self.waveform.start_animation()
        self._add_system_message("⚙️ Neural processing active...")
        
        def process():
            try:
                response = self.agent.chat(message)
                self.root.after(0, lambda: self._on_response_received(response))
            except Exception as e:
                self.root.after(0, lambda: self._on_response_error(str(e)))
        
        thread = threading.Thread(target=process, daemon=True)
        thread.start()
    
    def _on_response_received(self, response: str):
        """Called when response is received."""
        self.waveform.stop_animation()
        self._add_jarvis_message(response)
        self._speak(response)
    
    def _on_response_error(self, error: str):
        """Called when response has error."""
        self.waveform.stop_animation()
        self._add_system_message(f"❌ Error: {error}")
    
    # ========================================================================
    # VOICE OUTPUT (TTS)
    # ========================================================================
    
    def _detect_language(self, text: str) -> str:
        """
        Detect the language of the text.
        
        Args:
            text: Text to analyze
            
        Returns:
            'tr' for Turkish, 'en' for English, 'en' as default
        """
        try:
            # Remove common system messages and formatting
            clean_text = text.replace('[SYSTEM]', '').replace('[JARVIS]', '').replace('[YOU]', '')
            clean_text = clean_text.replace('✓', '').replace('⚠️', '').replace('❌', '')
            clean_text = clean_text.strip()
            
            # Skip if text is too short
            if len(clean_text) < 10:
                return 'en'
            
            # Detect language using langdetect
            detected = detect(clean_text)
            
            # Map language codes
            if detected == 'tr':
                return 'tr'
            else:
                return 'en'
                
        except LangDetectException:
            # If detection fails, use simple heuristic
            return self._simple_language_check(text)
        except Exception as e:
            print(f"Language detection error: {e}")
            return 'en'
    
    def _simple_language_check(self, text: str) -> str:
        """
        Simple regex-based language detection as fallback.
        
        Args:
            text: Text to analyze
            
        Returns:
            'tr' for Turkish, 'en' for English
        """
        # Turkish-specific characters
        turkish_chars = ['ş', 'ğ', 'ı', 'ö', 'ü', 'ç', 'Ş', 'Ğ', 'İ', 'Ö', 'Ü', 'Ç']
        
        # Count Turkish characters
        turkish_count = sum(1 for char in text if char in turkish_chars)
        
        # Common Turkish words
        turkish_words = ['bir', 've', 'için', 'bu', 'ile', 'var', 'gibi', 'olan', 
                        'değil', 'da', 'de', 'mi', 'mı', 'mu', 'mü']
        text_lower = text.lower()
        turkish_word_count = sum(1 for word in turkish_words if word in text_lower)
        
        # If we find Turkish indicators, classify as Turkish
        if turkish_count > 0 or turkish_word_count >= 2:
            return 'tr'
        
        return 'en'
    
    def _select_voice_for_language(self, language: str) -> bool:
        """
        Select appropriate voice for the detected language.
        
        Args:
            language: 'tr' for Turkish, 'en' for English
            
        Returns:
            True if voice was changed, False otherwise
        """
        if not self.tts_engine:
            return False
        
        try:
            if language == 'tr' and self.turkish_voices:
                # Use Turkish voice
                self.tts_engine.setProperty('voice', self.turkish_voices[0].id)
                print(f"🔊 Voice: Turkish ({self.turkish_voices[0].name})")
                return True
            elif language == 'en' and self.english_voices:
                # Use English voice
                self.tts_engine.setProperty('voice', self.english_voices[0].id)
                print(f"🔊 Voice: English ({self.english_voices[0].name})")
                return True
            else:
                print(f"⚠️ No voice available for language: {language}")
                return False
        except Exception as e:
            print(f"Voice selection error: {e}")
            return False
    
    def _speak(self, text: str):
        """
        Speak text using TTS with automatic language detection and voice switching.
        
        Args:
            text: Text to speak
        """
        if not self.tts_engine:
            return
        
        def speak():
            try:
                self.is_speaking = True
                
                # Detect language
                language = self._detect_language(text)
                print(f"🌍 Detected language: {'Turkish' if language == 'tr' else 'English'}")
                
                # Use advanced TTS or pyttsx3 based on configuration
                if self.use_advanced_tts:
                    self._speak_with_advanced_tts(text, language)
                else:
                    # Switch voice based on language
                    self._select_voice_for_language(language)
                    # Speak the text
                    self.tts_engine.say(text)
                    self.tts_engine.runAndWait()
                
                self.is_speaking = False
                
            except Exception as e:
                print(f"TTS Error: {e}")
                self.is_speaking = False
        
        # Run in separate thread (non-blocking)
        thread = threading.Thread(target=speak, daemon=True)
        thread.start()
    
    def _speak_with_advanced_tts(self, text: str, language: str):
        """
        Speak text using advanced TTS engine (Coqui TTS or similar).
        
        This is a hook for better TTS engines. To enable:
        1. Install: pip install TTS torch
        2. Set self.use_advanced_tts = True in __init__
        3. This will use Coqui TTS instead of pyttsx3
        
        Args:
            text: Text to speak
            language: Language code ('tr' or 'en')
        """
        try:
            from TTS.api import TTS
            import tempfile
            import os
            
            # Map language to TTS model
            if language == 'tr':
                # Turkish TTS model (example - adjust based on available models)
                model_name = "tts_models/tr/common-voice/glow-tts"
            else:
                # English TTS model
                model_name = "tts_models/en/ljspeech/glow-tts"
            
            # Initialize TTS
            tts = TTS(model_name=model_name, progress_bar=False, gpu=False)
            
            # Generate speech to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            
            tts.tts_to_file(text=text, file_path=temp_path)
            
            # Play audio using pygame or similar
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
            except ImportError:
                # Fallback: use system default player
                import platform
                if platform.system() == "Windows":
                    os.startfile(temp_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["afplay", temp_path], check=False)
                else:
                    subprocess.run(["aplay", temp_path], check=False)
            
            # Clean up temp file
            os.unlink(temp_path)
            
        except ImportError:
            self._add_system_message("⚠️ Advanced TTS not installed. Falling back to pyttsx3.")
            self.use_advanced_tts = False
            # Fallback to pyttsx3
            self._select_voice_for_language(language)
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
        except Exception as e:
            print(f"Advanced TTS error: {e}")
            self._add_system_message("⚠️ Advanced TTS error. Falling back to pyttsx3.")
            self.use_advanced_tts = False
            # Fallback to pyttsx3
            self._select_voice_for_language(language)
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
    
    # ========================================================================
    # UTILITY FUNCTIONS
    # ========================================================================
    
    def _clear_chat(self):
        """Clear chat display."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        if self.agent:
            self.agent.reset_memory()
        self._add_system_message("Conversation log cleared.")
    
    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================
    
    def _load_sessions(self):
        """Load all chat sessions from database."""
        try:
            sessions = db_manager.get_all_sessions(pinned_first=True)
            self.session_list = sessions
            self._refresh_session_list()
            
            # Create default session if none exist
            if not sessions:
                self._create_new_session()
            else:
                # Load most recent session
                self._load_session(sessions[0].id)
                
        except Exception as e:
            self._add_system_message(f"⚠️ Error loading sessions: {str(e)}")
    
    def _refresh_session_list(self):
        """Refresh the session list in sidebar."""
        # Clear existing widgets
        for widget in self.sessions_frame.winfo_children():
            widget.destroy()
        
        # Add session items
        for session in self.session_list:
            self._create_session_item(session)
    
    def _create_session_item(self, session):
        """Create a session item widget."""
        # Session frame
        session_frame = ctk.CTkFrame(
            self.sessions_frame,
            fg_color=COLORS['bg_light'] if session.id == self.current_session_id else COLORS['bg_medium'],
            corner_radius=6
        )
        session_frame.pack(fill="x", pady=5)
        
        # Title label
        title_label = ctk.CTkLabel(
            session_frame,
            text=session.title[:25] + "..." if len(session.title) > 25 else session.title,
            font=("Courier New", 10, "bold" if session.id == self.current_session_id else "normal"),
            text_color=COLORS['accent_cyan'] if session.id == self.current_session_id else COLORS['text_primary'],
            anchor="w"
        )
        title_label.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        
        # Pin button
        pin_btn = ctk.CTkButton(
            session_frame,
            text="📌" if session.is_pinned else "○",
            command=lambda s=session: self._toggle_session_pin(s.id),
            width=25,
            height=25,
            fg_color=COLORS['warning'] if session.is_pinned else COLORS['text_secondary'],
            hover_color=COLORS['accent_cyan'],
            corner_radius=4,
            text_color="black"
        )
        pin_btn.pack(side="right", padx=2)
        
        # Delete button
        delete_btn = ctk.CTkButton(
            session_frame,
            text="🗑️",
            command=lambda s=session: self._delete_session(s.id),
            width=25,
            height=25,
            fg_color=COLORS['error'],
            hover_color="#cc2244",
            corner_radius=4
        )
        delete_btn.pack(side="right", padx=2)
        
        # Click to load session
        session_frame.bind("<Button-1>", lambda e, s=session: self._load_session(s.id))
        title_label.bind("<Button-1>", lambda e, s=session: self._load_session(s.id))
    
    def _create_new_session(self):
        """Create a new chat session."""
        try:
            session = db_manager.create_session()
            self.session_list.insert(0, session)
            self._refresh_session_list()
            self._load_session(session.id)
            self._add_system_message(f"✓ New session created: {session.title}")
        except Exception as e:
            self._add_system_message(f"⚠️ Error creating session: {str(e)}")
    
    def _load_session(self, session_id):
        """Load a chat session."""
        try:
            self.current_session_id = session_id
            session = db_manager.get_session(session_id)
            
            if session:
                # Clear chat display
                self.chat_display.configure(state="normal")
                self.chat_display.delete("1.0", "end")
                self.chat_display.configure(state="disabled")
                
                # Load messages directly to display without saving to database
                self.chat_display.configure(state="normal")
                for msg in session.messages:
                    if msg.role == "user":
                        self.chat_display.insert("end", f"\n[YOU] {msg.content}\n", "user")
                    elif msg.role == "assistant":
                        self.chat_display.insert("end", f"\n[JARVIS] {msg.content}\n", "jarvis")
                    elif msg.role == "system":
                        self.chat_display.insert("end", f"\n[SYSTEM] {msg.content}\n", "system")
                
                # Configure tags and scroll
                self.chat_display.tag_config("user", foreground=COLORS['accent_cyan'])
                self.chat_display.tag_config("jarvis", foreground=COLORS['success'])
                self.chat_display.tag_config("system", foreground=COLORS['text_secondary'])
                self.chat_display.see("end")
                self.chat_display.configure(state="disabled")
                
                # Update agent memory
                if self.agent:
                    self.agent.load_session_history(session_id)
                
                # Refresh sidebar to show active session
                self._refresh_session_list()
                
                self._add_system_message(f"✓ Loaded session: {session.title}")
                
        except Exception as e:
            self._add_system_message(f"⚠️ Error loading session: {str(e)}")
    
    def _toggle_session_pin(self, session_id):
        """Toggle session pin status."""
        try:
            new_status = db_manager.toggle_session_pin(session_id)
            self.session_list = db_manager.get_all_sessions(pinned_first=True)
            self._refresh_session_list()
            self._add_system_message(f"✓ Session {'pinned' if new_status else 'unpinned'}")
        except Exception as e:
            self._add_system_message(f"⚠️ Error toggling pin: {str(e)}")
    
    def _delete_session(self, session_id):
        """Delete a chat session."""
        try:
            if session_id == self.current_session_id:
                self._add_system_message("⚠️ Cannot delete active session")
                return
            
            db_manager.delete_session(session_id)
            self.session_list = db_manager.get_all_sessions(pinned_first=True)
            self._refresh_session_list()
            self._add_system_message("✓ Session deleted")
        except Exception as e:
            self._add_system_message(f"⚠️ Error deleting session: {str(e)}")
    
    def _save_message_to_session(self, role: str, content: str):
        """Save a message to the current session."""
        if self.current_session_id:
            try:
                db_manager.add_message(self.current_session_id, role, content)
            except Exception as e:
                print(f"Error saving message: {e}")
    
    # ========================================================================
    # HARDWARE MONITORING
    # ========================================================================
    
    def _show_system_stats(self):
        """Show system hardware statistics."""
        if not self.agent_ready:
            self._add_system_message("⚠️ Please wait for agent to initialize.")
            return
        
        self._add_system_message("📊 Fetching system statistics...")
        
        def get_stats():
            try:
                # Import the raw function, not the decorated tool
                import tools
                stats = tools.get_system_stats.func()
                self.root.after(0, lambda: self._add_system_message(stats))
            except Exception as e:
                self.root.after(0, lambda: self._add_system_message(f"❌ Error: {str(e)}"))
        
        thread = threading.Thread(target=get_stats, daemon=True)
        thread.start()
    
    
    def _exit_app(self):
        """Exit application."""
        self.waveform.running = False
        if self.tts_engine:
            self.tts_engine.stop()
        self.root.quit()
        self.root.destroy()
    
    # ========================================================================
    # RUN
    # ========================================================================
    
    def run(self):
        """Run the GUI application."""
        self.root.mainloop()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    try:
        app = JarvisGUI()
        app.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
