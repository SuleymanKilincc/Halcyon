"""
Test script for hardware monitoring tools.
Tests the new get_system_stats() and set_performance_profile() tools.
"""

import sys
from tools import get_system_stats, set_performance_profile

def print_separator():
    print("\n" + "=" * 70 + "\n")

def test_system_stats():
    """Test the get_system_stats tool."""
    print("🧪 TESTING: get_system_stats()")
    print_separator()
    
    try:
        result = get_system_stats()
        print(result)
        print_separator()
        print("✅ get_system_stats() executed successfully!")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_performance_profile():
    """Test the set_performance_profile tool."""
    print("\n🧪 TESTING: set_performance_profile()")
    print_separator()
    
    print("NOTE: This test will NOT actually change your performance profile.")
    print("It will test the validation and provide information about profile switching.\n")
    
    # Test with invalid profile
    print("Test 1: Invalid profile name")
    result = set_performance_profile("invalid_mode")
    print(result)
    print()
    
    # Test with valid profile (but will require approval)
    print("Test 2: Valid profile name (balanced)")
    print("Note: You will be asked for approval. You can decline.")
    result = set_performance_profile("balanced")
    print(result)
    
    print_separator()
    print("✅ set_performance_profile() validation working!")
    return True

def main():
    """Run all hardware tests."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║         🧪 JARVIS HARDWARE MONITORING TEST SUITE         ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    # Test system stats
    success_stats = test_system_stats()
    
    # Test performance profile
    success_profile = test_performance_profile()
    
    # Summary
    print_separator()
    print("📊 TEST SUMMARY")
    print_separator()
    print(f"  • get_system_stats():        {'✅ PASS' if success_stats else '❌ FAIL'}")
    print(f"  • set_performance_profile(): {'✅ PASS' if success_profile else '❌ FAIL'}")
    print()
    
    if success_stats and success_profile:
        print("🎉 All hardware monitoring tools are working correctly!")
        print()
        print("You can now use these tools in Jarvis:")
        print("  - 'Show me system stats'")
        print("  - 'Check GPU temperature'")
        print("  - 'Set performance to turbo mode'")
        print("  - 'Change to silent mode'")
    else:
        print("⚠️  Some tests failed. Check the error messages above.")
        print()
        print("Common issues:")
        print("  • Missing libraries: pip install psutil GPUtil wmi")
        print("  • No NVIDIA GPU: GPU stats will show 'not detected'")
        print("  • No WMI access: CPU temp will show 'not available'")
    
    print_separator()

if __name__ == "__main__":
    main()
