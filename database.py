from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    mattermost_id = Column(String(50), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    encrypted_password = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserState(Base):
    """Модель состояния пользователя (для многошагового диалога)"""
    __tablename__ = "user_states"
    
    mattermost_id = Column(String(50), primary_key=True)
    state = Column(String(50))  # e.g., 'awaiting_title', 'awaiting_date', etc.
    data = Column(Text)  # JSON с данными для встречи
    message_id = Column(String(50))  # ID сообщения для обновления
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MeetingCache(Base):
    """Кэш встреч для отслеживания изменений"""
    __tablename__ = "meeting_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    uid = Column(String(500), nullable=False)  # Уникальный ID встречи в CalDAV
    title = Column(String(500), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    description = Column(Text)
    location = Column(String(500))
    organizer = Column(String(255))
    attendees = Column(Text)  # JSON список участников
    status = Column(String(20))  # CONFIRMED, CANCELLED, TENTATIVE
    hash_value = Column(String(100))  # Хэш для отслеживания изменений
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # Убедимся, что директория существует
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        return self.Session()
    
    def close(self):
        self.engine.dispose()
