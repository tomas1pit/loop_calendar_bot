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
    
    async def get_today_meetings(self, mattermost_id: str, user_email: str, 
                                 password: str) -> List[Dict]:
        """Получить все встречи на сегодня (async)"""
        tz_now = datetime.now(self.tz)
        start = tz_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        caldav = CalDAVManager(user_email, password)
        events: List[Dict] = []
        try:
            events = await caldav.get_events(start, end)
        except Exception:
            events = []
        finally:
            try:
                await caldav.close()
            except Exception:
                pass

        normalized: List[Dict] = []
        # Диагностика количества сырых событий
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Raw events fetched for {user_email}: count={len(events)} start={start.isoformat()} end={end.isoformat()}")
            for idx, evdbg in enumerate(events[:10]):
                logger.info(f"Event[{idx}] uid={evdbg.get('uid')} title={evdbg.get('title')} start={evdbg.get('start_time')} end={evdbg.get('end_time')}")
        except Exception:
            pass

        for ev in events:
            try:
                title = ev.get("title") or "Без названия"
                start_iso = ev.get("start_time") or ""
                end_iso = ev.get("end_time") or ""
                start_dt = datetime.fromisoformat(start_iso) if start_iso else tz_now
                end_dt = datetime.fromisoformat(end_iso) if end_iso else start_dt
                time_str = f"{start_dt.strftime('%d.%m %H:%M')}–{end_dt.strftime('%H:%M')}"
                status = ev.get("status") or "CONFIRMED"
                # Исключаем отменённые встречи из списка
                if status.upper() == "CANCELLED":
                    continue
                normalized.append({
                    "uid": ev.get("uid", ""),
                    "title": title,
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "time": time_str,
                    "status": status,
                    "attendees": ev.get("attendees", []),
                    "description": ev.get("description", ""),
                    "location": ev.get("location", ""),
                    "organizer": ev.get("organizer", ""),
                })
                try:
                    logger.debug(
                        f"Normalize uid={ev.get('uid')} title='{title}' start_raw='{start_iso}' end_raw='{end_iso}' start_parsed={start_dt} end_parsed={end_dt}"
                    )
                except Exception:
                    pass
            except Exception:
                continue
        try:
            logger.info(f"Normalized events for {user_email}: count={len(normalized)}")
        except Exception:
            pass
        return normalized
    
    async def get_current_meetings(self, mattermost_id: str, user_email: str,
                                   password: str) -> List[Dict]:
        """Получить текущие и будущие встречи на сегодня (async)"""
        all_today = await self.get_today_meetings(mattermost_id, user_email, password)
        now = datetime.now(self.tz)
        result: List[Dict] = []
        for m in all_today:
            try:
                start_dt = datetime.fromisoformat(m["start_time"])
                end_dt = datetime.fromisoformat(m["end_time"])
                status = (m.get("status") or "").upper()
                # Исключаем отменённые встречи
                if end_dt >= now and status != "CANCELLED":
                    result.append(m)
            except Exception:
                continue
        return result
    
    def format_meetings_table(self, meetings: List[Dict]) -> str:
        """Форматировать встречи в таблицу"""
        if not meetings:
            return "Встреч не найдено"
        status_map = {
            "ACCEPTED": "✅ Принято",
            "DECLINED": "❌ Отклонено",
            "TENTATIVE": "❓ Возможно",
            "NEEDS-ACTION": "⏳ Ожидает",
            "CONFIRMED": "✅ Подтверждено",
            "CANCELLED": "🚫 Отменено",
        }
        table = "| Встреча | Время | Статус |\n|---------|-------|--------|\n"
        for meeting in meetings:
            title = meeting.get('title', 'Без названия')
            time_str = meeting.get('time', '')
            raw_status = (meeting.get('status', 'ACCEPTED') or '').strip().upper()
            status = status_map.get(raw_status, raw_status or '—')
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
