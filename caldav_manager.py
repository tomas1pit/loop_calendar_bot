import aiohttp
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import pytz
from config import Config
import json
import hashlib
import logging
import vobject
import uuid

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
        self.last_events_ok = True
        self.last_events_statuses: List[int] = []
    
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
        self.last_events_statuses = []
        self.last_events_ok = False
        try:
            if not start_date:
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if not end_date:
                end_date = start_date + timedelta(days=1)

            # Локализуем диапазон к таймзоне конфигурации, чтобы корректно сформировать UTC диапазон.
            try:
                tz_localize = pytz.timezone(Config.TZ)
                if start_date.tzinfo is None:
                    start_date = tz_localize.localize(start_date)
                else:
                    start_date = start_date.astimezone(tz_localize)
                if end_date.tzinfo is None:
                    end_date = tz_localize.localize(end_date)
                else:
                    end_date = end_date.astimezone(tz_localize)
            except Exception:
                pass

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
                # Нормализуем относительные пути в абсолютный URL
                if cal_href.startswith('/'):
                    cal_href_full = self.base_url.rstrip('/') + cal_href
                else:
                    cal_href_full = cal_href
                try:
                    async with session.request("REPORT", cal_href_full, data=body, headers=headers) as resp:
                        self.last_events_statuses.append(resp.status)
                        if resp.status not in (200, 207):
                            logger.debug(f"CalDAV REPORT failed: {resp.status} for {cal_href_full}")
                            continue
                        self.last_events_ok = True
                        text = await resp.text()
                        # Сокращенный лог только статуса запроса
                        logger.info(f"CalDAV REPORT primary status={resp.status} href={cal_href_full} len={len(text)}")
                    evs = self._parse_events(text)
                    logger.debug(f"Fetched {len(evs)} events from {cal_href_full}")
                    all_events.extend(evs)
                except Exception as ce:
                    logger.debug(f"Error fetching events from {cal_href_full}: {ce}")

            # Fallback расширенный диапазон REPORT если ничего не нашли
            if not all_events:
                ext_start = start_date
                ext_end = start_date + timedelta(days=7)
                body_ext = self._build_calendar_query(ext_start, ext_end)
                for cal in calendars:
                    cal_href = cal.get("href")
                    if not cal_href:
                        continue
                    if cal_href.startswith('/'):
                        cal_href_full = self.base_url.rstrip('/') + cal_href
                    else:
                        cal_href_full = cal_href
                    try:
                        async with session.request("REPORT", cal_href_full, data=body_ext, headers=headers) as resp:
                            self.last_events_statuses.append(resp.status)
                            if resp.status not in (200, 207):
                                continue
                            self.last_events_ok = True
                            text = await resp.text()
                            logger.info(f"CalDAV REPORT fallback status={resp.status} href={cal_href_full} len={len(text)}")
                        evs = self._parse_events(text)
                        logger.debug(f"Fallback range fetched {len(evs)} events from {cal_href_full}")
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
                self.last_events_ok = True
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
                                    # Remove mailto: prefix
                                    if a.lower().startswith('mailto:'):
                                        a = a[7:]
                                    # Clean up whitespace, newlines, and take first word
                                    a = a.strip().replace('\n', '').replace('\r', '').split()[0] if a.strip() else ''
                                    if a:
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
            import vobject
            import uuid
            
            if attendees is None:
                attendees = []
            
            # Убедимся что start и end - timezone-aware datetime
            tz = pytz.timezone(Config.TZ)
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            
            # Нормализуем timezone - используем localize для правильного TZID
            if start.tzinfo is None:
                start = tz.localize(start)
            else:
                start = start.astimezone(tz)
            
            if end.tzinfo is None:
                end = tz.localize(end)
            else:
                end = end.astimezone(tz)
            
            # Get calendar using python-caldav
            calendars = await self.get_calendars()
            if not calendars:
                logger.error("No calendars found")
                return False
            
            # Use first calendar (Main/Основной preferred by get_calendars)
            calendar_url = calendars[0]['href']
            
            # Create vobject iCalendar
            vcal = vobject.iCalendar()
            vevent = vcal.add('vevent')
            
            uid = str(uuid.uuid4())
            vevent.add('uid').value = uid
            vevent.add('summary').value = title
            
            # Add dtstart with TZID parameter
            dtstart_prop = vevent.add('dtstart')
            dtstart_prop.value = start
            
            # Add dtend with TZID parameter
            dtend_prop = vevent.add('dtend')
            dtend_prop.value = end
            
            vevent.add('dtstamp').value = datetime.utcnow().replace(tzinfo=pytz.UTC)
            vevent.add('created').value = datetime.utcnow().replace(tzinfo=pytz.UTC)
            vevent.add('last-modified').value = datetime.utcnow().replace(tzinfo=pytz.UTC)
            vevent.add('status').value = 'CONFIRMED'
            vevent.add('sequence').value = "0"
            vevent.add('transp').value = 'OPAQUE'
            
            if description:
                vevent.add('description').value = description
            if location:
                vevent.add('location').value = location
            
            # Add organizer
            organizer = vevent.add('organizer')
            organizer.value = f'mailto:{self.email}'
            organizer.params['CN'] = [self.email]
            
            # Add attendees
            for addr in attendees:
                if addr and addr != self.email:
                    att = vevent.add('attendee')
                    att.value = f'mailto:{addr}'
                    att.params['CN'] = [addr]
                    att.params['ROLE'] = ['REQ-PARTICIPANT']
            
            # Serialize to iCalendar format
            ical_str = vcal.serialize()
            
            # PUT event to calendar
            event_url = f"{calendar_url.rstrip('/')}/{uid}.ics"
            headers = {
                'Content-Type': 'text/calendar; charset=utf-8',
            }
            
            # Initialize session if needed
            if not self.session:
                await self.init_session()
            
            from aiohttp import BasicAuth
            auth = BasicAuth(self.email, self.password)
            
            response = await self.session.put(
                event_url,
                data=ical_str.encode('utf-8'),
                headers=headers,
                auth=auth
            )
            
            if response.status in (200, 201, 204):
                logger.info(f"Event '{title}' created successfully: {uid}")
                return True
            else:
                response_text = await response.text()
                logger.error(f"Failed to create event: {response.status} {response_text}")
                return False
                
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
            ical_blocks: List[str] = []
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
                    # Извлекаем полный текст calendar-data, включая возможные дополнительные text nodes
                    try:
                        raw_ical = ''.join(caldata_el.itertext())
                    except Exception:
                        raw_ical = caldata_el.text or ''
                    raw_ical = raw_ical.strip()
                    # RFC 5545 line unfolding: объединить строки, начинающиеся с пробела
                    lines = raw_ical.split('\n')
                    unfolded_lines = []
                    for line in lines:
                        if line.startswith(' ') or line.startswith('\t'):
                            # Продолжение предыдущей строки
                            if unfolded_lines:
                                unfolded_lines[-1] += line[1:]  # Убираем первый пробел
                        else:
                            unfolded_lines.append(line)
                    raw_ical = '\n'.join(unfolded_lines)
                    # Убрали подробное превью для снижения шума
                    cleaned = ''.join(ch for ch in raw_ical if ch in ('\n','\r') or ord(ch) >= 32)
                    ical_blocks.append(cleaned)
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
                            raw_dtstart = component.get("dtstart")
                            raw_dtend = component.get("dtend")
                            dtstart = raw_dtstart.dt if raw_dtstart else None
                            dtend = raw_dtend.dt if raw_dtend else None
                            # Debug raw values + tzinfo
                            # Минимальный лог на случай разбора — отключен для снижения шума
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
                                # att is vCalAddress object with params and value
                                addr = str(att)
                                # Remove mailto: prefix if present
                                if addr.lower().startswith("mailto:"):
                                    addr = addr[7:]
                                # Clean up any trailing/leading whitespace, newlines, and split on whitespace
                                addr = addr.strip().replace('\n', '').replace('\r', '').split()[0] if addr.strip() else ''
                                if addr:
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
                            
                            # Extract VALARM components
                            alarms = []
                            for subcomp in component.walk():
                                if subcomp.name == "VALARM":
                                    trigger = subcomp.get("trigger")
                                    if trigger:
                                        try:
                                            # TRIGGER can be absolute datetime or relative duration
                                            if hasattr(trigger, 'dt'):
                                                # Absolute datetime
                                                alarm_dt = trigger.dt
                                                if isinstance(alarm_dt, datetime):
                                                    if alarm_dt.tzinfo is None:
                                                        alarm_dt = tz.localize(alarm_dt)
                                                    else:
                                                        alarm_dt = alarm_dt.astimezone(tz)
                                                    alarms.append(alarm_dt.isoformat())
                                            elif hasattr(trigger, 'td'):
                                                # Relative timedelta (e.g., -PT15M)
                                                alarm_dt = dtstart + trigger.td
                                                alarms.append(alarm_dt.isoformat())
                                        except Exception as alarm_err:
                                            logger.debug(f"Failed to parse VALARM trigger: {alarm_err}")
                            
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
                                "alarms": alarms,
                            })
                            # Без подробного лога добавления события
                        except Exception as ve_inner:
                            if Config.CALDAV_LOG_PARSE_ERRORS:
                                logger.debug(f"Failed VEVENT parse uid={component.get('uid')} err={ve_inner}")
                            continue
                    block_index += 1
            if events:
                logger.info(f"Parsed {len(events)} CalDAV events from REPORT response")
            else:
                logger.info("Parsed 0 CalDAV events from REPORT response")
                # Regex fallback: если стандартный парсер ничего не дал, пытаемся извлечь VEVENT вручную
                try:
                    import re
                    tz_local = pytz.timezone(Config.TZ)
                    fallback_events = []
                    for ib_idx, block in enumerate(ical_blocks):
                        for match in re.finditer(r"BEGIN:VEVENT(.*?)END:VEVENT", block, re.DOTALL):
                            vevent_raw = match.group(1)
                            # Извлекаем ключевые поля простыми regex
                            def rex(field):
                                m = re.search(rf"^{field}:(.+)$", vevent_raw, re.MULTILINE)
                                return m.group(1).strip() if m else ""
                            def rex_tz(field):
                                # DTSTART;TZID=Europe/Moscow:20251122T011500
                                m = re.search(rf"^{field}(?:;TZID=([^:]+))?:(.+)$", vevent_raw, re.MULTILINE)
                                if m:
                                    return m.group(1) or "", m.group(2).strip()
                                return "", ""
                            uid = rex("UID") or f"fallback-{ib_idx}-{len(fallback_events)}"
                            summary = rex("SUMMARY") or "Без названия"
                            status = rex("STATUS") or "CONFIRMED"
                            tzid_start, dtstart_raw = rex_tz("DTSTART")
                            tzid_end, dtend_raw = rex_tz("DTEND")
                            dtstart = None
                            dtend = None
                            dt_fmt_candidates = ["%Y%m%dT%H%M%S", "%Y%m%dT%H%M"]
                            for fmt in dt_fmt_candidates:
                                if dtstart is None and dtstart_raw:
                                    try:
                                        dtstart = datetime.strptime(dtstart_raw, fmt)
                                    except Exception:
                                        pass
                                if dtend is None and dtend_raw:
                                    try:
                                        dtend = datetime.strptime(dtend_raw, fmt)
                                    except Exception:
                                        pass
                            if dtstart is not None:
                                if tzid_start:
                                    try:
                                        tz_parsed = pytz.timezone(tzid_start)
                                    except Exception:
                                        tz_parsed = tz_local
                                else:
                                    tz_parsed = tz_local
                                dtstart = tz_parsed.localize(dtstart)
                            if dtend is not None:
                                if tzid_end:
                                    try:
                                        tz_parsed_e = pytz.timezone(tzid_end)
                                    except Exception:
                                        tz_parsed_e = tz_local
                                else:
                                    tz_parsed_e = tz_local
                                dtend = tz_parsed_e.localize(dtend)
                            if dtstart and dtend:
                                # Extract ATTENDEE emails from regex
                                attendees = []
                                for att_match in re.finditer(r"^ATTENDEE[^:]*:mailto:(.+)$", vevent_raw, re.MULTILINE):
                                    email = att_match.group(1).strip()
                                    # Remove any trailing/leading whitespace, newlines, and take first word
                                    email = email.replace('\n', '').replace('\r', '').split()[0] if email else ""
                                    if email:
                                        attendees.append(email)
                                
                                # Extract ORGANIZER email
                                organizer = ""
                                org_match = re.search(r"^ORGANIZER[^:]*:mailto:(.+)$", vevent_raw, re.MULTILINE)
                                if org_match:
                                    organizer = org_match.group(1).strip().replace('\n', '').replace('\r', '').split()[0]
                                
                                # Extract description and location
                                description = rex("DESCRIPTION")
                                location = rex("LOCATION")
                                
                                # Extract VALARM triggers from regex
                                alarms = []
                                for valarm_match in re.finditer(r"BEGIN:VALARM(.*?)END:VALARM", vevent_raw, re.DOTALL):
                                    valarm_content = valarm_match.group(1)
                                    trigger_m = re.search(r"^TRIGGER[^:]*:(.+)$", valarm_content, re.MULTILINE)
                                    if trigger_m:
                                        trigger_val = trigger_m.group(1).strip()
                                        # Parse relative duration (e.g., -PT15M)
                                        if trigger_val.startswith("-PT") or trigger_val.startswith("PT"):
                                            try:
                                                # Simple parser for -PT<N>M or -PT<N>H format
                                                is_negative = trigger_val.startswith("-")
                                                clean = trigger_val.lstrip("-PT").rstrip("HMS")
                                                if "H" in trigger_val:
                                                    hours = int(clean)
                                                    delta = timedelta(hours=hours)
                                                elif "M" in trigger_val:
                                                    minutes = int(clean)
                                                    delta = timedelta(minutes=minutes)
                                                else:
                                                    delta = timedelta(0)
                                                if is_negative:
                                                    delta = -delta
                                                alarm_dt = dtstart + delta
                                                alarms.append(alarm_dt.isoformat())
                                            except Exception:
                                                pass
                                fallback_events.append({
                                    "uid": uid,
                                    "title": summary,
                                    "start_time": dtstart.isoformat(),
                                    "end_time": dtend.isoformat(),
                                    "attendees": attendees,
                                    "description": description,
                                    "location": location,
                                    "organizer": organizer,
                                    "status": status,
                                    "alarms": alarms,
                                })
                    if fallback_events:
                        events.extend(fallback_events)
                        logger.info(f"Regex fallback extracted {len(fallback_events)} VEVENT(s)")
                    else:
                        logger.info("Regex fallback found 0 VEVENT blocks")
                except Exception as rex_e:
                    logger.debug(f"Regex fallback failed: {rex_e}")
        except Exception as e:
            logger.error(f"Error parsing CalDAV events XML: {e}")
        return events
    
    async def get_raw_caldav(self, start: datetime, end: datetime) -> str:
        """Получить RAW CalDAV REPORT ответы (для диагностики)."""
        try:
            # Нормализуем диапазон как в get_events
            tz_localize = pytz.timezone(Config.TZ)
            try:
                if start.tzinfo is None:
                    start = tz_localize.localize(start)
                else:
                    start = start.astimezone(tz_localize)
                if end.tzinfo is None:
                    end = tz_localize.localize(end)
                else:
                    end = end.astimezone(tz_localize)
            except Exception:
                pass

            session = await self._get_session()
            calendars = await self.get_calendars()
            if not calendars:
                return "No calendars found"

            body = self._build_calendar_query(start, end)
            headers = {
                "Depth": "1",
                "Content-Type": "application/xml; charset=utf-8",
            }

            raw_blocks: List[str] = []
            for cal in calendars:
                cal_href = cal.get("href")
                if not cal_href:
                    continue
                if cal_href.startswith('/'):
                    cal_url = self.base_url.rstrip('/') + cal_href
                else:
                    cal_url = cal_href
                try:
                    async with session.request("REPORT", cal_url, data=body, headers=headers) as resp:
                        text = await resp.text()
                        raw_blocks.append(
                            f"<!-- href={cal_url} status={resp.status} len={len(text)} -->\n{text}"
                        )
                except Exception as req_err:
                    raw_blocks.append(f"<!-- href={cal_url} error={req_err} -->")

            if not raw_blocks:
                return "Empty response"
            return "\n\n".join(raw_blocks)
        except Exception as e:
            logger.error(f"Error getting raw CalDAV: {e}")
            return f"Error: {e}"
    
    @staticmethod
    def hash_event(event: Dict) -> str:
        """Создать хэш события для отслеживания изменений"""
        event_str = json.dumps(event, sort_keys=True, default=str)
        return hashlib.md5(event_str.encode()).hexdigest()
