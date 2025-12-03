import logging
from datetime import datetime, timedelta
import json
from typing import List, Dict, Iterable
import pytz
from config import Config
from database import DatabaseManager, MeetingCache, DailyDigestLog
from encryption import EncryptionManager
from caldav_manager import CalDAVManager
from mattermost_manager import MattermostManager
from ui_messages import UIMessages

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self, db: DatabaseManager, mm: MattermostManager, logic):
        self.db = db
        self.mm = mm
        self.logic = logic
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
                try:
                    # Получить встречи на сегодня и завтра
                    today = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
                    tomorrow = today + timedelta(days=1)
                    tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)

                    # Получить события из CalDAV
                    current_events = await caldav_manager.get_events(today, tomorrow_end)
                    current_events_map: Dict[str, Dict] = {
                        ev.get('uid', ''): ev for ev in current_events if ev.get('uid')
                    }
                    request_ok = getattr(caldav_manager, "last_events_ok", bool(current_events_map))
                    if not request_ok:
                        logger.warning(
                            "CalDAV request for %s returned only error statuses; skip cancellation detection (statuses=%s)",
                            user.email,
                            getattr(caldav_manager, "last_events_statuses", [])
                        )

                    # Получить кэшированные события
                    cached_events_map = self._get_cached_events_map(user.mattermost_id, today, tomorrow_end)

                    # Сравнить текущие данные с кэшем
                    relevant_current_uids = set()
                    for uid, event in current_events_map.items():
                        if not self._is_today_or_tomorrow(event, today):
                            continue
                        relevant_current_uids.add(uid)
                        current_status = (event.get('status') or 'CONFIRMED').upper()
                        cached = cached_events_map.get(uid)

                        if not cached:
                            if current_status != 'CANCELLED':
                                await self._notify_new_meeting(user, event)
                                notification_count += 1
                            continue

                        cached_status = (cached.status or '').upper()
                        if cached_status == 'CANCELLED' and current_status != 'CANCELLED':
                            await self._notify_new_meeting(user, event)
                            notification_count += 1
                        elif cached_status != 'CANCELLED' and current_status == 'CANCELLED':
                            await self._notify_cancelled_meeting(user, cached)
                            notification_count += 1
                        elif current_status != 'CANCELLED' and self._event_changed_time(cached, event):
                            await self._notify_rescheduled_meeting(user, cached, event)
                            notification_count += 1

                    if request_ok and cached_events_map:
                        missing_uids = set(cached_events_map.keys()) - relevant_current_uids
                        for missing_uid in missing_uids:
                            cached = cached_events_map.get(missing_uid)
                            if not cached:
                                continue
                            cached_status = (cached.status or '').upper()
                            if cached_status == 'CANCELLED':
                                continue
                            await self._notify_cancelled_meeting(user, cached)
                            self._mark_event_cancelled(user.mattermost_id, missing_uid)
                            notification_count += 1

                    # Обновить кэш (по имеющимся событиям)
                    self._update_events_cache(user.mattermost_id, current_events_map.values())

                    # Проверить напоминания
                    reminders_sent = await self._check_reminders(user, list(current_events_map.values()))
                    notification_count += reminders_sent
                finally:
                    try:
                        await caldav_manager.close()
                    except Exception:
                        pass

                digest_sent = await self._maybe_send_daily_digest(user, password)
                notification_count += digest_sent
            
            except Exception as e:
                logger.error(f"Error checking notifications for user {user.mattermost_id}: {e}")
        
        return notification_count
    
    def _get_cached_events_map(self, user_id: str, start_date: datetime, 
                               end_date: datetime) -> Dict[str, MeetingCache]:
        """Получить кэшированные события (UID -> MeetingCache)."""
        session = self.db.get_session()
        try:
            events = session.query(MeetingCache).filter(
                MeetingCache.user_id == user_id,
                MeetingCache.start_time >= start_date,
                MeetingCache.start_time <= end_date
            ).all()
            return {evt.uid: evt for evt in events if evt.uid}
        finally:
            session.close()
    
    def _event_changed_time(self, cached: MeetingCache, current: Dict) -> bool:
        """Проверить, изменилось ли время события"""
        try:
            tz_local = self.tz
            current_start_raw = current.get('start_time', '')
            current_end_raw = current.get('end_time', '')
            if not current_start_raw or not current_end_raw:
                return False
            current_start = datetime.fromisoformat(current_start_raw)
            current_end = datetime.fromisoformat(current_end_raw)
            # Нормализуем в локальный TZ (если присутствует другой)
            if current_start.tzinfo:
                current_start = current_start.astimezone(tz_local)
            else:
                current_start = tz_local.localize(current_start)
            if current_end.tzinfo:
                current_end = current_end.astimezone(tz_local)
            else:
                current_end = tz_local.localize(current_end)
            cached_start = cached.start_time.astimezone(tz_local) if cached.start_time.tzinfo else tz_local.localize(cached.start_time)
            cached_end = cached.end_time.astimezone(tz_local) if cached.end_time.tzinfo else tz_local.localize(cached.end_time)
            # Сравниваем с точностью до минуты (секунды/микросекунды игнорируем)
            cached_start_min = cached_start.replace(second=0, microsecond=0)
            cached_end_min = cached_end.replace(second=0, microsecond=0)
            current_start_min = current_start.replace(second=0, microsecond=0)
            current_end_min = current_end.replace(second=0, microsecond=0)
            # Если равны по минутам — считаем не перенесено
            if cached_start_min == current_start_min and cached_end_min == current_end_min:
                return False
            # Иначе перенесено только если реально изменилось начало или конец на уровне минут
            return True
        except Exception:
            # В случае ошибки не шлем уведомление о переносе
            return False
    
    def _is_today_or_tomorrow(self, event: Dict, today: datetime) -> bool:
        """Проверить, событие ли это на сегодня или завтра"""
        start_time = datetime.fromisoformat(event.get('start_time', ''))
        tomorrow = today + timedelta(days=1)
        
        return start_time.date() in [today.date(), tomorrow.date()]
    
    def _update_events_cache(self, user_id: str, events: Iterable[Dict]):
        """Обновить/добавить записи кэша по событиям без удаления остальных."""
        session = self.db.get_session()
        try:
            for event in events:
                uid = event.get('uid')
                if not uid:
                    continue
                cache = session.query(MeetingCache).filter_by(user_id=user_id, uid=uid).first()
                if not cache:
                    cache = MeetingCache(user_id=user_id, uid=uid)
                    session.add(cache)
                cache.title = event.get('title', '')
                cache.start_time = datetime.fromisoformat(event.get('start_time', ''))
                cache.end_time = datetime.fromisoformat(event.get('end_time', ''))
                cache.description = event.get('description', '')
                cache.location = event.get('location', '')
                cache.organizer = event.get('organizer', '')
                cache.attendees = json.dumps(event.get('attendees', []))
                cache.status = event.get('status', 'CONFIRMED')
                cache.hash_value = CalDAVManager.hash_event(event)
            session.commit()
        finally:
            session.close()

    def _mark_event_cancelled(self, user_id: str, uid: str):
        """Пометить событие в кэше как отменённое, чтобы не спамить уведомлениями."""
        session = self.db.get_session()
        try:
            cache = session.query(MeetingCache).filter_by(user_id=user_id, uid=uid).first()
            if cache:
                cache.status = 'CANCELLED'
                session.commit()
        finally:
            session.close()
    
    async def _check_reminders(self, user, events: List[Dict]) -> int:
        """Проверить и отправить напоминания"""
        reminder_count = 0
        
        try:
            channel_id = await self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return 0
            
            now = datetime.now(self.tz)
            reminder_delta = timedelta(minutes=Config.REMINDER_MINUTES)
            check_window = max(5, Config.CHECK_INTERVAL)
            for event in events:
                start_time = datetime.fromisoformat(event.get('start_time', ''))
                if start_time.tzinfo:
                    start_time = start_time.astimezone(self.tz)
                else:
                    start_time = self.tz.localize(start_time)
                
                # Check VALARM alarms first
                alarms = event.get('alarms', [])
                alarm_triggered = False
                for alarm_iso in alarms:
                    try:
                        alarm_dt = datetime.fromisoformat(alarm_iso)
                        if alarm_dt.tzinfo:
                            alarm_dt = alarm_dt.astimezone(self.tz)
                        else:
                            alarm_dt = self.tz.localize(alarm_dt)
                        # Normalize to minute precision
                        delta_alarm = (alarm_dt - now).total_seconds()
                        if 0 <= delta_alarm < check_window:
                            message = UIMessages.reminder_notification(
                                event.get('title', ''),
                                start_time,
                                event.get('location', '')
                            )
                            await self.mm.send_message(channel_id, message)
                            reminder_count += 1
                            alarm_triggered = True
                            break  # Only send одно напоминание по VALARM
                    except Exception as alarm_err:
                        logger.debug(f"Failed to process alarm {alarm_iso}: {alarm_err}")
                        continue

                if alarm_triggered:
                    continue

                # Fallback: REMINDER_MINUTES (если нет VALARM или не сработало)
                if Config.REMINDER_MINUTES > 0 and not alarms:
                    delta_to_reminder = (start_time - now - reminder_delta).total_seconds()
                    if 0 <= delta_to_reminder < check_window:
                        message = UIMessages.reminder_notification(
                            event.get('title', ''),
                            start_time,
                            event.get('location', '')
                        )
                        await self.mm.send_message(channel_id, message)
                        reminder_count += 1
                        continue

                # Напоминание в момент начала встречи
                delta_to_start = (start_time - now).total_seconds()
                if 0 <= delta_to_start < check_window:
                    message = UIMessages.meeting_start_notification(
                        event.get('title', ''),
                        start_time,
                        event.get('location', '')
                    )
                    await self.mm.send_message(channel_id, message)
                    reminder_count += 1
        
        except Exception as e:
            logger.error(f"Error checking reminders: {e}")
        
        return reminder_count

    async def _maybe_send_daily_digest(self, user, password: str) -> int:
        """Отправить дайджест в 09:00, если ещё не был отправлен"""
        now = datetime.now(self.tz)
        digest_date = now.date()
        hour = max(0, min(23, int(getattr(Config, "DAILY_DIGEST_HOUR", 9))))
        target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)

        if now < target_time:
            return 0
        if self._digest_already_sent(user.mattermost_id, digest_date):
            return 0

        try:
            meetings = await self.logic.get_today_meetings(
                user.mattermost_id,
                user.email,
                password,
            )
        except Exception as err:
            logger.error(f"Daily digest failed to fetch meetings for {user.email}: {err}")
            return 0

        channel_id = await self.mm.get_channel_id(user.mattermost_id)
        if not channel_id:
            return 0

        table = self.logic.format_meetings_table(meetings)
        message = UIMessages.daily_digest(now, table)
        await self.mm.send_message(channel_id, message)
        self._mark_digest_sent(user.mattermost_id, digest_date)
        logger.info(f"Daily digest sent to {user.email}")
        return 1

    def _digest_already_sent(self, user_id: str, digest_date) -> bool:
        session = self.db.get_session()
        try:
            exists = session.query(DailyDigestLog).filter_by(
                user_id=user_id,
                digest_date=digest_date,
            ).first()
            return exists is not None
        finally:
            session.close()

    def _mark_digest_sent(self, user_id: str, digest_date):
        session = self.db.get_session()
        try:
            log = DailyDigestLog(user_id=user_id, digest_date=digest_date)
            session.add(log)
            session.commit()
        finally:
            session.close()
    
    async def _notify_new_meeting(self, user, event: Dict):
        """Отправить уведомление о новой встрече"""
        try:
            channel_id = await self.mm.get_channel_id(user.mattermost_id)
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
            
            await self.mm.send_message(channel_id, message)
            logger.info(f"Sent new meeting notification to {user.mattermost_id}")
        
        except Exception as e:
            logger.error(f"Error sending new meeting notification: {e}")
    
    async def _notify_cancelled_meeting(self, user, cached: MeetingCache):
        """Отправить уведомление об отмене встречи"""
        try:
            channel_id = await self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return
            
            message = UIMessages.meeting_cancelled(
                cached.title,
                cached.start_time,
                cached.end_time
            )
            
            await self.mm.send_message(channel_id, message)
            logger.info(f"Sent cancellation notification to {user.mattermost_id}")
        
        except Exception as e:
            logger.error(f"Error sending cancellation notification: {e}")
    
    async def _notify_rescheduled_meeting(self, user, cached: MeetingCache, new_event: Dict):
        """Отправить уведомление о переносе встречи"""
        try:
            channel_id = await self.mm.get_channel_id(user.mattermost_id)
            if not channel_id:
                return
            
            message = UIMessages.meeting_rescheduled(
                cached.title,
                cached.start_time,
                cached.end_time,
                datetime.fromisoformat(new_event.get('start_time', '')),
                datetime.fromisoformat(new_event.get('end_time', ''))
            )
            
            await self.mm.send_message(channel_id, message)
            logger.info(f"Sent rescheduled notification to {user.mattermost_id}")
        
        except Exception as e:
            logger.error(f"Error sending rescheduled notification: {e}")
