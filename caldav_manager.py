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
        """Получить список календарей (enumeration + fallback)."""
        try:
            session = await self._get_session()
            calendars: List[Dict[str, str]] = []
            headers = {"Depth": "1"}
            calendars_root_href = None
            # Первый проход: principal URL
            try:
                async with session.request("PROPFIND", self.principal_url, headers=headers) as resp:
                    text = await resp.text()
                    status = resp.status
                    logger.info(f"Principal PROPFIND status={status} url={self.principal_url}")
                    if status in (200, 207):
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
                                if href.endswith('/calendars/'):
                                    calendars_root_href = href
                                if rtype is not None and rtype.find("c:calendar", ns) is not None and href:
                                    calendars.append({"href": href if href.endswith('/') else href + '/', "name": displayname or "Calendar"})
                        except Exception as e:
                            logger.info(f"Failed to parse principal PROPFIND XML: {e}")
            except Exception as e:
                logger.info(f"Error during principal PROPFIND: {e}")

            # Второй проход: перечисление внутри /calendars/
            if calendars_root_href and not calendars:
                if calendars_root_href.startswith('/'):
                    calendars_root_url = self.base_url.rstrip('/') + calendars_root_href
                else:
                    calendars_root_url = calendars_root_href
                logger.info(f"Enumerating calendars at {calendars_root_url}")
                try:
                    async with session.request("PROPFIND", calendars_root_url, headers=headers) as resp2:
                        text2 = await resp2.text()
                        status2 = resp2.status
                        logger.info(f"Calendars collection PROPFIND status={status2}")
                        if status2 in (200, 207):
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

            preferred = [c for c in calendars if c["name"].lower() in ("main", "основной")]
            selected = preferred or calendars
            if selected:
                for c in selected:
                    logger.info(f"CalDAV calendar selected: {c['href']} name={c['name']}")
                return selected

            # Fallback candidates
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

            # Основной запрос (точный диапазон)
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
                        if Config.CALDAV_LOG_FULL_RAW:
                            logger.info(f"CalDAV REPORT RAW PRIMARY href={cal_href} status={resp.status} len={len(text)}\n{text}")
                        else:
                            head_primary = text[:400].replace("\n", " ")
                            logger.info(
                                f"CalDAV REPORT RAW primary href={cal_href} status={resp.status} len={len(text)} head='{head_primary}'"
                            )
                    evs = self._parse_events(text)
                    logger.debug(f"Fetched {len(evs)} events from {cal_href}")
                    all_events.extend(evs)
                except Exception as ce:
                    logger.debug(f"Error fetching events from {cal_href}: {ce}")

            # Fallback расширенный диапазон REPORT если ничего не нашли
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
                            if Config.CALDAV_LOG_FULL_RAW:
                                logger.info(f"CalDAV REPORT RAW FALLBACK href={cal_href} status={resp.status} len={len(text)}\n{text}")
                            else:
                                head_fallback = text[:400].replace("\n", " ")
                                logger.info(
                                    f"CalDAV REPORT RAW fallback href={cal_href} status={resp.status} len={len(text)} head='{head_fallback}'"
                                )
                        evs = self._parse_events(text)
                        logger.debug(f"Fallback range fetched {len(evs)} events from {cal_href}")
                        all_events.extend(evs)
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error getting events: {e}")
        finally:
            # Диагностика первичного результата до python-caldav
            try:
                if all_events:
                    for i, ev in enumerate(all_events[:10]):
                        logger.info(f"ALL_EVENTS[{i}] uid={ev.get('uid')} title={ev.get('title')} start={ev.get('start_time')} end={ev.get('end_time')}")
                else:
                    logger.info("ALL_EVENTS empty after REPORT aggregation (will try python-caldav fallback)")
            except Exception:
                pass

        # Python-caldav fallback (date_search) теперь достижим
        if not all_events:
            try:
                import caldav
                logger.info("Fallback: using python-caldav date_search")
                base_url = self.base_url.rstrip('/')
                principal = caldav.Principal(
                    client=caldav.DAVClient(url=base_url, username=self.email, password=self.password),
                    url=self.principal_url,
                )
                calendars2 = principal.calendars()
                if not calendars2:
                    logger.info("Fallback caldav: no calendars returned by principal")
                    return []
                preferred_names = {"main", "основной"}
                selected = None
                for c in calendars2:
                    name = getattr(c, 'name', '') or ''
                    if name.lower() in preferred_names:
                        selected = c
                        break
                if selected is None:
                    selected = calendars2[0]
                tz_local = pytz.timezone(Config.TZ)
                s_local = (start_date or datetime.now()).astimezone(tz_local) if (start_date and start_date.tzinfo) else (start_date or datetime.now()).replace(tzinfo=tz_local)
                e_local = (end_date or (start_date or datetime.now()) + timedelta(days=1))
                e_local = e_local.astimezone(tz_local) if (e_local and e_local.tzinfo) else e_local.replace(tzinfo=tz_local)
                raw_events = selected.date_search(s_local, e_local)
                logger.info(f"Fallback caldav: date_search returned {len(raw_events)} items")
                for ev_obj in raw_events:
                    try:
                        ics_data = getattr(ev_obj, 'data', None)
                        if ics_data is None:
                            ics_data = ev_obj._data if hasattr(ev_obj, '_data') else None
                        if not ics_data:
                            continue
                        try:
                            cal = Calendar.from_ical(ics_data)
                        except Exception as pe:
                            logger.debug(f"Fallback caldav: ical parse failed {pe}")
                            continue
                        for comp in cal.walk():
                            if comp.name != 'VEVENT':
                                continue
                            try:
                                uid = str(comp.get('uid', ''))
                                title = str(comp.get('summary', 'Без названия'))
                                dtstart = comp.get('dtstart').dt
                                dtend = comp.get('dtend').dt if comp.get('dtend') else None
                                tz_cfg = pytz.timezone(Config.TZ)
                                if isinstance(dtstart, datetime):
                                    dtstart = dtstart.astimezone(tz_cfg) if dtstart.tzinfo else tz_cfg.localize(dtstart)
                                if isinstance(dtend, datetime):
                                    dtend = dtend.astimezone(tz_cfg) if dtend.tzinfo else tz_cfg.localize(dtend)
                                attendees: List[str] = []
                                for att in comp.get_all('attendee', []):
                                    a = str(att)
                                    if a.lower().startswith('mailto:'):
                                        a = a[7:]
                                    attendees.append(a)
                                organizer = comp.get('organizer')
                                organizer_email = ''
                                if organizer:
                                    organizer_email = str(organizer)
                                    if organizer_email.lower().startswith('mailto:'):
                                        organizer_email = organizer_email[7:]
                                events_dict = {
                                    'uid': uid,
                                    'title': title,
                                    'start_time': dtstart.isoformat() if isinstance(dtstart, datetime) else '',
                                    'end_time': dtend.isoformat() if isinstance(dtend, datetime) else '',
                                    'attendees': attendees,
                                    'description': str(comp.get('description', '')),
                                    'location': str(comp.get('location', '')),
                                    'organizer': organizer_email,
                                    'status': str(comp.get('status', 'CONFIRMED')),
                                }
                                all_events.append(events_dict)
                            except Exception as ce_inner:
                                logger.debug(f"Fallback caldav: error building event dict {ce_inner}")
                    except Exception as ce_ev:
                        logger.debug(f"Fallback caldav: error processing event object {ce_ev}")
                if all_events:
                    logger.info(f"Fallback caldav: aggregated {len(all_events)} events")
            except Exception as e_fb:
                logger.info(f"Fallback caldav failed: {e_fb}")
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
        """Парсить REPORT XML -> события (устойчивый парсер)."""
        events: List[Dict] = []
        if not Calendar:
            return events
        try:
            from xml.etree import ElementTree as ET
            root = ET.fromstring(xml_text)
            ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "C": "urn:ietf:params:xml:ns:caldav"}
            block_index = 0
            for resp in root.findall("d:response", ns):
                for propstat in resp.findall("d:propstat", ns):
                    prop = propstat.find("d:prop", ns)
                    if prop is None:
                        continue
                    caldata_el = None
                    for child in list(prop):
                        if child.tag.endswith("calendar-data") and child.text:
                            caldata_el = child
                            break
                    if caldata_el is None:
                        continue
                    raw_ical = (caldata_el.text or "").strip()
                    cleaned = ''.join(ch for ch in raw_ical if ch in ('\n','\r') or ord(ch) >= 32)
                    parse_source = cleaned
                    parsed = False
                    try:
                        cal = Calendar.from_ical(parse_source)
                        parsed = True
                        logger.debug(f"Calendar-data block {block_index} parsed len={len(parse_source)}")
                    except Exception as e_first:
                        logger.debug(f"Calendar-data block {block_index} initial parse failed: {e_first}")
                        try:
                            cal = Calendar.from_ical(parse_source.encode('utf-8','ignore'))
                            parsed = True
                            logger.debug(f"Calendar-data block {block_index} parsed second attempt bytes len={len(parse_source)}")
                        except Exception as e_second:
                            logger.debug(f"Calendar-data block {block_index} parse failed bytes: {e_second}")
                            block_index += 1
                            continue
                    if not parsed:
                        block_index += 1
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
                        except Exception as ve_inner:
                            if Config.CALDAV_LOG_PARSE_ERRORS:
                                logger.debug(f"Failed VEVENT parse uid={component.get('uid')} err={ve_inner}")
                            continue
                    block_index += 1
            if events:
                logger.info(f"Parsed {len(events)} CalDAV events from REPORT response")
            else:
                logger.info("Parsed 0 CalDAV events from REPORT response")
        except Exception as e:
            logger.error(f"Error parsing CalDAV events XML: {e}")
        return events
    
    @staticmethod
    def hash_event(event: Dict) -> str:
        """Создать хэш события для отслеживания изменений"""
        event_str = json.dumps(event, sort_keys=True, default=str)
        return hashlib.md5(event_str.encode()).hexdigest()
