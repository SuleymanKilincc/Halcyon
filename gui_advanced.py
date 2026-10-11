"""
Halcyon AI Agent - Advanced GUI Interface with Session Management
Iron Man / Stark Industries inspired desktop interface with:
- Sidebar for chat session management
- Database-backed conversation history
- Hardware monitoring
- Voice capabilities
"""

import customtkinter as ctk
import threading
import queue
import time
import math
from typing import Optional, List
import speech_recognition as sr
import pyttsx3
from langdetect import detect, LangDetectException
from datetime import datetime

from agent import HalcyonAgent
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
    'bg_sidebar': '#0f1428',         # Sidebar background
    'accent_cyan': '#00d9ff',        # Neon cyan (Arc Reactor)
    'accent_blue': '#0080ff',        # Electric blue
    'text_primary': '#e0f7ff',       # Light cyan text
    'text_secondary': '#8ab4c9',     # Muted cyan
    'success': '#00ff88',            # Success green
    'warning': '#ffaa00',            # Warning orange
    'error': '#ff3366',              # Error red
    'glow': '#00ffff',               # Glow effect
    'hover': '#1a2a4a',              # Hover effect
}

# Window Configuration
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
WINDOW_TITLE = "J.A.R.V.I.S - Just A Rather Very Intelligent System"

# Layout
SIDEBAR_WIDTH = 250


# Animation Settings
WAVEFORM_BARS = 20
ANIMATION_SPEED = 0.05

# ============================================================================
# AUDIO WAVEFORM WIDGET
# ============================================================================

class AudioWaveform(ctk.CTkCanvas):
    """Animated audio waveform / Arc Reactor visualization."""
    
    def __init__(self, parent, width=800, height=80, **kwargs):
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
