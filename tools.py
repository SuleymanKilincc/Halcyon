"""
Custom tools for Jarvis AI Agent.
Implements terminal access, file system operations, web capabilities,
web automation, file downloading, and archive extraction.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List
import requests
from bs4 import BeautifulSoup
from langchain.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import zipfile
import tarfile
import py7zr
import shutil
from urllib.parse import urlparse, unquote

import config

# ============================================================================
# TERMINAL TOOLS
# ============================================================================

def get_user_approval(operation: str, details: str) -> bool:
    """
    Request user approval for critical operations.
    Uses GUI callback if available, otherwise falls back to terminal input.
    
    Args:
        operation: Name of the operation
        details: Details about what will be executed
        
    Returns:
        True if approved, False otherwise
    """
    # Try to use GUI callback first
    approval_callback = config.get_approval_callback()
    
    if approval_callback is not None:
        try:
            return approval_callback(operation, details)
        except Exception as e:
            print(f"GUI approval error: {e}")
            # Fall through to terminal approval
    
    # Fallback to terminal input (for CLI mode)
    print(f"\n{config.COLORS['warning']}⚠️  APPROVAL REQUIRED{config.COLORS['reset']}")
    print(f"Operation: {operation}")
    print(f"Details: {details}")
    
    while True:
        response = input(f"\nApprove this operation? (Y/N): ").strip().upper()
        if response in ['Y', 'YES']:
            return True
        elif response in ['N', 'NO']:
            return False
        else:
            print("Please enter Y or N")

def is_dangerous_command(command: str) -> bool:
    """
    Check if a command contains dangerous keywords.
    
    Args:
        command: Command to check
        
    Returns:
        True if command is potentially dangerous
    """
    command_lower = command.lower()
    return any(keyword.lower() in command_lower 
               for keyword in config.DANGEROUS_COMMAND_KEYWORDS)

@tool
def execute_terminal_command(command: str) -> str:
    """
    Execute a terminal command on the local system.
    
    This tool allows running shell commands. All commands require user approval
    for safety. Use this when you need to:
    - Run system commands
    - Install packages
    - Check system information
    - Execute scripts
    
    Args:
        command: The shell command to execute
        
    Returns:
        Command output or error message
        
    Example:
        execute_terminal_command("ls -la")
        execute_terminal_command("python --version")
    """
    # Check for dangerous commands
    if is_dangerous_command(command):
        return f"❌ BLOCKED: This command contains potentially dangerous operations: {command}"
    
    # Request user approval
    if not get_user_approval("Terminal Command Execution", f"Command: {command}"):
        return "❌ Operation cancelled by user"
    
    try:
        # Determine shell based on OS
        shell = sys.platform == "win32"
        
        # Execute command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(config.WORKSPACE_DIR)
        )
        
        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"
        
        # Truncate if too long
        if len(output) > config.MAX_OUTPUT_LENGTH:
            output = output[:config.MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
        
        return output if output else "✓ Command executed successfully (no output)"
        
    except subprocess.TimeoutExpired:
        return "❌ Command execution timeout (30 seconds exceeded)"
    except Exception as e:
        return f"❌ Error executing command: {str(e)}"

# ============================================================================
# FILE SYSTEM TOOLS
# ============================================================================

@tool
def read_file(file_path: str) -> str:
    """
    Read the contents of a file.
    
    Use this tool to read file contents. Supports text files up to 10MB.
    
    Args:
        file_path: Path to the file (relative to workspace or absolute)
        
    Returns:
        File contents or error message
        
    Example:
        read_file("example.txt")
        read_file("code/main.py")
    """
    try:
        path = Path(file_path)
        
        # Convert to absolute path if relative
        if not path.is_absolute():
            path = config.get_workspace_path(file_path)
        
        # Check if file exists
        if not path.exists():
            return f"❌ File not found: {file_path}"
        
        if not path.is_file():
            return f"❌ Path is not a file: {file_path}"
        
        # Check file size
        if path.stat().st_size > config.MAX_FILE_READ_SIZE:
            return f"❌ File too large (max {config.MAX_FILE_READ_SIZE / (1024*1024)}MB)"
        
        # Read file
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        return content
        
    except Exception as e:
        return f"❌ Error reading file: {str(e)}"

@tool
def write_file(file_path: str, content: str) -> str:
    """
    Write content to a file. Creates the file if it doesn't exist.
    
    Use this tool to create or overwrite files. Requires user approval.
    
    Args:
        file_path: Path to the file (relative to workspace or absolute)
        content: Content to write to the file
        
    Returns:
        Success message or error
        
    Example:
        write_file("hello.txt", "Hello, World!")
        write_file("script.py", "print('Hello')")
    """
    try:
        path = Path(file_path)
        
        # Convert to absolute path if relative
        if not path.is_absolute():
            path = config.get_workspace_path(file_path)
        
        # Check if sensitive file
        if path.suffix in config.SENSITIVE_EXTENSIONS:
            if not get_user_approval(
                "Write Sensitive File", 
                f"File: {path}\nExtension: {path.suffix}"
            ):
                return "❌ Operation cancelled by user"
        
        # Check if file exists (overwrite warning)
        operation = "Overwrite File" if path.exists() else "Create File"
        if not get_user_approval(operation, f"Path: {path}\nSize: {len(content)} bytes"):
            return "❌ Operation cancelled by user"
        
        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"✓ File written successfully: {path}"
        
    except Exception as e:
        return f"❌ Error writing file: {str(e)}"

@tool
def append_to_file(file_path: str, content: str) -> str:
    """
    Append content to the end of a file. Creates the file if it doesn't exist.
    
    Use this tool to add content without overwriting existing data.
    
    Args:
        file_path: Path to the file (relative to workspace or absolute)
        content: Content to append
        
    Returns:
        Success message or error
        
    Example:
        append_to_file("log.txt", "New log entry\\n")
    """
    try:
        path = Path(file_path)
        
        # Convert to absolute path if relative
        if not path.is_absolute():
            path = config.get_workspace_path(file_path)
        
        # Request approval
        if not get_user_approval(
            "Append to File", 
            f"Path: {path}\nContent length: {len(content)} bytes"
        ):
            return "❌ Operation cancelled by user"
        
        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Append to file
        with open(path, 'a', encoding='utf-8') as f:
            f.write(content)
        
        return f"✓ Content appended successfully: {path}"
        
    except Exception as e:
        return f"❌ Error appending to file: {str(e)}"

@tool
def list_directory(directory_path: str = ".") -> str:
    """
    List contents of a directory.
    
    Use this tool to explore directory structure and find files.
    
    Args:
        directory_path: Path to directory (relative to workspace or absolute)
        
    Returns:
        Formatted list of files and directories
        
    Example:
        list_directory(".")
        list_directory("src")
    """
    try:
        path = Path(directory_path)
        
        # Convert to absolute path if relative
        if not path.is_absolute():
            path = config.get_workspace_path(directory_path)
        
        # Check if directory exists
        if not path.exists():
            return f"❌ Directory not found: {directory_path}"
        
        if not path.is_dir():
            return f"❌ Path is not a directory: {directory_path}"
        
        # List contents
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        
        if not items:
            return f"📁 {path}\n(empty directory)"
        
        output = [f"📁 {path}\n"]
        for item in items:
            if item.is_dir():
                output.append(f"  📂 {item.name}/")
            else:
                size = item.stat().st_size
                size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                output.append(f"  📄 {item.name} ({size_str})")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error listing directory: {str(e)}"

@tool
def delete_file(file_path: str) -> str:
    """
    Delete a file. Requires user approval for safety.
    
    Use this tool to remove files. Cannot delete directories.
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        Success message or error
        
    Example:
        delete_file("temp.txt")
    """
    try:
        path = Path(file_path)
        
        # Convert to absolute path if relative
        if not path.is_absolute():
            path = config.get_workspace_path(file_path)
        
        # Check if file exists
        if not path.exists():
            return f"❌ File not found: {file_path}"
        
        if not path.is_file():
            return f"❌ Path is not a file (use with caution for directories): {file_path}"
        
        # Request approval
        if not get_user_approval("Delete File", f"Path: {path}"):
            return "❌ Operation cancelled by user"
        
        # Delete file
        path.unlink()
        
        return f"✓ File deleted successfully: {path}"
        
    except Exception as e:
        return f"❌ Error deleting file: {str(e)}"

# ============================================================================
# WEB TOOLS
# ============================================================================

@tool
def search_web(query: str) -> str:
    """
    Search the web using DuckDuckGo.
    
    Use this tool to find information on the internet. Returns top search results.
    
    Args:
        query: Search query string
        
    Returns:
        Search results with titles and snippets
        
    Example:
        search_web("Python async programming tutorial")
        search_web("latest news AI")
    """
    try:
        search = DuckDuckGoSearchRun()
        results = search.run(query)
        return results
        
    except Exception as e:
        return f"❌ Search error: {str(e)}"

@tool
def fetch_webpage(url: str) -> str:
    """
    Fetch and parse content from a webpage.
    
    Use this tool to extract text content from websites. Returns cleaned text
    without HTML tags.
    
    Args:
        url: URL of the webpage to fetch
        
    Returns:
        Webpage text content or error message
        
    Example:
        fetch_webpage("https://python.org")
        fetch_webpage("https://example.com/article")
    """
    try:
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return "❌ Invalid URL: must start with http:// or https://"
        
        # Fetch webpage
        response = requests.get(
            url,
            headers=config.REQUEST_HEADERS,
            timeout=config.REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Get text
        text = soup.get_text(separator='\n', strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        content = '\n'.join(lines)
        
        # Truncate if too long
        if len(content) > config.MAX_OUTPUT_LENGTH:
            content = content[:config.MAX_OUTPUT_LENGTH] + "\n... (content truncated)"
        
        return f"📄 Content from {url}:\n\n{content}"
        
    except requests.Timeout:
        return f"❌ Timeout: Could not fetch webpage within {config.REQUEST_TIMEOUT} seconds"
    except requests.RequestException as e:
        return f"❌ Error fetching webpage: {str(e)}"
    except Exception as e:
        return f"❌ Error parsing webpage: {str(e)}"

# ============================================================================
# WEB AUTOMATION TOOLS
# ============================================================================

@tool
def browse_website_interactive(url: str, actions: str = "") -> str:
    """
    Browse and interact with modern JavaScript-heavy websites using Playwright.
    
    Use this tool when regular web scraping fails due to JavaScript requirements.
    Can handle SPAs, dynamic content, and interactive elements.
    
    Args:
        url: URL of the website to browse
        actions: Optional actions to perform (e.g., "click button", "scroll down")
        
    Returns:
        Page content or action result
        
    Example:
        browse_website_interactive("https://example.com")
        browse_website_interactive("https://example.com", "click login button")
    """
    try:
        from playwright.sync_api import sync_playwright
        
        # Request approval for web automation
        if not get_user_approval(
            "Web Browser Automation",
            f"URL: {url}\nActions: {actions or 'Load and extract content'}\nNote: Will open headless browser"
        ):
            return "❌ Operation cancelled by user"
        
        with sync_playwright() as p:
            # Launch browser (headless mode)
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Navigate to URL
            page.goto(url, timeout=30000)
            
            # Wait for page to load
            page.wait_for_load_state("networkidle", timeout=10000)
            
            # Perform actions if specified
            if actions:
                # Simple action interpreter
                actions_lower = actions.lower()
                
                if "click" in actions_lower:
                    # Extract element to click
                    parts = actions_lower.split("click")
                    if len(parts) > 1:
                        selector = parts[1].strip()
                        page.click(f"text={selector}")
                        page.wait_for_load_state("networkidle")
                
                elif "scroll" in actions_lower:
                    if "down" in actions_lower:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    elif "up" in actions_lower:
                        page.evaluate("window.scrollTo(0, 0)")
                
                elif "type" in actions_lower or "fill" in actions_lower:
                    # Extract selector and text
                    # Format: "type 'text' in selector"
                    pass  # Basic implementation
            
            # Get page content
            content = page.content()
            
            # Extract text from HTML
            soup = BeautifulSoup(content, 'lxml')
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            clean_content = '\n'.join(lines)
            
            # Close browser
            browser.close()
            
            # Truncate if too long
            if len(clean_content) > config.MAX_OUTPUT_LENGTH:
                clean_content = clean_content[:config.MAX_OUTPUT_LENGTH] + "\n... (content truncated)"
            
            return f"✓ Browser automation completed\nURL: {url}\n\n{clean_content}"
            
    except ImportError:
        return "❌ Playwright not installed. Run: pip install playwright && playwright install chromium"
    except Exception as e:
        return f"❌ Browser automation error: {str(e)}"

# ============================================================================
# FILE DOWNLOAD TOOL
# ============================================================================

@tool
def download_file(url: str, filename: str = "") -> str:
    """
    Download a file from a URL and save it to the workspace.
    
    Use this tool to download files, documents, images, or archives from the internet.
    Files are automatically saved to the workspace directory.
    
    Args:
        url: URL of the file to download
        filename: Optional custom filename (auto-detected from URL if not provided)
        
    Returns:
        Success message with file path or error
        
    Example:
        download_file("https://example.com/document.pdf")
        download_file("https://example.com/image.jpg", "my_image.jpg")
    """
    try:
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return "❌ Invalid URL: must start with http:// or https://"
        
        # Auto-detect filename from URL if not provided
        if not filename:
            parsed_url = urlparse(url)
            filename = unquote(os.path.basename(parsed_url.path))
            
            # If still no filename, use timestamp
            if not filename or '.' not in filename:
                import time
                filename = f"download_{int(time.time())}"
        
        # Ensure filename is safe
        filename = os.path.basename(filename)  # Remove path components
        
        # Full path in workspace
        file_path = config.get_workspace_path(filename)
        
        # Request approval
        if not get_user_approval(
            "Download File",
            f"URL: {url}\nDestination: {file_path}\nNote: Will download file from internet"
        ):
            return "❌ Operation cancelled by user"
        
        # Download file
        print(f"Downloading: {url}")
        response = requests.get(
            url,
            headers=config.REQUEST_HEADERS,
            timeout=60,  # 1 minute timeout
            stream=True  # Stream for large files
        )
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        size_mb = total_size / (1024 * 1024)
        
        # Check if file is too large (max 100MB)
        if total_size > 100 * 1024 * 1024:
            return f"❌ File too large: {size_mb:.1f}MB (max 100MB)"
        
        # Write file in chunks
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Get actual file size
        actual_size = os.path.getsize(file_path)
        actual_size_mb = actual_size / (1024 * 1024)
        
        return f"✓ File downloaded successfully\nURL: {url}\nSaved to: {file_path}\nSize: {actual_size_mb:.2f}MB"
        
    except requests.Timeout:
        return "❌ Download timeout: File took too long to download (60 seconds)"
    except requests.RequestException as e:
        return f"❌ Download error: {str(e)}"
    except Exception as e:
        return f"❌ Error downloading file: {str(e)}"

# ============================================================================
# ARCHIVE EXTRACTION TOOLS
# ============================================================================

@tool
def extract_archive(archive_path: str, extract_to: str = "") -> str:
    """
    Extract compressed archive files (.zip, .tar, .tar.gz, .7z) in the workspace.
    
    Use this tool to extract downloaded archives or compressed files.
    Supports ZIP, TAR, TAR.GZ, TGZ, and 7Z formats.
    
    Args:
        archive_path: Path to archive file (relative to workspace or absolute)
        extract_to: Optional destination directory (defaults to archive name)
        
    Returns:
        Success message with extracted files list or error
        
    Example:
        extract_archive("download.zip")
        extract_archive("archive.tar.gz", "extracted_files")
    """
    try:
        # Convert to absolute path if relative
        archive_path = Path(archive_path)
        if not archive_path.is_absolute():
            archive_path = config.get_workspace_path(str(archive_path))
        else:
            archive_path = Path(archive_path)
        
        # Check if file exists
        if not archive_path.exists():
            return f"❌ Archive not found: {archive_path}"
        
        if not archive_path.is_file():
            return f"❌ Path is not a file: {archive_path}"
        
        # Determine extraction directory
        if extract_to:
            extract_path = config.get_workspace_path(extract_to)
        else:
            # Use archive name without extension
            extract_path = config.get_workspace_path(archive_path.stem)
        
        # Request approval
        if not get_user_approval(
            "Extract Archive",
            f"Archive: {archive_path}\nExtract to: {extract_path}\nNote: Will extract all files"
        ):
            return "❌ Operation cancelled by user"
        
        # Create extraction directory
        extract_path.mkdir(parents=True, exist_ok=True)
        
        # Detect archive type and extract
        archive_ext = archive_path.suffix.lower()
        
        if archive_ext == '.zip':
            # Extract ZIP
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
                file_list = zip_ref.namelist()
        
        elif archive_ext in ['.tar', '.gz', '.tgz', '.bz2']:
            # Extract TAR (including compressed variants)
            mode = 'r'
            if archive_ext == '.gz' or archive_path.suffixes[-2:] == ['.tar', '.gz']:
                mode = 'r:gz'
            elif archive_ext == '.bz2':
                mode = 'r:bz2'
            
            with tarfile.open(archive_path, mode) as tar_ref:
                tar_ref.extractall(extract_path)
                file_list = tar_ref.getnames()
        
        elif archive_ext == '.7z':
            # Extract 7Z
            with py7zr.SevenZipFile(archive_path, mode='r') as z:
                z.extractall(path=extract_path)
                file_list = z.getnames()
        
        else:
            return f"❌ Unsupported archive format: {archive_ext}\nSupported: .zip, .tar, .tar.gz, .tgz, .7z"
        
        # Count extracted files
        total_files = len(file_list)
        
        # List first 10 files
        preview = '\n'.join(f"  - {f}" for f in file_list[:10])
        if total_files > 10:
            preview += f"\n  ... and {total_files - 10} more files"
        
        return f"✓ Archive extracted successfully\nArchive: {archive_path.name}\nExtracted to: {extract_path}\nTotal files: {total_files}\n\nFiles:\n{preview}"
        
    except zipfile.BadZipFile:
        return f"❌ Corrupted or invalid ZIP file: {archive_path}"
    except tarfile.TarError as e:
        return f"❌ TAR extraction error: {str(e)}"
    except py7zr.Bad7zFile:
        return f"❌ Corrupted or invalid 7Z file: {archive_path}"
    except Exception as e:
        return f"❌ Error extracting archive: {str(e)}"

# ============================================================================
# HARDWARE MONITORING TOOLS (ASUS TUF)
# ============================================================================

@tool
def get_system_stats() -> str:
    """
    Get comprehensive system hardware statistics including CPU, GPU, RAM, and temperatures.
    
    Use this tool to monitor system performance and hardware health.
    Designed for ASUS TUF laptops but works on any Windows system.
    
    Returns:
        Formatted system statistics including:
        - CPU usage, temperature, frequency
        - GPU usage, temperature, memory
        - RAM usage
        - Disk usage
        - Battery status (if laptop)
        
    Example:
        get_system_stats()
    """
    try:
        import psutil
        import GPUtil
        
        output = []
        output.append("=" * 60)
        output.append("SYSTEM HARDWARE STATISTICS")
        output.append("=" * 60)
        
        # ====================================================================
        # CPU INFORMATION
        # ====================================================================
        output.append("\n📊 CPU INFORMATION:")
        output.append("-" * 60)
        
        cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
        cpu_avg = sum(cpu_percent) / len(cpu_percent)
        output.append(f"  • Average Usage: {cpu_avg:.1f}%")
        output.append(f"  • Per Core Usage: {', '.join([f'{p:.1f}%' for p in cpu_percent[:8]])}")  # First 8 cores
        
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            output.append(f"  • Current Frequency: {cpu_freq.current:.0f} MHz")
            output.append(f"  • Max Frequency: {cpu_freq.max:.0f} MHz")
        
        # CPU Temperature (Windows)
        try:
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            temperature_info = w.MSAcpi_ThermalZoneTemperature()
            if temperature_info:
                # Convert from tenths of Kelvin to Celsius
                temp_celsius = (temperature_info[0].CurrentTemperature / 10.0) - 273.15
                output.append(f"  • Temperature: {temp_celsius:.1f}°C")
        except:
            output.append(f"  • Temperature: Not available (WMI access required)")
        
        # ====================================================================
        # MEMORY INFORMATION
        # ====================================================================
        output.append("\n💾 MEMORY (RAM):")
        output.append("-" * 60)
        
        mem = psutil.virtual_memory()
        output.append(f"  • Total: {mem.total / (1024**3):.1f} GB")
        output.append(f"  • Used: {mem.used / (1024**3):.1f} GB ({mem.percent}%)")
        output.append(f"  • Available: {mem.available / (1024**3):.1f} GB")
        
        # ====================================================================
        # GPU INFORMATION
        # ====================================================================
        output.append("\n🎮 GPU INFORMATION:")
        output.append("-" * 60)
        
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                for i, gpu in enumerate(gpus):
                    output.append(f"  GPU {i}: {gpu.name}")
                    output.append(f"    • Load: {gpu.load * 100:.1f}%")
                    output.append(f"    • Memory Used: {gpu.memoryUsed:.0f} MB / {gpu.memoryTotal:.0f} MB ({gpu.memoryUtil * 100:.1f}%)")
                    output.append(f"    • Temperature: {gpu.temperature:.1f}°C")
                    output.append(f"    • Driver: {gpu.driver}")
            else:
                output.append("  • No NVIDIA GPU detected")
        except Exception as e:
            output.append(f"  • GPU stats unavailable: {str(e)}")
        
        # ====================================================================
        # DISK INFORMATION
        # ====================================================================
        output.append("\n💿 DISK USAGE:")
        output.append("-" * 60)
        
        partitions = psutil.disk_partitions()
        for partition in partitions[:3]:  # Show first 3 partitions
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                output.append(f"  {partition.device}")
                output.append(f"    • Total: {usage.total / (1024**3):.1f} GB")
                output.append(f"    • Used: {usage.used / (1024**3):.1f} GB ({usage.percent}%)")
                output.append(f"    • Free: {usage.free / (1024**3):.1f} GB")
            except:
                pass
        
        # ====================================================================
        # BATTERY INFORMATION (Laptop)
        # ====================================================================
        if hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery:
                output.append("\n🔋 BATTERY:")
                output.append("-" * 60)
                output.append(f"  • Charge: {battery.percent}%")
                output.append(f"  • Plugged In: {'Yes' if battery.power_plugged else 'No'}")
                if not battery.power_plugged and battery.secsleft > 0:
                    hours = battery.secsleft // 3600
                    minutes = (battery.secsleft % 3600) // 60
                    output.append(f"  • Time Remaining: {hours}h {minutes}m")
        
        # ====================================================================
        # NETWORK INFORMATION
        # ====================================================================
        output.append("\n🌐 NETWORK:")
        output.append("-" * 60)
        
        net_io = psutil.net_io_counters()
        output.append(f"  • Bytes Sent: {net_io.bytes_sent / (1024**2):.1f} MB")
        output.append(f"  • Bytes Received: {net_io.bytes_recv / (1024**2):.1f} MB")
        
        output.append("\n" + "=" * 60)
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"❌ Required library not installed: {str(e)}\nRun: pip install psutil GPUtil wmi"
    except Exception as e:
        return f"❌ Error getting system stats: {str(e)}"


# ============================================================================
# TOOL LIST
# ============================================================================

def get_all_tools() -> List:
    """
    Get list of all available tools.
    
    Returns:
        List of tool functions
    """
    return [
        # Terminal
        execute_terminal_command,
        
        # File System
        read_file,
        write_file,
        append_to_file,
        list_directory,
        delete_file,
        
        # Web
        search_web,
        fetch_webpage,
        
        # Advanced Web
        browse_website_interactive,
        
        # File Operations
        download_file,
        extract_archive,
        
        # Hardware Monitoring
        get_system_stats,
    ]
