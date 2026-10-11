"""
Halcyon AI Agent - Main Orchestrator
Handles the LangGraph agent loop, memory management, and CLI interface.
"""

import sys
from typing import Optional
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import config
from tools import get_all_tools
from database import db_manager

# ============================================================================
# AGENT INITIALIZATION
# ============================================================================

class HalcyonAgent:
    """Main Halcyon AI Agent class."""
    
    def __init__(self):
        """Initialize the Halcyon agent with LLM, tools, and memory."""
        self.llm = None
        self.agent = None
        self.chat_history = []
        self.current_session_id = None
        self.setup_agent()
    
    def setup_agent(self):
        """Set up the LLM, tools, and agent executor."""
        try:
            print(f"{config.COLORS['info']}Initializing Halcyon...{config.COLORS['reset']}")
            
            # Initialize Ollama LLM
            print(f"  • Loading model: {config.OLLAMA_MODEL}")
            self.llm = ChatOllama(
                model=config.OLLAMA_MODEL,
                base_url=config.OLLAMA_BASE_URL,
                temperature=config.MODEL_TEMPERATURE,
                top_p=config.MODEL_TOP_P,
                num_predict=config.MODEL_MAX_TOKENS,
            )
            
            # Get tools
            print(f"  • Loading tools...")
            tools = get_all_tools()
            print(f"    Loaded {len(tools)} tools")
            
            # Create agent using LangGraph
            print(f"  • Creating agent...")
            self.agent = create_react_agent(
                self.llm,
                tools,
                prompt=config.SYSTEM_PROMPT
            )
            
            print(f"{config.COLORS['info']}✓ Halcyon initialized successfully!{config.COLORS['reset']}\n")
            
        except Exception as e:
            print(f"{config.COLORS['error']}❌ Error initializing Halcyon: {str(e)}{config.COLORS['reset']}")
            print(f"\nPlease ensure:")
            print(f"  1. Ollama is running (check with: ollama list)")
            print(f"  2. Model is installed (run: ollama pull {config.OLLAMA_MODEL})")
            print(f"  3. All dependencies are installed (run: pip install -r requirements.txt)")
            sys.exit(1)
    
    def chat(self, user_input: str) -> str:
        """
        Process user input and return agent response.
        
        Args:
            user_input: User's message
            
        Returns:
            Agent's response
        """
        try:
            # Add user message to history
            self.chat_history.append(HumanMessage(content=user_input))
            
            # Run agent
            response = self.agent.invoke({
                "messages": self.chat_history
            })
            
            # Extract the last message (agent's response)
            if response and "messages" in response:
                messages = response["messages"]
                if messages:
                    last_message = messages[-1]
                    output = last_message.content if hasattr(last_message, 'content') else str(last_message)
                    
                    # Add agent response to history
                    self.chat_history.append(AIMessage(content=output))
                    
                    return output
            
            return "I apologize, but I couldn't generate a response."
            
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            print(f"{config.COLORS['error']}{error_msg}{config.COLORS['reset']}")
            return error_msg
    
    def reset_memory(self):
        """Clear conversation history."""
        self.chat_history = []
        self.current_session_id = None
        print(f"{config.COLORS['info']}✓ Conversation history cleared{config.COLORS['reset']}")
    
    def load_session_history(self, session_id: int):
        """Load conversation history from database session."""
        try:
            self.current_session_id = session_id
            messages = db_manager.get_session_messages(session_id)
            
            # Convert database messages to LangChain messages
            self.chat_history = []
            for msg in messages:
                if msg.role == "user":
                    self.chat_history.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    self.chat_history.append(AIMessage(content=msg.content))
                elif msg.role == "system":
                    self.chat_history.append(SystemMessage(content=msg.content))
            
            print(f"{config.COLORS['info']}✓ Loaded {len(messages)} messages from session {session_id}{config.COLORS['reset']}")
            
        except Exception as e:
            print(f"{config.COLORS['error']}Error loading session history: {str(e)}{config.COLORS['reset']}")
    
    def set_session_id(self, session_id: int):
        """Set the current session ID for message saving."""
        self.current_session_id = session_id

# ============================================================================
# CLI INTERFACE
# ============================================================================

def print_banner():
    """Print welcome banner."""
    banner = f"""
{config.COLORS['halcyon']}╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║              🤖  HALCYON AI AGENT SYSTEM  🤖              ║
║                                                           ║
║        Your Local AI Assistant powered by Ollama         ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝{config.COLORS['reset']}
"""
    print(banner)
    
    description = config.AGENT_DESCRIPTION.format(
        model=config.OLLAMA_MODEL,
        workspace=config.WORKSPACE_DIR
    )
    print(description)
    print()

def print_help():
    """Print help information."""
    help_text = f"""
{config.COLORS['info']}Available Commands:{config.COLORS['reset']}
  /help      - Show this help message
  /reset     - Clear conversation history
  /workspace - Show workspace directory path
  /tools     - List available tools
  /exit      - Exit Halcyon

{config.COLORS['info']}Example Requests:{config.COLORS['reset']}
  • "List files in the current directory"
  • "Create a Python script that prints Hello World"
  • "Search the web for Python best practices"
  • "Read the contents of example.txt"
  • "Run the command 'python --version'"
"""
    print(help_text)

def handle_command(command: str, agent: HalcyonAgent) -> bool:
    """
    Handle special commands.
    
    Args:
        command: Command string
        agent: HalcyonAgent instance
        
    Returns:
        True if should continue, False if should exit
    """
    command = command.strip().lower()
    
    if command == "/exit":
        print(f"\n{config.COLORS['halcyon']}Goodbye! Stay awesome! 👋{config.COLORS['reset']}")
        return False
    
    elif command == "/help":
        print_help()
    
    elif command == "/reset":
        agent.reset_memory()
    
    elif command == "/workspace":
        print(f"\n{config.COLORS['info']}Workspace Directory:{config.COLORS['reset']}")
        print(f"  {config.WORKSPACE_DIR}")
        print(f"\n{config.COLORS['info']}This is where Halcyon will create and manage files.{config.COLORS['reset']}")
    
    elif command == "/tools":
        print(f"\n{config.COLORS['info']}Available Tools:{config.COLORS['reset']}")
        tools = get_all_tools()
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.name}")
            if tool.description:
                # Get first line of description
                first_line = tool.description.split('\n')[0].strip()
                print(f"     {first_line}")
        print()
    
    else:
        print(f"{config.COLORS['warning']}Unknown command: {command}{config.COLORS['reset']}")
        print("Type /help for available commands")
    
    return True

def run_cli():
    """Run the interactive CLI loop."""
    # Print banner
    print_banner()
    
    # Initialize agent
    agent = HalcyonAgent()
    
    # Main loop
    print(f"{config.COLORS['info']}Ready! Type your request or /help for commands.{config.COLORS['reset']}\n")
    
    while True:
        try:
            # Get user input
            user_input = input(f"{config.COLORS['user']}{config.CLI_PROMPT_USER}{config.COLORS['reset']}").strip()
            
            # Skip empty input
            if not user_input:
                continue
            
            # Handle commands
            if user_input.startswith('/'):
                should_continue = handle_command(user_input, agent)
                if not should_continue:
                    break
                continue
            
            # Process with agent
            print(f"\n{config.COLORS['halcyon']}{config.CLI_PROMPT_HALCYON}{config.COLORS['reset']}", end="", flush=True)
            response = agent.chat(user_input)
            print(f"{response}\n")
            
        except KeyboardInterrupt:
            print(f"\n\n{config.COLORS['warning']}Interrupted by user{config.COLORS['reset']}")
            print(f"{config.COLORS['halcyon']}Goodbye! 👋{config.COLORS['reset']}")
            break
        
        except EOFError:
            print(f"\n{config.COLORS['halcyon']}Goodbye! 👋{config.COLORS['reset']}")
            break
        
        except Exception as e:
            print(f"\n{config.COLORS['error']}Unexpected error: {str(e)}{config.COLORS['reset']}")
            print(f"{config.COLORS['info']}Continuing...{config.COLORS['reset']}\n")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    try:
        run_cli()
    except Exception as e:
        print(f"{config.COLORS['error']}Fatal error: {str(e)}{config.COLORS['reset']}")
        sys.exit(1)

if __name__ == "__main__":
    main()
