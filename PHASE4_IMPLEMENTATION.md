# Phase 4: Advanced GUI with Sessions & Hardware Monitoring

## ✅ COMPLETED COMPONENTS

### 1. Database Layer (`database.py`) ✓
- **SQLite database** with SQLAlchemy ORM
- **ChatSession model**: Stores session metadata (title, timestamps, pin status)
- **ChatMessage model**: Stores individual messages with roles
- **DatabaseManager class**: Complete CRUD operations for sessions and messages
- **Features**:
  - Create/read/update/delete sessions
  - Pin/unpin sessions (pinned appear first)
  - Add/retrieve messages
  - Export/import sessions as JSON
  - Cascade delete (deleting session removes all messages)

### 2. Hardware Monitoring Tools (`tools.py`) ✓
Added two new tools to the agent:

#### `get_system_stats()`
Comprehensive hardware monitoring for ASUS TUF laptops and Windows systems:
- **CPU**: Usage per core, frequency, temperature (via WMI)
- **GPU**: Load, memory, temperature (NVIDIA via GPUtil)
- **RAM**: Total, used, available
- **Disk**: Usage for all partitions
- **Battery**: Charge level, plugged status, time remaining
- **Network**: Bytes sent/received

#### `set_performance_profile(profile)`
Performance profile switcher for ASUS TUF:
- **Profiles**: silent, balanced, turbo
- **Methods**: 
  1. G-Helper CLI (primary, if installed)
  2. Windows power plans (fallback)
- **User approval required** before changing profiles

### 3. Updated Tool Count
- **Total tools**: 13 (was 11 in Phase 3)
- New tools integrated with approval system

---

## 🚧 REMAINING WORK

### GUI Refactoring (Priority 1)

The current `gui.py` needs significant refactoring to add session management. Here's the implementation plan:

#### Layout Changes
```
┌──────────────────────────────────────────────────────────┐
│ WINDOW (1200x800)                                        │
├────────────┬─────────────────────────────────────────────┤
│            │ Header (Title + Status)                     │
│ SIDEBAR    ├─────────────────────────────────────────────┤
│ (250px)    │ Waveform                                    │
│            ├─────────────────────────────────────────────┤
│ Sessions   │ Chat Display (messages)                     │
│ List       │                                             │
│            │                                             │
│            ├─────────────────────────────────────────────┤
│ [New Chat] │ Input Field                                 │
│            ├─────────────────────────────────────────────┤
│            │ Control Buttons                             │
└────────────┴─────────────────────────────────────────────┘
```

#### Sidebar Components
1. **New Chat Button** (top)
   - Creates new session in database
   - Switches to new empty chat

2. **Session List** (scrollable)
   - Shows all sessions (pinned first, then by date)
   - Each session item shows:
     - 📌 Pin icon (if pinned)
     - Session title
     - Last update time
     - Message count
   - Right-click context menu:
     - Rename
     - Pin/Unpin
     - Export
     - Delete

3. **Session Item Design**
```python
# Each session displayed as:
┌──────────────────────────────┐
│ 📌 Chat Title               │
│ 12 messages • 2h ago        │
└──────────────────────────────┘
```

#### Session Integration Steps

1. **Modify `JarvisGUI.__init__()`**
   - Add `self.current_session_id = None`
   - Load or create default session
   - Initialize session list

2. **Add Sidebar Frame**
```python
self.sidebar = ctk.CTkFrame(
    self.root,
    width=SIDEBAR_WIDTH,
    fg_color=COLORS['bg_sidebar']
)
self.sidebar.pack(side="left", fill="y")
```

3. **Add Session Management Methods**
   - `_create_new_session()`: Create and switch to new chat
   - `_load_session(session_id)`: Load session from database
   - `_save_message(role, content)`: Save message to current session
   - `_refresh_session_list()`: Update sidebar with all sessions
   - `_delete_session(session_id)`: Delete with confirmation
   - `_toggle_pin(session_id)`: Pin/unpin session
   - `_rename_session(session_id)`: Show rename dialog

4. **Update Message Handling**
```python
def _add_user_message(self, message: str):
    # Display in chat
    self.chat_display.insert(...)
    # Save to database
    if self.current_session_id:
        db_manager.add_message(
            self.current_session_id,
            "user",
            message
        )

def _add_jarvis_message(self, message: str):
    # Display in chat
    self.chat_display.insert(...)
    # Save to database
    if self.current_session_id:
        db_manager.add_message(
            self.current_session_id,
            "assistant",
            message
        )
```

5. **Agent Memory Integration**
```python
def _load_session(self, session_id):
    # Load from database
    messages = db_manager.get_session_messages(session_id)
    
    # Clear chat display
    self.chat_display.delete("1.0", "end")
    
    # Restore messages to display
    for msg in messages:
        if msg.role == "user":
            self._add_user_message(msg.content)
        elif msg.role == "assistant":
            self._add_jarvis_message(msg.content)
        elif msg.role == "system":
            self._add_system_message(msg.content)
    
    # Restore agent memory
    self.agent.chat_history = []
    for msg in messages:
        if msg.role == "user":
            self.agent.chat_history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            self.agent.chat_history.append(AIMessage(content=msg.content))
```

---

## 📁 FILE CHANGES SUMMARY

### Created Files
1. ✅ `database.py` - Database models and manager
2. 🚧 `gui_advanced.py` - New GUI with sidebar (started, needs completion)
3. ✅ `PHASE4_IMPLEMENTATION.md` - This file

### Modified Files
1. ✅ `tools.py` - Added hardware monitoring tools
2. ✅ `requirements.txt` - Already contains all needed dependencies
3. 🚧 `gui.py` - Needs refactoring (or use gui_advanced.py)
4. 🚧 `agent.py` - May need session_id parameter

### Files to Update
- `gui.py` → Full refactor to add sidebar and session management
- `start_jarvis_gui.bat` → Update if using gui_advanced.py
- Create test file: `test_sessions.py`

---

## 🎯 NEXT STEPS (Priority Order)

1. **Complete GUI Refactoring** (2-3 hours)
   - Finish `gui_advanced.py` with full sidebar implementation
   - Or refactor existing `gui.py` incrementally
   - Test session switching
   - Test message persistence

2. **Session Auto-Title Generation** (30 min)
   - Use first user message as session title
   - Or use AI to generate summary title
   - Limit to 50 characters

3. **Hardware Monitoring Integration** (15 min)
   - Add "System Stats" button to GUI
   - Display stats in popup window
   - Add periodic monitoring option

4. **Advanced Voice Features** (Phase 5 - Future)
   - Local Whisper STT integration
   - Better TTS (Coqui TTS or similar)
   - Voice activity detection

5. **Testing** (1 hour)
   - Test all session operations
   - Test database persistence
   - Test hardware monitoring tools
   - Test approval system with new GUI

---

## 🔧 USAGE INSTRUCTIONS

### Current State
```bash
# Phase 1-3 features work:
python start_jarvis_gui.bat

# Hardware monitoring is ready (13 tools total):
# Ask Jarvis: "Show me system stats"
# Ask Jarvis: "Set performance to turbo mode"
```

### After GUI Refactor
```bash
# Full Phase 4 features:
python start_jarvis_gui.bat

# New capabilities:
# - Multiple chat sessions with persistence
# - Session pinning and organization
# - Hardware monitoring in GUI
# - Export/import conversations
```

---

## 📊 DATABASE SCHEMA

```sql
-- Chat Sessions
CREATE TABLE chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    is_pinned BOOLEAN NOT NULL DEFAULT 0
);

-- Chat Messages
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_session_id ON chat_messages(session_id);
CREATE INDEX idx_timestamp ON chat_messages(timestamp);
```

---

## 💡 DESIGN DECISIONS

1. **SQLite over JSON**: Better for querying, concurrent access, relationships
2. **SQLAlchemy ORM**: Type-safe, easier to maintain than raw SQL
3. **Cascade Delete**: Deleting session removes messages automatically
4. **Pin First Ordering**: Pinned sessions always appear at top
5. **ISO Timestamps**: Standard format for export/import
6. **Sidebar Left**: Common pattern (VSCode, ChatGPT, Discord)
7. **WMI for Temps**: Windows-native method for CPU temperature
8. **G-Helper Primary**: Best tool for ASUS TUF profile switching

---

## 🐛 KNOWN LIMITATIONS

1. **CPU Temperature**: Requires WMI access (may need admin rights)
2. **GPU Stats**: Only works with NVIDIA GPUs (GPUtil limitation)
3. **Performance Profiles**: G-Helper must be installed for ASUS features
4. **Voice Quality**: Current TTS (pyttsx3) is robotic - Phase 5 will improve
5. **Session Search**: Not yet implemented (can add in future)
6. **Message Editing**: Not supported (would require agent memory reset)

---

## 📦 DEPENDENCIES STATUS

All Phase 4 dependencies are already in `requirements.txt`:
- ✅ sqlalchemy (database)
- ✅ psutil (CPU, RAM, disk, battery)
- ✅ GPUtil (GPU stats)
- ✅ wmi (CPU temperature on Windows)
- ✅ customtkinter (GUI)
- ✅ All Phase 1-3 dependencies

No additional installations needed!

---

## 🎨 UI DESIGN NOTES

### Color Palette (Iron Man Theme)
- **Primary BG**: `#0a0e27` (deep space blue)
- **Sidebar BG**: `#0f1428` (slightly darker)
- **Accent**: `#00d9ff` (arc reactor cyan)
- **Success**: `#00ff88` (JARVIS green)
- **Warning**: `#ffaa00` (alert orange)
- **Error**: `#ff3366` (critical red)

### Typography
- **Header**: Orbitron Bold 32px
- **Body**: Courier New 11-12px
- **Code**: Consolas 11px
- **Mono**: Consistent monospace for technical info

### Animations
- Waveform continues from Phase 2
- Smooth session list scrolling
- Hover effects on session items
- Pin icon animation

---

**Last Updated**: Phase 4 Implementation
**Status**: Database ✅ | Tools ✅ | GUI 🚧 (40% complete)
