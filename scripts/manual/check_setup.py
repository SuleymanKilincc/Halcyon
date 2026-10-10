"""
Setup verification script for Jarvis.
Run this to check if your environment is properly configured.
"""

import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check Python version."""
    print("Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"  ✗ Python {version.major}.{version.minor}.{version.micro} (3.8+ required)")
        return False

def check_ollama():
    """Check if Ollama is installed and running."""
    print("\nChecking Ollama...")
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("  ✓ Ollama is installed and running")
            print("\nInstalled models:")
            for line in result.stdout.split('\n')[1:]:  # Skip header
                if line.strip():
                    print(f"    • {line.split()[0]}")
            return True
        else:
            print("  ✗ Ollama is installed but not responding")
            return False
    except FileNotFoundError:
        print("  ✗ Ollama not found")
        print("    Install from: https://ollama.ai/download")
        return False
    except Exception as e:
        print(f"  ✗ Error checking Ollama: {e}")
        return False

def check_dependencies():
    """Check if required packages are installed."""
    print("\nChecking Python dependencies...")
    required = [
        "langchain",
        "langchain_ollama",
        "langchain_community",
        "duckduckgo_search",
        "beautifulsoup4",
        "requests",
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} (missing)")
            missing.append(package)
    
    if missing:
        print("\nTo install missing packages:")
        print("  pip install -r requirements.txt")
        return False
    return True

def check_workspace():
    """Check workspace directory."""
    print("\nChecking workspace...")
    workspace = Path("workspace")
    if workspace.exists() and workspace.is_dir():
        print(f"  ✓ Workspace directory exists: {workspace.absolute()}")
        return True
    else:
        print("  ✗ Workspace directory not found")
        print("    Creating workspace directory...")
        workspace.mkdir(exist_ok=True)
        print("  ✓ Workspace created")
        return True

def main():
    """Run all checks."""
    print("=" * 60)
    print("JARVIS SETUP VERIFICATION")
    print("=" * 60)
    
    checks = [
        check_python_version(),
        check_ollama(),
        check_dependencies(),
        check_workspace()
    ]
    
    print("\n" + "=" * 60)
    if all(checks):
        print("✓ ALL CHECKS PASSED!")
        print("\nYou're ready to run Jarvis:")
        print("  python agent.py")
    else:
        print("✗ SOME CHECKS FAILED")
        print("\nPlease fix the issues above before running Jarvis.")
    print("=" * 60)

if __name__ == "__main__":
    main()
