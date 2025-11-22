import asyncio
from datetime import datetime, timedelta
import json
import re
from typing import Optional, List, Dict
import pytz
from config import Config
from database import DatabaseManager, User, UserState, MeetingCache
from encryption import EncryptionManager
from mattermost_manager import MattermostManager
from caldav_manager import CalDAVManager
from ui_messages import UIMessages, ButtonActions, create_main_menu_buttons


class BotLogic:
    def __init__(self, db_manager: DatabaseManager, mm_manager: MattermostManager):
        self.db = db_manager
        self.mm = mm_manager
        self.encryption = EncryptionManager()
        self.tz = pytz.timezone(Config.TZ)
    
    def get_user(self, mattermost_id: str) -> Optional[User]:
        """Получить пользователя из БД"""
        session = self.db.get_session()
        try:
            user = session.query(User).filter_by(mattermost_id=mattermost_id).first()
            return user
        finally:
            session.close()
    
    def create_user(self, mattermost_id: str, email: str, password: str) -> User:
        """Создать нового пользователя"""
        session = self.db.get_session()
        try:
            encrypted_password = self.encryption.encrypt(password)
            user = User(
                mattermost_id=mattermost_id,
                email=email,
                encrypted_password=encrypted_password
            )
            session.add(user)
            session.commit()
            return user
        finally:
            session.close()
    
    def delete_user(self, mattermost_id: str) -> bool:
        """Удалить пользователя"""
        session = self.db.get_session()
        try:
            user = session.query(User).filter_by(mattermost_id=mattermost_id).first()
            if user:
                session.delete(user)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def get_user_state(self, mattermost_id: str) -> Optional[UserState]:
        """Получить состояние пользователя"""
        session = self.db.get_session()
        try:
            state = session.query(UserState).filter_by(mattermost_id=mattermost_id).first()
            return state
        finally:
            session.close()
    
    def set_user_state(self, mattermost_id: str, state: str, data: Dict = None, 
                      message_id: str = None):
        """Установить состояние пользователя"""
        session = self.db.get_session()
        try:
            user_state = session.query(UserState).filter_by(mattermost_id=mattermost_id).first()
            
            if not user_state:
                user_state = UserState(mattermost_id=mattermost_id)
                session.add(user_state)
            
            user_state.state = state
            if data:
                user_state.data = json.dumps(data)
            if message_id:
                user_state.message_id = message_id
            
            session.commit()
        finally:
            session.close()
    
    def clear_user_state(self, mattermost_id: str):
        """Очистить состояние пользователя"""
        session = self.db.get_session()
        try:
            user_state = session.query(UserState).filter_by(mattermost_id=mattermost_id).first()
            if user_state:
                session.delete(user_state)
                session.commit()
        finally:
            session.close()
    
    def get_today_meetings(self, mattermost_id: str, user_email: str, 
                          password: str) -> List[Dict]:
        """Получить все встречи на сегодня"""
        # Здесь будет интеграция с CalDAV
        # На данный момент возвращаем пустой список
        return []
    
    def get_current_meetings(self, mattermost_id: str, user_email: str,
                            password: str) -> List[Dict]:
        """Получить текущие и будущие встречи на сегодня"""
        return []
    
    def format_meetings_table(self, meetings: List[Dict]) -> str:
        """Форматировать встречи в таблицу"""
        if not meetings:
            return "Встреч не найдено"
        
        table = "| Встреча | Время | Статус |\n|---------|-------|--------|\n"
        for meeting in meetings:
            title = meeting.get('title', 'Без названия')
            time_str = meeting.get('time', '')
            status = meeting.get('status', 'ACCEPTED')
            table += f"| {title} | {time_str} | {status} |\n"
        
        return table
    
    async def parse_attendees(self, text: str) -> List[str]:
        """Парсить список участников (@username и emails)"""
        attendees = []
        
        # Найти все @username
        usernames = re.findall(r'@(\w+)', text)
        for username in usernames:
            user = await self.mm.get_user_by_username(username)
            if user and user.get('email'):
                attendees.append(user['email'])
        
        # Найти все email адреса
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        attendees.extend(emails)
        
        # Удалить дубликаты
        return list(set(attendees))
    
    def validate_date(self, date_str: str) -> Optional[datetime]:
        """Валидировать дату в формате DD.MM.YYYY"""
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y")
            # Конвертировать в текущий timezone
            return self.tz.localize(dt)
        except:
            return None
    
    def validate_time(self, time_str: str) -> Optional[timedelta]:
        """Валидировать время в формате HH:MM"""
        try:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
            return time_obj
        except:
            return None
    
    def validate_minutes(self, minutes_str: str) -> Optional[int]:
        """Валидировать минуты"""
        try:
            minutes = int(minutes_str)
            if 1 <= minutes <= 1440:  # От 1 минуты до 24 часов
                return minutes
            return None
        except:
            return None
