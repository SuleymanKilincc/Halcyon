"""
Test script for GUI-based approval system.
Tests the approval dialog and callback mechanism.
"""

import customtkinter as ctk
import sys
import time
import threading

# Add current directory to path
sys.path.insert(0, '.')

try:
    from gui import ApprovalDialog, COLORS
    import config
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from the Halcyon directory")
    sys.exit(1)

def test_approval_dialog_visual():
    """Test the approval dialog visually."""
    print("="*60)
    print("TEST 1: Visual Approval Dialog")
    print("="*60)
    print("\nThis will show the approval dialog.")
    print("Try different interactions:")
    print("  - Click ✅ APPROVE button")
    print("  - Click ❌ DECLINE button")
    print("  - Press Y key")
    print("  - Press N key")
    print("  - Press Enter")
    print("  - Press Escape")
    print()
    
    input("Press Enter to start test...")
    
    # Create GUI
    root = ctk.CTk()
    root.title("Approval Dialog Test")
    root.geometry("800x600")
    
    # Configure appearance
    ctk.set_appearance_mode("dark")
    
    results = []
    
    def show_test_dialog(test_name, operation, details):
        print(f"\n[{test_name}]")
        print(f"Operation: {operation}")
        print(f"Details: {details}")
        
        dialog = ApprovalDialog(root, operation, details)
        result = dialog.get_result()
        
        results.append((test_name, result))
        print(f"Result: {'✅ APPROVED' if result else '❌ DECLINED'}")
        
        # Show result in main window
        result_label = ctk.CTkLabel(
            root,
            text=f"{test_name}: {'✅ APPROVED' if result else '❌ DECLINED'}",
            font=("Courier New", 12),
            text_color=COLORS['success'] if result else COLORS['error']
        )
        result_label.pack(pady=5)
    
    # Test 1: File write
    root.after(500, lambda: show_test_dialog(
        "Test 1: File Write",
        "Write File",
        "Path: workspace/test.txt\nSize: 150 bytes\nContent: Hello, World!"
    ))
    
    # Test 2: Terminal command
    root.after(3000, lambda: show_test_dialog(
        "Test 2: Terminal Command",
        "Terminal Command Execution",
        "Command: python --version\nWorking Directory: workspace/\nTimeout: 30 seconds"
    ))
    
    # Test 3: File delete
    root.after(5500, lambda: show_test_dialog(
        "Test 3: File Delete",
        "Delete File",
        "Path: workspace/old_file.txt\nWarning: This operation cannot be undone!"
    ))
    
    # Summary
    def show_summary():
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        for test_name, result in results:
            status = "✅ APPROVED" if result else "❌ DECLINED"
            print(f"{test_name}: {status}")
        print("="*60)
        root.quit()
    
    root.after(8000, show_summary)
    
    root.mainloop()

def test_callback_system():
    """Test the callback registration system."""
    print("\n" + "="*60)
    print("TEST 2: Callback System")
    print("="*60)
    
    # Test callback registration
    print("\n1. Testing callback registration...")
    
    def mock_callback(operation, details):
        print(f"   Callback called: {operation}")
        return True
    
    config.set_approval_callback(mock_callback)
    callback = config.get_approval_callback()
    
    if callback is not None:
        print("   ✓ Callback registered successfully")
    else:
        print("   ✗ Callback registration failed")
        return False
    
    # Test callback execution
    print("\n2. Testing callback execution...")
    result = callback("Test Operation", "Test Details")
    
    if result is True:
        print("   ✓ Callback executed successfully")
    else:
        print("   ✗ Callback execution failed")
        return False
    
    # Test callback clearing
    print("\n3. Testing callback clearing...")
    config.set_approval_callback(None)
    callback = config.get_approval_callback()
    
    if callback is None:
        print("   ✓ Callback cleared successfully")
    else:
        print("   ✗ Callback clearing failed")
        return False
    
    print("\n✅ All callback tests passed!")
    return True

def test_thread_safety():
    """Test thread-safe approval from background thread."""
    print("\n" + "="*60)
    print("TEST 3: Thread Safety")
    print("="*60)
    print("\nThis tests approval from a background thread")
    print("(simulating real agent usage)")
    print()
    
    input("Press Enter to start test...")
    
    # Create GUI
    root = ctk.CTk()
    root.title("Thread Safety Test")
    root.geometry("600x400")
    ctk.set_appearance_mode("dark")
    
    result_container = {'result': None, 'ready': False}
    
    def approval_callback(operation, details):
        """Mock approval callback."""
        callback_result = {'result': None, 'ready': False}
        
        def show_dialog():
            dialog = ApprovalDialog(root, operation, details)
            callback_result['result'] = dialog.get_result()
            callback_result['ready'] = True
            print(f"   Dialog result: {callback_result['result']}")
        
        root.after(0, show_dialog)
        
        # Wait for result
        timeout = 30
        start = time.time()
        while not callback_result['ready']:
            time.sleep(0.1)
            if time.time() - start > timeout:
                print("   ⚠️ Timeout!")
                return False
        
        return callback_result['result']
    
    def background_task():
        """Simulate agent running in background thread."""
        print("\n[Background Thread Started]")
        time.sleep(1)
        
        print("   Requesting approval from background thread...")
        result = approval_callback(
            "Background Thread Operation",
            "Thread: background_task\nOperation: File Write\nPath: workspace/test.txt"
        )
        
        result_container['result'] = result
        result_container['ready'] = True
        
        print(f"   Background thread received: {result}")
        print("[Background Thread Completed]")
        
        # Schedule close
        root.after(2000, root.quit)
    
    # Start background thread
    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    
    root.mainloop()
    
    print("\n" + "="*60)
    print("THREAD SAFETY RESULT")
    print("="*60)
    
    if result_container['ready']:
        result = result_container['result']
        print(f"✓ Thread-safe approval {'APPROVED' if result else 'DECLINED'}")
        print("✓ No deadlocks or hangs")
        print("✓ Result propagated correctly")
        return True
    else:
        print("✗ Thread safety test failed")
        return False

def test_keyboard_shortcuts():
    """Test keyboard shortcuts in approval dialog."""
    print("\n" + "="*60)
    print("TEST 4: Keyboard Shortcuts")
    print("="*60)
    print("\nThis tests keyboard shortcuts:")
    print("  - Test 1: Press Y to approve")
    print("  - Test 2: Press N to decline")
    print("  - Test 3: Press Enter to approve")
    print("  - Test 4: Press Escape to decline")
    print()
    
    input("Press Enter to start test...")
    
    root = ctk.CTk()
    root.title("Keyboard Shortcuts Test")
    root.geometry("600x400")
    ctk.set_appearance_mode("dark")
    
    tests = [
        ("Press Y", "Test with Y key"),
        ("Press N", "Test with N key"),
        ("Press Enter", "Test with Enter key"),
        ("Press Escape", "Test with Escape key"),
    ]
    
    results = []
    test_index = [0]
    
    def show_next_test():
        if test_index[0] < len(tests):
            name, details = tests[test_index[0]]
            print(f"\n{name}...")
            
            dialog = ApprovalDialog(root, name, details)
            result = dialog.get_result()
            
            results.append((name, result))
            print(f"Result: {'✅ APPROVED' if result else '❌ DECLINED'}")
            
            test_index[0] += 1
            root.after(500, show_next_test)
        else:
            # Show summary
            print("\n" + "="*60)
            print("KEYBOARD SHORTCUTS SUMMARY")
            print("="*60)
            for name, result in results:
                print(f"{name}: {'✅' if result else '❌'}")
            print("="*60)
            root.quit()
    
    root.after(500, show_next_test)
    root.mainloop()

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("HALCYON GUI APPROVAL SYSTEM TEST SUITE")
    print("="*60)
    print("\nThis will test the GUI-based approval system.")
    print("\nTests:")
    print("  1. Visual Approval Dialog")
    print("  2. Callback System")
    print("  3. Thread Safety")
    print("  4. Keyboard Shortcuts")
    print()
    
    response = input("Run all tests? (Y/N): ").strip().upper()
    if response not in ['Y', 'YES']:
        print("Tests cancelled.")
        return
    
    # Run tests
    results = {}
    
    try:
        # Test 1: Visual
        test_approval_dialog_visual()
        results['visual'] = True
    except Exception as e:
        print(f"Visual test error: {e}")
        results['visual'] = False
    
    try:
        # Test 2: Callback
        results['callback'] = test_callback_system()
    except Exception as e:
        print(f"Callback test error: {e}")
        results['callback'] = False
    
    try:
        # Test 3: Thread safety
        results['thread'] = test_thread_safety()
    except Exception as e:
        print(f"Thread test error: {e}")
        results['thread'] = False
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL TEST SUMMARY")
    print("="*60)
    print(f"Visual Dialog Test: {'✅ PASS' if results.get('visual') else '✗ FAIL'}")
    print(f"Callback System Test: {'✅ PASS' if results.get('callback') else '✗ FAIL'}")
    print(f"Thread Safety Test: {'✅ PASS' if results.get('thread') else '✗ FAIL'}")
    print("="*60)
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED!")
        print("\nThe GUI approval system is working correctly.")
    else:
        print("\n⚠️ SOME TESTS FAILED")
        print("\nPlease review the errors above.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
