import asyncio
import logging
from datetime import datetime, timedelta
import json
from typing import List, Dict, Optional
import pytz
from config import Config
from database import DatabaseManager, MeetingCache
from encryption import EncryptionManager
from caldav_manager import CalDAVManager
from mattermost_manager import MattermostManager
from ui_messages import UIMessages

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self, db: DatabaseManager, mm: MattermostManager):
        self.db = db
        self.mm = mm
        self.encryption = EncryptionManager()
        self.tz = pytz.timezone(Config.TZ)
    
    async def check_and_notify(self, users: List) -> int:
        """
        Проверить изменения встреч и отправить уведомления
        Возвращает количество отправленных уведомлений
        """
        notification_count = 0
        
        for user in users:
            try:
                # Получить пароль пользователя
                password = self.encryption.decrypt(user.encrypted_password)
                if not password:
                    logger.warning(f"Could not decrypt password for user {user.mattermost_id}")
                    continue
                
                # Создать менеджер CalDAV
                caldav_manager = CalDAVManager(user.email, password)
                
                # Получить встречи на сегодня и завтра
                today = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = today + timedelta(days=1)
                tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)
                
                # TODO: Получить события из CalDAV
                current_events = []  # await caldav_manager.get_events(...)
                
                # Получить кэшированные события
                cached_events = self._get_cached_events(user.mattermost_id, today, tomorrow_end)
                
                # Найти добавленные события
                for event in current_events:
                    if not self._is_event_cached(event, cached_events):
                        # Новое событие
                        if self._is_today_or_tomorrow(event, today):
                            await self._notify_new_meeting(user, event)
                            notification_count += 1
                
                # Найти удаленные или отмененные события
                for cached in cached_events:
                    if cached.status != "CANCELLED" and not self._is_event_in_current(cached, current_events):
                        # Событие было отменено или удалено
                        if self._is_today_or_tomorrow_from_cache(cached, today):
                            await self._notify_cancelled_meeting(user, cached)
                            notification_count += 1
                
                # Найти перенесенные события
                for cached in cached_events:
                    current_version = self._find_event_by_uid(cached.uid, current_events)
                    if current_version and self._event_changed_time(cached, current_version):
                        if self._is_today_or_tomorrow(current_version, today):
                            await self._notify_rescheduled_meeting(user, cached, current_version)
                            notification_count += 1
                
                # Обновить кэш
                self._update_events_cache(user.mattermost_id, current_events)
                
                # Проверить напоминания
                reminders_sent = await self._check_reminders(user, current_events)
                notification_count += reminders_sent
                
                await caldav_manager.close()
            
            except Exception as e:
                logger.error(f"Error checking notifications for user {user.mattermost_id}: {e}")
        
        return notification_count
    
    def _get_cached_events(self, user_id: str, start_date: datetime, 
                          end_date: datetime) -> List[MeetingCache]:
        """Получить кэшированные события"""
        session = self.db.get_session()
        try:
            events = session.query(MeetingCache).filter(
                MeetingCache.user_id == user_id,
                MeetingCache.start_time >= start_date,
                MeetingCache.start_time <= end_date
            ).all()
            return events
        finally:
            session.close()
    
    def _is_event_cached(self, event: Dict, cached_events: List[MeetingCache]) -> bool:
        """Проверить, кэшировано ли событие"""
        for cached in cached_events:
            if cached.uid == event.get('uid'):
                return True
        return False
    
    def _is_event_in_current(self, cached: MeetingCache, current_events: List[Dict]) -> bool:
        """Проверить, есть ли кэшированное событие в текущих"""
        for event in current_events:
            if event.get('uid') == cached.uid:
                return True
        return False
    
    def _find_event_by_uid(self, uid: str, events: List[Dict]) -> Optional[Dict]:
        """Найти событие по UID"""
        for event in events:
            if event.get('uid') == uid:
                return event
        return None
    
    def _event_changed_time(self, cached: MeetingCache, current: Dict) -> bool:
        """Проверить, изменилось ли время события"""
        current_start = datetime.fromisoformat(current.get('start_time', ''))
        current_end = datetime.fromisoformat(current.get('end_time', ''))
        
        return (cached.start_time != current_start or cached.end_time != current_end)
    
    def _is_today_or_tomorrow(self, event: Dict, today: datetime) -> bool:
        """Проверить, событие ли это на сегодня или завтра"""
        start_time = datetime.fromisoformat(event.get('start_time', ''))
        tomorrow = today + timedelta(days=1)
        
        return start_time.date() in [today.date(), tomorrow.date()]
    
    def _is_today_or_tomorrow_from_cache(self, cached: MeetingCache, today: datetime) -> bool:
        """Проверить, кэшировано ли событие на сегодня или завтра"""
        tomorrow = today + timedelta(days=1)
        return cached.start_time.date() in [today.date(), tomorrow.date()]
    
    def _update_events_cache(self, user_id: str, events: List[Dict]):
        """Обновить кэш событий"""
        session = self.db.get_session()
        try:
            # Очистить старый кэш
            session.query(MeetingCache).filter_by(user_id=user_id).delete()
            
            # Добавить новые события
            for event in events:
                cache = MeetingCache(
                    user_id=user_id,
                    uid=event.get('uid', ''),
                    title=event.get('title', ''),
                    start_time=datetime.fromisoformat(event.get('start_time', '')),
                    end_time=datetime.fromisoformat(event.get('end_time', '')),
                    description=event.get('description', ''),
                    location=event.get('location', ''),
                    organizer=event.get('organizer', ''),
                    attendees=json.dumps(event.get('attendees', [])),
                    status=event.get('status', 'CONFIRMED'),
                    hash_value=CalDAVManager.hash_event(event)
                )
                session.add(cache)
            
            session.commit()
        finally:
            session.close()
    
    async def _check_reminders(self, user, events: List[Dict]) -> int:
        """Проверить и отправить напоминания"""
        reminder_count = 0
        
        try:
            channel_id = self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return 0
            
            now = datetime.now(self.tz)
            reminder_delta = timedelta(minutes=Config.REMINDER_MINUTES)
            
            for event in events:
                start_time = datetime.fromisoformat(event.get('start_time', ''))
                time_until = start_time - now
                
                # Проверить, является ли это нашим временем напоминания
                if timedelta(0) <= time_until <= reminder_delta:
                    message = UIMessages.reminder_notification(
                        event.get('title', ''),
                        start_time,
                        event.get('location', '')
                    )
                    self.mm.send_message(channel_id, message)
                    reminder_count += 1
        
        except Exception as e:
            logger.error(f"Error checking reminders: {e}")
        
        return reminder_count
    
    async def _notify_new_meeting(self, user, event: Dict):
        """Отправить уведомление о новой встрече"""
        try:
            channel_id = self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return
            
            message = UIMessages.new_meeting_notification(
                event.get('title', ''),
                datetime.fromisoformat(event.get('start_time', '')),
                datetime.fromisoformat(event.get('end_time', '')),
                event.get('attendees', []),
                event.get('description', ''),
                event.get('location', '')
            )
            
            self.mm.send_message(channel_id, message)
            logger.info(f"Sent new meeting notification to {user.mattermost_id}")
        
        except Exception as e:
            logger.error(f"Error sending new meeting notification: {e}")
    
    async def _notify_cancelled_meeting(self, user, cached: MeetingCache):
        """Отправить уведомление об отмене встречи"""
        try:
            channel_id = self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return
            
            message = UIMessages.meeting_cancelled(
                cached.title,
                cached.start_time,
                cached.end_time
            )
            
            self.mm.send_message(channel_id, message)
            logger.info(f"Sent cancellation notification to {user.mattermost_id}")
        
        except Exception as e:
            logger.error(f"Error sending cancellation notification: {e}")
    
    async def _notify_rescheduled_meeting(self, user, cached: MeetingCache, new_event: Dict):
        """Отправить уведомление о переносе встречи"""
        try:
            channel_id = self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return
            
            message = UIMessages.meeting_rescheduled(
                cached.title,
                cached.start_time,
                cached.end_time,
                datetime.fromisoformat(new_event.get('start_time', '')),
                datetime.fromisoformat(new_event.get('end_time', ''))
            )
            
            self.mm.send_message(channel_id, message)
            logger.info(f"Sent rescheduled notification to {user.mattermost_id}")
        
        except Exception as e:
            logger.error(f"Error sending rescheduled notification: {e}")
