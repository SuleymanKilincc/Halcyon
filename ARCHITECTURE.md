# Jarvis AI Agent - System Architecture

Detailed technical architecture and design decisions.

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         USER                                │
│                    (CLI Interface)                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGENT.PY                                 │
│  ┌────────────────────────────────────────────────────┐    │
│  │         JarvisAgent (Main Orchestrator)            │    │
│  │                                                     │    │
│  │  • Conversation Memory                             │    │
│  │  • Agent Executor (LangChain)                      │    │
│  │  • Tool Calling Loop                               │    │
│  └───────────┬─────────────────────────────────────┬──┘    │
└──────────────┼─────────────────────────────────────┼────────┘
               │                                     │
               ▼                                     ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│      CONFIG.PY           │        │       TOOLS.PY           │
│                          │        │                          │
│ • Model Settings         │        │ ┌──────────────────────┐ │
│ • System Prompts         │        │ │  Terminal Tool       │ │
│ • Safety Rules           │        │ │  - execute_command   │ │
│ • Workspace Config       │        │ └──────────────────────┘ │
│ • UI Settings            │        │                          │
└──────────────────────────┘        │ ┌──────────────────────┐ │
                                    │ │  File System Tools   │ │
               ┌────────────────────┤ │  - read_file         │ │
               │                    │ │  - write_file        │ │
               ▼                    │ │  - append_to_file    │ │
┌──────────────────────────┐        │ │  - list_directory    │ │
│   OLLAMA (Local LLM)     │        │ │  - delete_file       │ │
│                          │        │ └──────────────────────┘ │
│ • qwen2.5-coder:7b       │        │                          │
│ • Function Calling       │        │ ┌──────────────────────┐ │
│ • Token Generation       │        │ │  Web Tools           │ │
│ • Context Management     │        │ │  - search_web        │ │
└──────────────────────────┘        │ │  - fetch_webpage     │ │
                                    │ └──────────────────────┘ │
                                    └────────┬─────────────────┘
                                             │
                                             ▼
                                    ┌──────────────────────────┐
                                    │   EXTERNAL RESOURCES     │
                                    │                          │
                                    │ • Local File System      │
                                    │ • Terminal/Shell         │
                                    │ • DuckDuckGo API         │
                                    │ • Web (HTTP/HTTPS)       │
                                    └──────────────────────────┘
```

## 🔄 Agent Execution Flow

### 1. Initialization Phase

```python
User starts → agent.py
             ↓
         JarvisAgent.__init__()
             ↓
         setup_agent()
             ↓
    ┌────────┴────────┐
    ↓                 ↓
Initialize LLM    Load Tools
(ChatOllama)     (get_all_tools)
    ↓                 ↓
Create Prompt    Create Agent
Template        (create_tool_calling_agent)
    ↓                 ↓
    └────────┬────────┘
             ↓
    Create AgentExecutor
             ↓
    Initialize Memory
             ↓
        Ready for Input
```

### 2. Request Processing Flow

```python
User Input
    ↓
JarvisAgent.chat(input)
    ↓
Load Chat History from Memory
    ↓
AgentExecutor.invoke({
    "input": input,
    "chat_history": history
})
    ↓
┌─────────── AGENT LOOP ───────────┐
│                                   │
│  1. THOUGHT PHASE                 │
│     LLM analyzes input            │
│     Plans next action             │
│                                   │
│  2. ACTION SELECTION              │
│     Choose tool & parameters      │
│     ↓                            │
│  3. APPROVAL CHECK (if critical)  │
│     get_user_approval()           │
│     Wait for Y/N                  │
│     ↓                            │
│  4. TOOL EXECUTION                │
│     Execute selected tool         │
│     Capture output                │
│     ↓                            │
│  5. OBSERVATION                   │
│     LLM receives tool output      │
│     Evaluates result              │
│     ↓                            │
│  6. DECISION                      │
│     Task complete? → Exit loop    │
│     Need more actions? → Return   │
│     to step 1                     │
│                                   │
└───────────────────────────────────┘
    ↓
Final Response
    ↓
Save to Memory
    ↓
Return to User
```

### 3. Tool Execution Flow (with Safety)

```python
Tool Invoked (e.g., write_file)
    ↓
Check if Critical Operation
    ↓
    ├─ YES → Request Approval
    │        ↓
    │    Display Details
    │        ↓
    │    Wait for User Input (Y/N)
    │        ↓
    │    ├─ N → Return "Cancelled"
    │    │
    │    └─ Y → Continue
    │
    └─ NO → Continue
    ↓
Validate Parameters
    ↓
Execute Operation
    ↓
    ├─ Success → Return Result
    │
    └─ Error → Return Error Message
```

## 🧩 Component Details

### 1. Agent Layer (`agent.py`)

**Responsibilities:**
- Manage conversation state
- Coordinate LLM and tools
- Handle user interaction
- Error recovery

**Key Classes:**

```python
class JarvisAgent:
    llm: ChatOllama              # Language model
    agent_executor: AgentExecutor # Tool orchestrator
    memory: ConversationBufferMemory # Chat history
    
    def setup_agent()            # Initialize components
    def chat(input) → response   # Process user request
    def reset_memory()           # Clear history
```

**Design Patterns:**
- **Facade Pattern**: Simple interface to complex LangChain system
- **Strategy Pattern**: Pluggable LLM and tools
- **Memento Pattern**: Conversation state management

### 2. Configuration Layer (`config.py`)

**Responsibilities:**
- Centralize all settings
- Define safety rules
- Manage paths and constants
- Provide helper functions

**Key Sections:**

```python
# Model Configuration
OLLAMA_MODEL = "qwen2.5-coder:7b"
MODEL_TEMPERATURE = 0.7

# Safety Configuration
DANGEROUS_COMMAND_KEYWORDS = [...]
SENSITIVE_EXTENSIONS = [...]

# System Prompts
SYSTEM_PROMPT = """..."""

# Helper Functions
def get_workspace_path(path)
def is_safe_path(path)
```

**Design Patterns:**
- **Singleton Pattern**: Single source of truth
- **Factory Pattern**: Path creation helpers

### 3. Tools Layer (`tools.py`)

**Responsibilities:**
- Implement tool functions
- Handle external interactions
- Provide safety checks
- Format outputs

**Tool Categories:**

```python
# Terminal Tools
@tool
def execute_terminal_command(cmd: str) → str:
    - Check against blacklist
    - Request approval
    - Execute via subprocess
    - Return output

# File System Tools
@tool
def read_file(path: str) → str:
@tool
def write_file(path: str, content: str) → str:
@tool
def append_to_file(path: str, content: str) → str:
@tool
def list_directory(path: str) → str:
@tool
def delete_file(path: str) → str:

# Web Tools
@tool
def search_web(query: str) → str:
    - DuckDuckGo search
    - Return formatted results

@tool
def fetch_webpage(url: str) → str:
    - HTTP request
    - Parse HTML with BeautifulSoup
    - Return clean text
```

**Design Patterns:**
- **Decorator Pattern**: `@tool` wrapper
- **Template Method**: Common error handling
- **Proxy Pattern**: Safety checks before execution

### 4. Safety System

**Multi-Layer Protection:**

```
User Request
    ↓
Layer 1: Command Blacklist
    • Blocks obviously dangerous commands
    • Returns error immediately
    ↓
Layer 2: Path Validation
    • Ensures operations within workspace
    • Prevents directory traversal
    ↓
Layer 3: File Type Checking
    • Identifies sensitive extensions
    • Triggers additional warnings
    ↓
Layer 4: User Approval
    • Displays operation details
    • Waits for explicit Y/N
    ↓
Layer 5: Resource Limits
    • File size limits (10MB)
    • Command timeout (30s)
    • Output truncation (5000 chars)
    ↓
Execution
```

## 🗄️ Data Flow

### Memory Management

```python
# Conversation stored as message list
messages = [
    HumanMessage("Create a file"),
    AIMessage("Creating file..."),
    HumanMessage("Now read it"),
    AIMessage("Reading file...")
]

# Loaded into each request for context
agent_executor.invoke({
    "input": new_input,
    "chat_history": messages
})

# Updated after each interaction
memory.save_context(
    {"input": user_msg},
    {"output": agent_response}
)
```

### Context Window Management

```
┌────────────────────────────────┐
│     System Prompt (Static)     │  ~800 tokens
├────────────────────────────────┤
│   Chat History (Dynamic)       │  ~variable
│   - Message 1                  │
│   - Message 2                  │
│   - ...                        │
├────────────────────────────────┤
│   Current User Input           │  ~variable
├────────────────────────────────┤
│   Tool Descriptions            │  ~1200 tokens
├────────────────────────────────┤
│   Agent Scratchpad            │  ~variable
│   (intermediate thoughts)      │
└────────────────────────────────┘
      Total: ~2048 tokens output limit
```

## 🔌 Integration Points

### 1. Ollama Integration

```python
# Connection
llm = ChatOllama(
    model="qwen2.5-coder:7b",
    base_url="http://localhost:11434",
    temperature=0.7
)

# Tool binding (function calling)
agent = create_tool_calling_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

# The agent can now:
# - Understand tool descriptions
# - Generate tool calls with parameters
# - Process tool outputs
```

### 2. LangChain Integration

```python
# Prompt Template
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad")
])

# Agent Creation
agent = create_tool_calling_agent(llm, tools, prompt)

# Executor (with safety limits)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=15,
    max_execution_time=300
)
```

### 3. External Services

```python
# DuckDuckGo (via langchain_community)
search = DuckDuckGoSearchRun()
results = search.run(query)

# Web Scraping (via requests + BeautifulSoup)
response = requests.get(url, headers=HEADERS, timeout=10)
soup = BeautifulSoup(response.content, 'lxml')
text = soup.get_text()

# Terminal (via subprocess)
result = subprocess.run(
    command,
    shell=True,
    capture_output=True,
    timeout=30
)
```

## 📊 Error Handling Strategy

### Hierarchical Error Handling

```python
Level 1: Tool Level
    try:
        # Tool operation
    except SpecificError:
        return "User-friendly error message"

Level 2: Agent Level
    try:
        response = agent_executor.invoke(...)
    except Exception:
        return "Error processing request"

Level 3: CLI Level
    try:
        # Main loop
    except KeyboardInterrupt:
        # Graceful shutdown
    except Exception:
        # Log and continue
```

### Error Recovery

```python
# Parsing Errors
AgentExecutor(
    handle_parsing_errors=True  # Auto-retry on parse failure
)

# Timeout Protection
subprocess.run(
    command,
    timeout=30  # Prevent hanging
)

# Output Truncation
if len(output) > MAX_LENGTH:
    output = output[:MAX_LENGTH] + "...(truncated)"
```

## 🎯 Performance Optimizations

### 1. Lazy Loading
- Tools loaded once at startup
- Model stays in memory after first use

### 2. Output Truncation
- Prevents overwhelming context window
- Keeps responses manageable

### 3. Timeout Protection
- 30s per command
- 5min per agent task
- Prevents infinite loops

### 4. Memory Management
- Conversation buffer (grows with use)
- Can be cleared with `/reset`
- Option to implement sliding window

## 🔐 Security Architecture

### Defense in Depth

```
Layer 1: Input Validation
    - Command syntax checking
    - Path normalization
    - Parameter sanitization

Layer 2: Blacklisting
    - Dangerous command patterns
    - Sensitive file extensions
    - Risky operations

Layer 3: Sandboxing
    - Default workspace directory
    - Path traversal prevention
    - Resource limits

Layer 4: User Confirmation
    - Explicit approval required
    - Operation details displayed
    - Can't be bypassed

Layer 5: Execution Isolation
    - Subprocess for commands
    - Timeout limits
    - Error containment
```

### Threat Model

**Protected Against:**
- ✅ Accidental destructive commands
- ✅ Path traversal attacks
- ✅ Resource exhaustion
- ✅ Unauthorized file access
- ✅ Command injection (via subprocess)

**User Responsibility:**
- ⚠️ Reviewing approval prompts
- ⚠️ Verifying operations make sense
- ⚠️ Not approving suspicious commands

## 🧪 Testing Strategy

### Manual Testing
```bash
# Run setup verification
python test_setup.py

# Test basic functionality
python agent.py
> List files in the current directory
> What is 2+2?
> /help
```

### Component Testing
```python
# Test individual tools
from tools import read_file
result = read_file("test.txt")

# Test configuration
from config import is_safe_path
assert is_safe_path("workspace/file.txt")
```

## 📈 Scalability Considerations

### Current Limits
- Single conversation at a time
- Local model (hardware-dependent)
- No persistent storage
- In-memory conversation history

### Future Scalability
- Multiple concurrent conversations
- Distributed agent execution
- Persistent storage (database)
- Model load balancing
- Cloud model fallback

## 🎓 Design Decisions

### Why LangChain?
- **Pros**: Established ecosystem, tool calling support, memory management
- **Cons**: Additional abstraction layer
- **Alternatives**: Raw Ollama API, LangGraph, CrewAI

### Why Ollama?
- **Pros**: Simple setup, local execution, model variety
- **Cons**: Requires local resources
- **Alternatives**: OpenAI API, Anthropic, local transformers

### Why Approval for Everything?
- **Pros**: Maximum safety, user awareness, educational
- **Cons**: Can be tedious for trusted operations
- **Future**: Permission system, trusted command whitelist

### Why Workspace Directory?
- **Pros**: Clear boundaries, easy to clean up, prevents accidents
- **Cons**: Extra step to access other locations
- **Future**: Configurable allowed paths

## 🔄 Extension Points

### Adding New Tools

```python
# 1. Define tool in tools.py
@tool
def my_new_tool(param: str) -> str:
    """Tool description for LLM."""
    # Implementation
    return result

# 2. Add to tool list
def get_all_tools():
    return [
        # ...existing tools
        my_new_tool,
    ]

# 3. Restart agent (tools loaded at startup)
```

### Changing LLM

```python
# In config.py
OLLAMA_MODEL = "mistral:7b"  # Or any other model

# Restart agent
python agent.py
```

### Custom System Prompt

```python
# In config.py
SYSTEM_PROMPT = """
Your custom instructions here...
"""
```

---

This architecture provides a solid foundation for a local AI agent with room for growth and customization!
