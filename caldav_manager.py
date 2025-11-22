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
            username, domain = email.split("@")
            principal = f"{self.base_url}{Config.CALDAV_PRINCIPAL_PATH}{domain}/{username}/"
            logger.info(f"CalDAV principal URL built: {principal}")
            return principal
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
        """Получить список календарей.

        1. Делаем PROPFIND Depth=1 по principal URL и ищем ресурсы типа calendar.
        2. Извлекаем displayname / href.
        3. Приоритизируем displayname == 'Main' или 'Основной' (регистр игнорируем).
        4. Фоллбек: пробуем набор кандидатных путей (как раньше).
        """
        try:
            session = await self._get_session()

            calendars: List[Dict[str, str]] = []
            headers = {"Depth": "1"}
            calendars_root_href = None
            try:
                async with session.request("PROPFIND", self.principal_url, headers=headers) as resp:
                    text = await resp.text()
                    status = resp.status
                    logger.info(f"Principal PROPFIND status={status} url={self.principal_url}")
                    if status not in (200, 207):
                        logger.info(f"Principal PROPFIND failed: {status} {self.principal_url}")
                    else:
                        from xml.etree import ElementTree as ET
                        ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
                        try:
                            root = ET.fromstring(text)
                            for response in root.findall("d:response", ns):
                                href_el = response.find("d:href", ns)
                                propstat = response.find("d:propstat", ns)
                                if href_el is None or propstat is None:
                                    continue
                                prop = propstat.find("d:prop", ns)
                                if prop is None:
                                    continue
                                rtype = prop.find("d:resourcetype", ns)
                                displayname_el = prop.find("d:displayname", ns)
                                displayname = displayname_el.text.strip() if displayname_el is not None and displayname_el.text else ""
                                href = href_el.text.strip() if href_el.text else ""
                                is_calendar = False
                                if rtype is not None and rtype.find("c:calendar", ns) is not None:
                                    is_calendar = True
                                # Запоминаем корневую директорию календарей пользователя
                                if href.endswith('/calendars/'):
                                    calendars_root_href = href
                                if is_calendar and href:
                                    calendars.append({"href": href if href.endswith('/') else href + '/', "name": displayname or "Calendar"})
                        except Exception as e:
                            logger.info(f"Failed to parse principal PROPFIND XML: {e}")
            except Exception as e:
                logger.info(f"Error during principal PROPFIND: {e}")

            # Если нашли корневой каталог calendars, делаем второй проход Depth=1
            if calendars_root_href and not calendars:
                # Собираем абсолютный URL если ответ был относительным
                if calendars_root_href.startswith('/'):
                    calendars_root_url = self.base_url.rstrip('/') + calendars_root_href
                else:
                    calendars_root_url = calendars_root_href
                logger.info(f"Enumerating calendars at {calendars_root_url}")
                try:
                    async with session.request("PROPFIND", calendars_root_url, headers={"Depth": "1"}) as resp2:
                        text2 = await resp2.text()
                        status2 = resp2.status
                        logger.info(f"Calendars collection PROPFIND status={status2}")
                        if status2 in (200,207):
                            from xml.etree import ElementTree as ET
                            ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
                            try:
                                root2 = ET.fromstring(text2)
                                for response in root2.findall("d:response", ns):
                                    href_el = response.find("d:href", ns)
                                    propstat = response.find("d:propstat", ns)
                                    if href_el is None or propstat is None:
                                        continue
                                    prop = propstat.find("d:prop", ns)
                                    if prop is None:
                                        continue
                                    rtype = prop.find("d:resourcetype", ns)
                                    displayname_el = prop.find("d:displayname", ns)
                                    displayname = displayname_el.text.strip() if displayname_el is not None and displayname_el.text else ""
                                    href_child = href_el.text.strip() if href_el.text else ""
                                    is_calendar = rtype is not None and rtype.find("c:calendar", ns) is not None
                                    if is_calendar and href_child != calendars_root_href:
                                        full_child_href = href_child if href_child.endswith('/') else href_child + '/'
                                        if full_child_href.startswith('/'):
                                            full_child_href = self.base_url.rstrip('/') + full_child_href
                                        calendars.append({"href": full_child_href, "name": displayname or "Calendar"})
                            except Exception as e:
                                logger.info(f"Failed to parse calendars collection XML: {e}")
                except Exception as e:
                    logger.info(f"Error during calendars root enumeration: {e}")

            # Приоритизируем Main / Основной
            preferred = [c for c in calendars if c["name"].lower() in ("main", "основной")]
            selected = preferred or calendars
            if selected:
                # Логируем только выбранные (приоритетные либо первые найденные)
                for c in selected:
                    logger.info(f"CalDAV calendar selected: {c['href']} name={c['name']}")
                return selected

            # Если не нашли через автоматический способ — пробуем кандидаты (фоллбек)
            candidates = [
                f"{self.principal_url}calendar/",
                f"{self.base_url}/dav/{self.email}/calendar/",
                f"{self.base_url}/dav/{self.email}/",
                f"{self.base_url}/calendars/{self.email}/",
            ]
            # Сокращённый fallback перебор
            for href in candidates:
                try:
                    async with session.request("PROPFIND", href, headers={"Depth": "0"}) as resp:
                        body = await resp.text()
                        if resp.status in (200, 207):
                            logger.info(f"CalDAV fallback calendar path detected: {href}")
                            return [{"href": href, "name": "Calendar"}]
                        else:
                            logger.debug(f"Fallback probe failed: {href} status={resp.status}")
                except Exception as e:
                    logger.debug(f"Fallback probe error {href}: {e}")

            logger.error("No CalDAV calendar path found after enumeration and fallback probes")
            return []
        except Exception as e:
            logger.error(f"Error getting calendars: {e}")
            return []
    
    async def get_events(self, start_date: datetime = None, end_date: datetime = None) -> List[Dict]:
        """Получить события за период"""
        all_events: List[Dict] = []
        try:
            if not start_date:
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if not end_date:
                end_date = start_date + timedelta(days=1)

            session = await self._get_session()
            calendars = await self.get_calendars()
            if not calendars:
                logger.info("No calendars discovered to fetch events")
                return []

            body = self._build_calendar_query(start_date, end_date)
            headers = {
                "Depth": "1",
                "Content-Type": "application/xml; charset=utf-8",
            }

            for cal in calendars:
                cal_href = cal.get("href")
                if not cal_href:
                    continue
                try:
                    async with session.request("REPORT", cal_href, data=body, headers=headers) as resp:
                        if resp.status not in (200, 207):
                            logger.debug(f"CalDAV REPORT failed: {resp.status} for {cal_href}")
                            continue
                        text = await resp.text()
                        head_primary = text[:400].replace("\n", " ")
                        logger.info(
                            f"CalDAV REPORT RAW primary href={cal_href} status={resp.status} len={len(text)} head='{head_primary}'"
                        )
                    evs = self._parse_events(text)
                    logger.debug(f"Fetched {len(evs)} events from {cal_href}")
                    all_events.extend(evs)
                except Exception as ce:
                    logger.debug(f"Error fetching events from {cal_href}: {ce}")

            # Если за указанный день ничего не нашли, делаем расширенный диапазон (7 дней вперёд) как fallback
            if not all_events:
                ext_start = start_date
                ext_end = start_date + timedelta(days=7)
                body_ext = self._build_calendar_query(ext_start, ext_end)
                for cal in calendars:
                    cal_href = cal.get("href")
                    if not cal_href:
                        continue
                    try:
                        async with session.request("REPORT", cal_href, data=body_ext, headers=headers) as resp:
                            if resp.status not in (200, 207):
                                continue
                            text = await resp.text()
                            head_fallback = text[:400].replace("\n", " ")
                            logger.info(
                                f"CalDAV REPORT RAW fallback href={cal_href} status={resp.status} len={len(text)} head='{head_fallback}'"
                            )
                        evs = self._parse_events(text)
                        logger.debug(f"Fallback range fetched {len(evs)} events from {cal_href}")
                        all_events.extend(evs)
                    except Exception:
                        continue

            return all_events
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return all_events
    
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
        # Преобразуем в UTC перед добавлением 'Z'
        import pytz
        start_utc = start.astimezone(pytz.UTC) if start.tzinfo else start
        end_utc = end.astimezone(pytz.UTC) if end.tzinfo else end
        start_str = start_utc.strftime("%Y%m%dT%H%M%SZ")
        end_str = end_utc.strftime("%Y%m%dT%H%M%SZ")
        
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
        events: List[Dict] = []

        if not Calendar:
            return events

        try:
            # Очень упрощённый парсер: ищем блоки с VCALENDAR внутри XML
            # и забираем оттуда VEVENT в формате ical.
            from xml.etree import ElementTree as ET

            root = ET.fromstring(xml_text)
            ns = {
                "d": "DAV:",
                "c": "urn:ietf:params:xml:ns:caldav",
            }

            for resp in root.findall("d:response", ns):
                # REPORT ответ может содержать несколько propstat; calendar-data не всегда в первом
                for propstat in resp.findall("d:propstat", ns):
                    prop = propstat.find("d:prop", ns)
                    if prop is None:
                        continue
                    caldata_el = prop.find("c:calendar-data", ns)
                    if caldata_el is None or not caldata_el.text:
                        continue

                    ical_str = caldata_el.text.strip()
                    try:
                        cal = Calendar.from_ical(ical_str)
                    except Exception:
                        continue

                    for component in cal.walk():
                        if component.name != "VEVENT":
                            continue

                        try:
                            uid = str(component.get("uid", ""))
                            title = str(component.get("summary", "Без названия"))

                            dtstart = component.get("dtstart").dt
                            dtend = component.get("dtend").dt

                            tz = pytz.timezone(Config.TZ)
                            if not isinstance(dtstart, datetime):
                                dtstart = datetime.combine(dtstart, datetime.min.time())
                            if not isinstance(dtend, datetime):
                                dtend = datetime.combine(dtend, datetime.min.time())

                            if dtstart.tzinfo is None:
                                dtstart = tz.localize(dtstart)
                            else:
                                dtstart = dtstart.astimezone(tz)

                            if dtend.tzinfo is None:
                                dtend = tz.localize(dtend)
                            else:
                                dtend = dtend.astimezone(tz)

                            attendees: List[str] = []
                            for att in component.get_all("attendee", []):
                                addr = str(att)
                                if addr.lower().startswith("mailto:"):
                                    addr = addr[7:]
                                attendees.append(addr)

                            organizer = component.get("organizer")
                            organizer_email = ""
                            if organizer:
                                organizer_email = str(organizer)
                                if organizer_email.lower().startswith("mailto:"):
                                    organizer_email = organizer_email[7:]

                            description = str(component.get("description", ""))
                            location = str(component.get("location", ""))
                            status = str(component.get("status", "CONFIRMED"))

                            events.append({
                                "uid": uid,
                                "title": title,
                                "start_time": dtstart.isoformat(),
                                "end_time": dtend.isoformat(),
                                "attendees": attendees,
                                "description": description,
                                "location": location,
                                "organizer": organizer_email,
                                "status": status,
                            })
                        except Exception:
                            continue

        except Exception as e:
            logger.error(f"Error parsing CalDAV events XML: {e}")

        return events
    
    @staticmethod
    def hash_event(event: Dict) -> str:
        """Создать хэш события для отслеживания изменений"""
        event_str = json.dumps(event, sort_keys=True, default=str)
        return hashlib.md5(event_str.encode()).hexdigest()
