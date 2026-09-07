"""
Database module for Jarvis AI Agent.
Manages chat sessions and conversation history using SQLAlchemy.
"""

import os
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import json

import config

# ============================================================================
# DATABASE SETUP
# ============================================================================

Base = declarative_base()

# Database file path
DB_PATH = config.BASE_DIR / "jarvis_sessions.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ============================================================================
# DATABASE MODELS
# ============================================================================

class ChatSession(Base):
    """Chat session model."""
    
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    
    # Relationship to messages
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict:
        """Convert session to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_pinned": self.is_pinned,
            "message_count": len(self.messages) if self.messages else 0
        }

class ChatMessage(Base):
    """Chat message model."""
    
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship to session
    session = relationship("ChatSession", back_populates="messages")
    
    def to_dict(self) -> Dict:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Manages database operations for chat sessions."""
    
    def __init__(self):
        """Initialize database connection."""
        self.engine = create_engine(DATABASE_URL, echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    # ========================================================================
    # SESSION OPERATIONS
    # ========================================================================
    
    def create_session(self, title: str = None) -> ChatSession:
        """
        Create a new chat session.
        
        Args:
            title: Optional session title (auto-generated if not provided)
            
        Returns:
            ChatSession object
        """
        session = self.Session()
        try:
            if not title:
                # Auto-generate title with timestamp
                title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            chat_session = ChatSession(title=title)
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            
            return chat_session
            
        finally:
            session.close()
    
    def get_session(self, session_id: int) -> Optional[ChatSession]:
        """
        Get a chat session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            ChatSession object or None
        """
        session = self.Session()
        try:
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if chat_session:
                # Load messages
                _ = chat_session.messages
            return chat_session
            
        finally:
            session.close()
    
    def get_all_sessions(self, pinned_first: bool = True) -> List[ChatSession]:
        """
        Get all chat sessions.
        
        Args:
            pinned_first: If True, pinned sessions appear first
            
        Returns:
            List of ChatSession objects
        """
        session = self.Session()
        try:
            query = session.query(ChatSession)
            
            if pinned_first:
                query = query.order_by(
                    ChatSession.is_pinned.desc(),
                    ChatSession.updated_at.desc()
                )
            else:
                query = query.order_by(ChatSession.updated_at.desc())
            
            sessions = query.all()
            
            # Load messages for each session
            for chat_session in sessions:
                _ = chat_session.messages
            
            return sessions
            
        finally:
            session.close()
    
    def update_session_title(self, session_id: int, new_title: str) -> bool:
        """
        Update session title.
        
        Args:
            session_id: Session ID
            new_title: New title
            
        Returns:
            True if successful
        """
        session = self.Session()
        try:
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if chat_session:
                chat_session.title = new_title
                chat_session.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
            
        finally:
            session.close()
    
    def toggle_session_pin(self, session_id: int) -> bool:
        """
        Toggle session pin status.
        
        Args:
            session_id: Session ID
            
        Returns:
            New pin status
        """
        session = self.Session()
        try:
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if chat_session:
                chat_session.is_pinned = not chat_session.is_pinned
                session.commit()
                return chat_session.is_pinned
            return False
            
        finally:
            session.close()
    
    def delete_session(self, session_id: int) -> bool:
        """
        Delete a chat session and all its messages.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if successful
        """
        session = self.Session()
        try:
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if chat_session:
                session.delete(chat_session)
                session.commit()
                return True
            return False
            
        finally:
            session.close()
    
    # ========================================================================
    # MESSAGE OPERATIONS
    # ========================================================================
    
    def add_message(self, session_id: int, role: str, content: str) -> Optional[ChatMessage]:
        """
        Add a message to a session.
        
        Args:
            session_id: Session ID
            role: Message role ("user", "assistant", "system")
            content: Message content
            
        Returns:
            ChatMessage object or None
        """
        session = self.Session()
        try:
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if not chat_session:
                return None
            
            message = ChatMessage(
                session_id=session_id,
                role=role,
                content=content
            )
            session.add(message)
            
            # Update session timestamp
            chat_session.updated_at = datetime.utcnow()
            
            session.commit()
            session.refresh(message)
            
            return message
            
        finally:
            session.close()
    
    def get_session_messages(self, session_id: int) -> List[ChatMessage]:
        """
        Get all messages for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of ChatMessage objects
        """
        session = self.Session()
        try:
            messages = session.query(ChatMessage).filter_by(
                session_id=session_id
            ).order_by(ChatMessage.timestamp).all()
            
            return messages
            
        finally:
            session.close()
    
    def clear_session_messages(self, session_id: int) -> bool:
        """
        Clear all messages in a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if successful
        """
        session = self.Session()
        try:
            session.query(ChatMessage).filter_by(session_id=session_id).delete()
            
            # Update session timestamp
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if chat_session:
                chat_session.updated_at = datetime.utcnow()
            
            session.commit()
            return True
            
        finally:
            session.close()
    
    # ========================================================================
    # UTILITY OPERATIONS
    # ========================================================================
    
    def get_session_count(self) -> int:
        """Get total number of sessions."""
        session = self.Session()
        try:
            return session.query(ChatSession).count()
        finally:
            session.close()
    
    def export_session(self, session_id: int, export_path: str) -> bool:
        """
        Export a session to JSON file.
        
        Args:
            session_id: Session ID
            export_path: Path to export file
            
        Returns:
            True if successful
        """
        try:
            chat_session = self.get_session(session_id)
            if not chat_session:
                return False
            
            export_data = {
                "session": chat_session.to_dict(),
                "messages": [msg.to_dict() for msg in chat_session.messages]
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"Export error: {e}")
            return False
    
    def import_session(self, import_path: str) -> Optional[int]:
        """
        Import a session from JSON file.
        
        Args:
            import_path: Path to import file
            
        Returns:
            New session ID or None
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Create new session
            session_data = import_data["session"]
            new_session = self.create_session(title=session_data["title"])
            
            # Import messages
            for msg_data in import_data["messages"]:
                self.add_message(
                    new_session.id,
                    msg_data["role"],
                    msg_data["content"]
                )
            
            return new_session.id
            
        except Exception as e:
            print(f"Import error: {e}")
            return None

# ============================================================================
# GLOBAL DATABASE INSTANCE
# ============================================================================

# Initialize global database manager
db_manager = DatabaseManager()

