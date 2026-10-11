"""
GUI Setup Script for Halcyon
Checks and installs GUI dependencies with helpful guidance
"""

import subprocess
import sys
import platform

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

def check_package(package_name, import_name=None):
    """Check if a package is installed."""
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        print(f"  ✓ {package_name}")
        return True
    except ImportError:
        print(f"  ✗ {package_name} (missing)")
        return False

def install_requirements():
    """Install all requirements."""
    print("\nInstalling requirements from requirements.txt...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("  ✓ Requirements installed")
        return True
    except subprocess.CalledProcessError:
        print("  ✗ Failed to install requirements")
        return False

def check_pyaudio_special():
    """Special check for PyAudio on Windows."""
    if platform.system() != "Windows":
        return True
    
    try:
        import pyaudio
        print("  ✓ PyAudio (working)")
        return True
    except ImportError:
        print("  ✗ PyAudio (missing)")
        print("\n" + "="*60)
        print("WINDOWS PYAUDIO INSTALLATION GUIDE")
        print("="*60)
        print("\nPyAudio requires special installation on Windows:")
        print("\nOption 1 (Recommended):")
        print("  1. Download wheel from:")
        print("     https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio")
        print(f"  2. Choose file matching Python {sys.version_info.major}.{sys.version_info.minor}")
        print("  3. Install: pip install PyAudio-X.X.XX-cpXX-cpXX-win_amd64.whl")
        print("\nOption 2:")
        print("  pip install pipwin")
        print("  pipwin install pyaudio")
        print("\n" + "="*60)
        return False

def check_microphone():
    """Check if microphone is available."""
    print("\nChecking microphone access...")
    try:
        import speech_recognition as sr
        mic_list = sr.Microphone.list_microphone_names()
        if mic_list:
            print(f"  ✓ Found {len(mic_list)} microphone(s)")
            print(f"    Default: {mic_list[0]}")
            return True
        else:
            print("  ⚠️ No microphones detected")
            return False
    except Exception as e:
        print(f"  ⚠️ Could not check microphones: {e}")
        return False

def check_tts():
    """Check TTS engine."""
    print("\nChecking Text-to-Speech engine...")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        print(f"  ✓ TTS engine initialized")
        print(f"  ✓ Found {len(voices)} voice(s)")
        return True
    except Exception as e:
        print(f"  ✗ TTS error: {e}")
        return False

def check_ollama():
    """Check Ollama installation."""
    print("\nChecking Ollama...")
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("  ✓ Ollama is running")
            
            # Check for qwen3.5:9b model
            if "qwen3.5:9b" in result.stdout or "qwen2.5:9b" in result.stdout:
                print("  ✓ Required model found")
            else:
                print("  ⚠️ Model qwen3.5:9b not found")
                print("     Run: ollama pull qwen3.5:9b")
            return True
        else:
            print("  ✗ Ollama not responding")
            return False
    except FileNotFoundError:
        print("  ✗ Ollama not installed")
        print("     Install from: https://ollama.ai/download")
        return False
    except Exception as e:
        print(f"  ✗ Error checking Ollama: {e}")
        return False

def main():
    """Main setup check."""
    print("="*60)
    print("HALCYON GUI SETUP CHECKER")
    print("="*60)
    print()
    
    checks = []
    
    # Python version
    checks.append(check_python_version())
    
    print("\nChecking core dependencies...")
    checks.append(check_package("langchain"))
    checks.append(check_package("langchain_ollama"))
    checks.append(check_package("langgraph"))
    
    print("\nChecking GUI dependencies...")
    gui_checks = []
    gui_checks.append(check_package("customtkinter"))
    gui_checks.append(check_package("PIL", "pillow"))
    gui_checks.append(check_package("speech_recognition"))
    gui_checks.append(check_package("pyttsx3"))
    
    # If any GUI dependency is missing, offer to install
    if not all(gui_checks):
        print("\n" + "="*60)
        response = input("Install missing GUI dependencies? (Y/N): ").strip().upper()
        if response in ['Y', 'YES']:
            if install_requirements():
                print("\nRechecking GUI dependencies...")
                gui_checks = []
                gui_checks.append(check_package("customtkinter"))
                gui_checks.append(check_package("PIL", "pillow"))
                gui_checks.append(check_package("speech_recognition"))
                gui_checks.append(check_package("pyttsx3"))
    
    checks.extend(gui_checks)
    
    # Special PyAudio check
    checks.append(check_pyaudio_special())
    
    # Hardware checks
    checks.append(check_microphone())
    checks.append(check_tts())
    checks.append(check_ollama())
    
    # Summary
    print("\n" + "="*60)
    if all(checks):
        print("✓ ALL CHECKS PASSED!")
        print("\nYou're ready to launch Halcyon GUI:")
        print("  python gui.py")
        print("\nOr use the launcher:")
        if platform.system() == "Windows":
            print("  start_halcyon_gui.bat")
        else:
            print("  ./start_halcyon_gui.sh")
    else:
        print("⚠️ SOME CHECKS FAILED")
        print("\nPlease fix the issues above before running Halcyon GUI.")
        print("\nCommon fixes:")
        print("  - Install dependencies: pip install -r requirements.txt")
        print("  - Install Ollama: https://ollama.ai/download")
        print("  - Pull model: ollama pull qwen3.5:9b")
        if platform.system() == "Windows":
            print("  - Install PyAudio (see instructions above)")
    print("="*60)

if __name__ == "__main__":
    main()
