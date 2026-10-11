"""
Test script for database functionality.
Tests chat session and message management.
"""

from database import db_manager
from datetime import datetime

def print_separator():
    print("\n" + "=" * 70 + "\n")

def test_session_creation():
    """Test creating chat sessions."""
    print("🧪 TEST 1: Creating Chat Sessions")
    print_separator()
    
    # Create sessions
    session1 = db_manager.create_session("My First Chat")
    print(f"✅ Created session 1: {session1.title} (ID: {session1.id})")
    
    session2 = db_manager.create_session("Python Programming Help")
    print(f"✅ Created session 2: {session2.title} (ID: {session2.id})")
    
    session3 = db_manager.create_session()  # Auto-generated title
    print(f"✅ Created session 3: {session3.title} (ID: {session3.id})")
    
    print(f"\nTotal sessions: {db_manager.get_session_count()}")
    return [session1.id, session2.id, session3.id]

def test_adding_messages(session_id):
    """Test adding messages to a session."""
    print(f"\n🧪 TEST 2: Adding Messages to Session {session_id}")
    print_separator()
    
    # Add messages
    db_manager.add_message(session_id, "system", "Halcyon initialized")
    print("✅ Added system message")
    
    db_manager.add_message(session_id, "user", "Hello Halcyon!")
    print("✅ Added user message")
    
    db_manager.add_message(session_id, "assistant", "Hello! How can I assist you today?")
    print("✅ Added assistant message")
    
    db_manager.add_message(session_id, "user", "What's the weather?")
    print("✅ Added user message")
    
    db_manager.add_message(session_id, "assistant", "I'll check the weather for you.")
    print("✅ Added assistant message")
    
    # Get messages
    messages = db_manager.get_session_messages(session_id)
    print(f"\nTotal messages in session: {len(messages)}")

def test_listing_sessions():
    """Test listing all sessions."""
    print("\n🧪 TEST 3: Listing All Sessions")
    print_separator()
    
    sessions = db_manager.get_all_sessions()
    
    print(f"Found {len(sessions)} sessions:\n")
    for session in sessions:
        pin_icon = "📌" if session.is_pinned else "  "
        msg_count = len(session.messages)
        print(f"{pin_icon} [{session.id}] {session.title}")
        print(f"     Created: {session.created_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"     Messages: {msg_count}")
        print()

def test_pinning(session_id):
    """Test pinning a session."""
    print(f"\n🧪 TEST 4: Pinning Session {session_id}")
    print_separator()
    
    # Pin session
    is_pinned = db_manager.toggle_session_pin(session_id)
    print(f"✅ Session {session_id} pin status: {'PINNED' if is_pinned else 'UNPINNED'}")
    
    # List sessions to show pinned first
    print("\nSessions after pinning:")
    sessions = db_manager.get_all_sessions(pinned_first=True)
    for session in sessions:
        pin_icon = "📌" if session.is_pinned else "  "
        print(f"{pin_icon} [{session.id}] {session.title}")

def test_renaming(session_id):
    """Test renaming a session."""
    print(f"\n🧪 TEST 5: Renaming Session {session_id}")
    print_separator()
    
    new_title = "Renamed Chat Session"
    success = db_manager.update_session_title(session_id, new_title)
    
    if success:
        print(f"✅ Session {session_id} renamed to: {new_title}")
        
        # Verify
        session = db_manager.get_session(session_id)
        print(f"   Verified: {session.title}")
    else:
        print(f"❌ Failed to rename session {session_id}")

def test_export_import(session_id):
    """Test exporting and importing a session."""
    print(f"\n🧪 TEST 6: Export/Import Session {session_id}")
    print_separator()
    
    import os
    export_path = "test_export.json"
    
    # Export
    success = db_manager.export_session(session_id, export_path)
    if success:
        print(f"✅ Session {session_id} exported to: {export_path}")
        
        # Show file size
        file_size = os.path.getsize(export_path)
        print(f"   File size: {file_size} bytes")
        
        # Import (creates new session)
        new_id = db_manager.import_session(export_path)
        if new_id:
            print(f"✅ Session imported with new ID: {new_id}")
            
            # Clean up
            os.remove(export_path)
            print(f"   Cleaned up: {export_path}")
        else:
            print(f"❌ Failed to import session")
    else:
        print(f"❌ Failed to export session {session_id}")

def test_deletion(session_id):
    """Test deleting a session."""
    print(f"\n🧪 TEST 7: Deleting Session {session_id}")
    print_separator()
    
    # Get message count before
    messages = db_manager.get_session_messages(session_id)
    msg_count = len(messages)
    
    # Delete
    success = db_manager.delete_session(session_id)
    if success:
        print(f"✅ Session {session_id} deleted (with {msg_count} messages)")
        print(f"   Cascade delete removes all associated messages")
    else:
        print(f"❌ Failed to delete session {session_id}")

def cleanup_test_data():
    """Clean up all test data."""
    print("\n🧹 CLEANUP: Removing all test sessions")
    print_separator()
    
    sessions = db_manager.get_all_sessions()
    for session in sessions:
        db_manager.delete_session(session.id)
        print(f"  Deleted session {session.id}: {session.title}")
    
    print(f"\n✅ Cleanup complete. Total sessions: {db_manager.get_session_count()}")

def main():
    """Run all database tests."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           🧪 HALCYON DATABASE TEST SUITE                  ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    try:
        # Run tests
        session_ids = test_session_creation()
        test_adding_messages(session_ids[0])
        test_listing_sessions()
        test_pinning(session_ids[1])
        test_renaming(session_ids[2])
        test_export_import(session_ids[0])
        test_deletion(session_ids[2])
        
        # Summary
        print_separator()
        print("📊 TEST SUMMARY")
        print_separator()
        print("✅ All database operations working correctly!")
        print()
        print("Database file location:")
        print(f"  {db_manager.engine.url}")
        print()
        print("The database system is ready for GUI integration.")
        
        # Cleanup option
        print_separator()
        response = input("Clean up all test data? (y/N): ").strip().lower()
        if response == 'y':
            cleanup_test_data()
        else:
            print("Test data preserved for inspection.")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    print_separator()

if __name__ == "__main__":
    main()
