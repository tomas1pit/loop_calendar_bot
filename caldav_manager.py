import aiohttp
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import pytz
from config import Config
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

try:
    from icalendar import Calendar, Event, Alarm
except ImportError:
    Calendar = Event = Alarm = None


class CalDAVManager:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.base_url = Config.CALDAV_BASE_URL
        self.principal_url = self._build_principal_url(email)
        self.session = None
        self.calendar_path = None
    
    def _build_principal_url(self, email: str) -> str:
        """Построить URL principal для Mail.ru CalDAV"""
        try:
            domain, username = email.split("@")
            return f"{self.base_url}{Config.CALDAV_PRINCIPAL_PATH}{domain}/{username}/"
        except:
            return f"{self.base_url}{Config.CALDAV_PRINCIPAL_PATH}"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(self.email, self.password)
            )
        return self.session
    
    async def close(self):
        """Закрыть сессию"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def test_connection(self) -> bool:
        """Проверить подключение к CalDAV"""
        try:
            session = await self._get_session()
            async with session.request("PROPFIND", self.principal_url, 
                                      headers={"Depth": "0"}) as resp:
                return resp.status in [207, 200]
        except Exception as e:
            logger.error(f"Error testing connection: {e}")
            return False
    
    async def get_calendars(self) -> List[Dict[str, str]]:
        """Получить список календарей"""
        try:
            # Упрощенная реализация - возвращаем основной календарь
            return [{
                "href": f"{self.principal_url}calendar/",
                "name": "Personal Calendar"
            }]
        except Exception as e:
            logger.error(f"Error getting calendars: {e}")
            return []
    
    async def get_events(self, start_date: datetime = None, end_date: datetime = None) -> List[Dict]:
        """Получить события за период"""
        try:
            if not start_date:
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if not end_date:
                end_date = start_date + timedelta(days=1)
            
            # Пока серверная интеграция не реализована полностью, возвращаем пустой
            # список, чтобы верхний уровень мог работать без ошибок.
            # Когда будет готов серверный доступ, здесь нужно будет:
            # 1) Отправлять REPORT-запрос `_build_calendar_query(start_date, end_date)`
            #    на URL календаря.
            # 2) Распарсить ответ и вернуть список словарей единого формата:
            #    {
            #      "uid": str,
            #      "title": str,
            #      "start_time": iso-строка,
            #      "end_time": iso-строка,
            #      "attendees": [emails],
            #      "description": str,
            #      "location": str,
            #      "organizer": email,
            #      "status": str
            #    }
            return []
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return []
    
    async def create_event(self, title: str, start: datetime, end: datetime, 
                          attendees: List[str] = None, description: str = "", 
                          location: str = "") -> bool:
        """Создать событие в CalDAV"""
        try:
            if not Calendar or not Event:
                logger.error("icalendar library not available")
                return False
            
            if attendees is None:
                attendees = []
            
            calendar = Calendar()
            calendar.add("prodid", "-//Calendar Bot//Calendar//EN")
            calendar.add("version", "2.0")
            calendar.add("calscale", "GREGORIAN")
            
            event = Event()
            uid = f"{datetime.utcnow().timestamp()}@{self.email}"
            event.add("uid", uid)
            event.add("summary", title)
            event.add("dtstart", start)
            event.add("dtend", end)
            event.add("dtstamp", datetime.utcnow())
            event.add("created", datetime.utcnow())
            event.add("last-modified", datetime.utcnow())
            
            if description:
                event.add("description", description)
            if location:
                event.add("location", location)
            
            # Добавить организатора
            event.add("organizer", f"mailto:{self.email}")
            
            # Добавить участников
            for attendee in attendees:
                if attendee != self.email:
                    event.add("attendee", f"mailto:{attendee}")
            
            # Добавить напоминание за Config.REMINDER_MINUTES минут
            if Alarm:
                alarm = Alarm()
                alarm.add("trigger", f"-PT{Config.REMINDER_MINUTES}M")
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"Встреча '{title}' через {Config.REMINDER_MINUTES} минут")
                event.add_component(alarm)
            
            calendar.add_component(event)
            
            # Упрощенная реализация - просто логируем
            # TODO: Загрузить событие на сервер
            logger.info(f"Event '{title}' would be created from {start} to {end}")
            return True
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return False
    
    def _build_calendar_query(self, start: datetime, end: datetime) -> str:
        """Построить CalDAV REPORT запрос"""
        start_str = start.strftime("%Y%m%dT%H%M%SZ")
        end_str = end.strftime("%Y%m%dT%H%M%SZ")
        
        return f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start_str}" end="{end_str}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""
    
    def _parse_events(self, xml_text: str) -> List[Dict]:
        """Парсить XML ответ с событиями"""
        events = []
        # TODO: Полный парсинг XML с событиями
        return events
    
    @staticmethod
    def hash_event(event: Dict) -> str:
        """Создать хэш события для отслеживания изменений"""
        event_str = json.dumps(event, sort_keys=True, default=str)
        return hashlib.md5(event_str.encode()).hexdigest()
