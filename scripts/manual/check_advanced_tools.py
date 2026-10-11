"""
Test script for advanced tools (web automation, downloads, archives).
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, '.')

def test_imports():
    """Test if all required libraries are installed."""
    print("="*60)
    print("TEST 1: Import Dependencies")
    print("="*60)
    
    results = {}
    
    # Test Playwright
    print("\n1. Testing Playwright...")
    try:
        from playwright.sync_api import sync_playwright
        print("   ✓ Playwright imported successfully")
        results['playwright'] = True
    except ImportError as e:
        print(f"   ✗ Playwright import failed: {e}")
        print("     Install: pip install playwright && playwright install chromium")
        results['playwright'] = False
    
    # Test py7zr
    print("\n2. Testing py7zr (7z support)...")
    try:
        import py7zr
        print("   ✓ py7zr imported successfully")
        results['py7zr'] = True
    except ImportError as e:
        print(f"   ✗ py7zr import failed: {e}")
        print("     Install: pip install py7zr")
        results['py7zr'] = False
    
    # Test requests
    print("\n3. Testing requests...")
    try:
        import requests
        print("   ✓ requests imported successfully")
        results['requests'] = True
    except ImportError as e:
        print(f"   ✗ requests import failed: {e}")
        results['requests'] = False
    
    # Test zipfile (built-in)
    print("\n4. Testing zipfile...")
    try:
        import zipfile
        print("   ✓ zipfile available (built-in)")
        results['zipfile'] = True
    except ImportError:
        print("   ✗ zipfile not available")
        results['zipfile'] = False
    
    # Test tarfile (built-in)
    print("\n5. Testing tarfile...")
    try:
        import tarfile
        print("   ✓ tarfile available (built-in)")
        results['tarfile'] = True
    except ImportError:
        print("   ✗ tarfile not available")
        results['tarfile'] = False
    
    return results

def test_tools_import():
    """Test if tools can be imported."""
    print("\n" + "="*60)
    print("TEST 2: Import Tools")
    print("="*60)
    
    try:
        from tools import (
            browse_website_interactive,
            download_file,
            extract_archive,
            get_all_tools
        )
        print("\n✓ All new tools imported successfully")
        
        # Count tools
        all_tools = get_all_tools()
        print(f"\nTotal tools available: {len(all_tools)}")
        print("\nNew advanced tools:")
        print("  1. browse_website_interactive")
        print("  2. download_file")
        print("  3. extract_archive")
        
        return True
    except ImportError as e:
        print(f"\n✗ Tool import failed: {e}")
        return False

def test_playwright_browser():
    """Test if Playwright can launch browser."""
    print("\n" + "="*60)
    print("TEST 3: Playwright Browser Test")
    print("="*60)
    
    try:
        from playwright.sync_api import sync_playwright
        
        print("\nAttempting to launch Chromium...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            print("✓ Browser launched successfully")
            
            page = browser.new_page()
            print("✓ Page created")
            
            # Test navigation
            print("\nTesting navigation to example.com...")
            page.goto("https://example.com", timeout=10000)
            print("✓ Navigation successful")
            
            # Get title
            title = page.title()
            print(f"✓ Page title: {title}")
            
            browser.close()
            print("✓ Browser closed")
        
        return True
        
    except ImportError:
        print("✗ Playwright not installed")
        print("  Install: pip install playwright")
        return False
    except Exception as e:
        print(f"✗ Browser test failed: {e}")
        if "Executable doesn't exist" in str(e):
            print("  Chromium not installed")
            print("  Install: playwright install chromium")
        return False

def test_download_capability():
    """Test download capability (without actually downloading)."""
    print("\n" + "="*60)
    print("TEST 4: Download Capability")
    print("="*60)
    
    try:
        import requests
        
        print("\nTesting HEAD request to example.com...")
        response = requests.head("https://example.com", timeout=5)
        
        if response.status_code == 200:
            print("✓ Connection successful")
            print(f"  Status: {response.status_code}")
            return True
        else:
            print(f"⚠️ Unexpected status: {response.status_code}")
            return False
            
    except requests.RequestException as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_archive_formats():
    """Test archive format support."""
    print("\n" + "="*60)
    print("TEST 5: Archive Format Support")
    print("="*60)
    
    formats = {
        'ZIP': ('zipfile', 'zipfile'),
        'TAR': ('tarfile', 'tarfile'),
        'TAR.GZ': ('tarfile', 'tarfile'),
        '7Z': ('py7zr', 'py7zr'),
    }
    
    results = {}
    
    for format_name, (module_name, display_name) in formats.items():
        try:
            __import__(module_name)
            print(f"✓ {format_name} support available ({display_name})")
            results[format_name] = True
        except ImportError:
            print(f"✗ {format_name} support missing ({display_name})")
            results[format_name] = False
    
    return all(results.values())

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("HALCYON ADVANCED TOOLS TEST SUITE")
    print("="*60)
    print("\nThis will test the new advanced tools:")
    print("  - Web Automation (Playwright)")
    print("  - File Downloads (requests)")
    print("  - Archive Extraction (zipfile, tarfile, py7zr)")
    print()
    
    results = {}
    
    # Test 1: Imports
    import_results = test_imports()
    results['imports'] = all(import_results.values())
    
    # Test 2: Tools import
    results['tools'] = test_tools_import()
    
    # Test 3: Playwright
    if import_results.get('playwright', False):
        results['playwright'] = test_playwright_browser()
    else:
        print("\n⊘ Skipping Playwright test (not installed)")
        results['playwright'] = False
    
    # Test 4: Downloads
    if import_results.get('requests', False):
        results['download'] = test_download_capability()
    else:
        print("\n⊘ Skipping download test (requests not installed)")
        results['download'] = False
    
    # Test 5: Archives
    results['archives'] = test_archive_formats()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Dependencies Import: {'✅ PASS' if results['imports'] else '✗ FAIL'}")
    print(f"Tools Import: {'✅ PASS' if results['tools'] else '✗ FAIL'}")
    print(f"Playwright Browser: {'✅ PASS' if results['playwright'] else '✗ FAIL'}")
    print(f"Download Capability: {'✅ PASS' if results['download'] else '✗ FAIL'}")
    print(f"Archive Support: {'✅ PASS' if results['archives'] else '✗ FAIL'}")
    print("="*60)
    
    # Overall result
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED!")
        print("\nAll advanced tools are ready to use.")
        print("Launch Halcyon: python gui.py")
    else:
        print("\n⚠️ SOME TESTS FAILED")
        print("\nPlease install missing dependencies:")
        
        if not results['imports']:
            print("\n1. Install dependencies:")
            print("   pip install -r requirements.txt")
        
        if not results['playwright']:
            print("\n2. Install Playwright:")
            print("   pip install playwright")
            print("   playwright install chromium")
        
        print("\nThen run this test again: python test_advanced_tools.py")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
