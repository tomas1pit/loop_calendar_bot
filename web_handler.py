from aiohttp import web
import json
import logging
from datetime import datetime
from config import Config
from ui_messages import ButtonActions

logger = logging.getLogger(__name__)


class ActionHandler:
    def __init__(self, bot):
        self.bot = bot
    
    async def handle_action(self, request):
        """Обработать действие от интерактивной кнопки"""
        try:
            data = await request.json()
            logger.info(f"Action received: {data}")
            
            context = data.get('context', {})
            action = context.get('action')
            user_id = context.get('user_id')
            
            # Получить канал для личного сообщения (async вызов)
            channel_id = await self.bot.mm.get_channel_id(user_id)
            
            if action == ButtonActions.TODAY_ALL_MEETINGS:
                await self.show_today_all_meetings(user_id, channel_id)
            
            elif action == ButtonActions.TODAY_CURRENT_MEETINGS:
                await self.show_today_current_meetings(user_id, channel_id)
            
            elif action == ButtonActions.CREATE_MEETING:
                await self.start_create_meeting(user_id, channel_id)
            
            elif action == ButtonActions.LOGOUT:
                await self.logout_user(user_id, channel_id)
            
            elif action == ButtonActions.RAW_CALDAV:
                await self.show_raw_caldav(user_id, channel_id)
            
            elif action == "skip_description":
                await self.skip_description(user_id, channel_id)
            
            elif action == "skip_location":
                await self.skip_location(user_id, channel_id)

            elif action == ButtonActions.NO_INVITE:
                await self.no_invite(user_id, channel_id)

            elif action == ButtonActions.CANCEL_WIZARD:
                await self.cancel_wizard(user_id, channel_id)
            
            elif action == "quick_date":
                date_value = context.get("date") or (data.get("context", {}) if isinstance(data.get("context"), dict) else {}).get("date")
                await self.quick_select_date(user_id, channel_id, date_value)

            elif action == "quick_time":
                time_value = context.get("time") or (data.get("context", {}) if isinstance(data.get("context"), dict) else {}).get("time")
                await self.quick_select_time(user_id, channel_id, time_value)

            elif action == ButtonActions.SELECT_MEETING or (action and action.startswith("select_meeting")):
                # selected_option может быть либо строкой UID, либо dict {value: UID}
                selected_raw = context.get("selected_option")
                meeting_id = None
                if isinstance(selected_raw, dict):
                    meeting_id = selected_raw.get("value")
                elif isinstance(selected_raw, str):
                    meeting_id = selected_raw.strip()
                if not meeting_id:
                    data_ctx = data.get("data", {}) or {}
                    sel = data_ctx.get("selected_option")
                    if isinstance(sel, dict):
                        meeting_id = sel.get("value")
                    elif isinstance(sel, str):
                        meeting_id = sel.strip()
                if meeting_id:
                    await self.show_meeting_details(user_id, channel_id, meeting_id)
            
            return web.json_response({"status": "ok"})
        
        except Exception as e:
            logger.error(f"Error handling action: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    async def show_today_all_meetings(self, user_id: str, channel_id: str):
        """Показать все встречи на сегодня"""
        try:
            user = self.bot.logic.get_user(user_id)
            if not user:
                await self.bot.mm.send_message(channel_id, "Пожалуйста, авторизуйтесь сначала")
                return
            
            # Получить встречи
            meetings = await self.bot.logic.get_today_meetings(
                user_id,
                user.email,
                self.bot.logic.encryption.decrypt(user.encrypted_password),
            )

            message, props = self._compose_meetings_response(
                "**Все встречи на сегодня**",
                meetings,
                user_id,
                "selectMeeting"
            )

            await self.bot.mm.send_message(channel_id, message, props=props)
        
        except Exception as e:
            logger.error(f"Error showing today meetings: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при получении встреч")
    
    async def show_today_current_meetings(self, user_id: str, channel_id: str):
        """Показать текущие встречи"""
        try:
            user = self.bot.logic.get_user(user_id)
            if not user:
                await self.bot.mm.send_message(channel_id, "Пожалуйста, авторизуйтесь сначала")
                return
            
            # Получить встречи
            meetings = await self.bot.logic.get_current_meetings(
                user_id,
                user.email,
                self.bot.logic.encryption.decrypt(user.encrypted_password),
            )

            message, props = self._compose_meetings_response(
                "**Текущие и будущие встречи на сегодня**",
                meetings,
                user_id,
                "selectMeetingCurrent"
            )

            await self.bot.mm.send_message(channel_id, message, props=props)
        
        except Exception as e:
            logger.error(f"Error showing current meetings: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при получении встреч")
    
    async def start_create_meeting(self, user_id: str, channel_id: str):
        """Начать создание встречи"""
        try:
            await self.bot.ask_meeting_title(user_id, channel_id, {})
        except Exception as e:
            logger.error(f"Error starting create meeting: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при создании встречи")

    async def quick_select_date(self, user_id: str, channel_id: str, date_value: str):
        """Быстрый выбор даты встречи"""
        if not date_value:
            return
        try:
            user_state = self.bot.logic.get_user_state(user_id)
            if not user_state or user_state.state != "creating_meeting_date":
                return
            state_data = json.loads(user_state.data) if user_state.data else {}
            date_obj = self.bot.logic.validate_date(date_value)
            if not date_obj:
                await self.bot.mm.send_message(channel_id, "❌ Не удалось распознать дату. Введите вручную DD.MM.YYYY")
                return
            state_data['date'] = date_obj.isoformat()
            if user_state.message_id:
                try:
                    await self.bot.mm.update_post(user_state.message_id, f"Дата встречи: ✅ {date_value}")
                except Exception:
                    pass
            await self.bot.ask_meeting_time(user_id, channel_id, state_data)
        except Exception as e:
            logger.error(f"Error in quick date selection: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при выборе даты")

    async def quick_select_time(self, user_id: str, channel_id: str, time_value: str):
        """Быстрый выбор времени встречи"""
        if not time_value:
            return
        try:
            user_state = self.bot.logic.get_user_state(user_id)
            if not user_state or user_state.state != "creating_meeting_time":
                return
            state_data = json.loads(user_state.data) if user_state.data else {}
            time_obj = self.bot.logic.validate_time(time_value)
            if not time_obj:
                await self.bot.mm.send_message(channel_id, "❌ Не удалось распознать время. Введите вручную HH:MM")
                return
            state_data['time'] = time_obj.isoformat()
            if user_state.message_id:
                try:
                    await self.bot.mm.update_post(user_state.message_id, f"Время начала: ✅ {time_value}")
                except Exception:
                    pass
            await self.bot.ask_meeting_duration(user_id, channel_id, state_data)
        except Exception as e:
            logger.error(f"Error in quick time selection: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при выборе времени")
    
    async def logout_user(self, user_id: str, channel_id: str):
        """Разлогинить пользователя"""
        try:
            self.bot.logic.delete_user(user_id)
            self.bot.logic.clear_user_state(user_id)
            
            await self.bot.mm.send_message(channel_id, 
                "✅ Вы успешно разлогинены. Все ваши данные удалены.")
        
        except Exception as e:
            logger.error(f"Error logging out user: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при разлогинивании")
    
    async def skip_description(self, user_id: str, channel_id: str):
        """Пропустить добавление описания"""
        try:
            user_state = self.bot.logic.get_user_state(user_id)
            state_data = json.loads(user_state.data) if user_state.data else {}
            
            state_data['description'] = ""
            
            # Очистить кнопки предыдущего сообщения
            if user_state.message_id:
                try:
                    await self.bot.mm.update_post(user_state.message_id, "Описание: ✅ _пропущено_")
                except Exception:
                    pass
            
            # Перейти к вопросу про место
            await self.bot.ask_meeting_location(user_id, channel_id, state_data)
        
        except Exception as e:
            logger.error(f"Error skipping description: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при пропуске описания")
    
    async def skip_location(self, user_id: str, channel_id: str):
        """Пропустить добавление места"""
        try:
            user_state = self.bot.logic.get_user_state(user_id)
            state_data = json.loads(user_state.data) if user_state.data else {}
            
            state_data['location'] = ""
            
            # Очистить кнопки предыдущего сообщения
            if user_state.message_id:
                try:
                    await self.bot.mm.update_post(user_state.message_id, "Место: ✅ _пропущено_")
                except Exception:
                    pass
            
            # Создать встречу
            await self.bot.create_meeting(user_id, channel_id, state_data)
        
        except Exception as e:
            logger.error(f"Error skipping location: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при пропуске места")

    async def no_invite(self, user_id: str, channel_id: str):
        """Обработать кнопку "Никого не приглашать""" 
        try:
            user_state = self.bot.logic.get_user_state(user_id)
            state_data = json.loads(user_state.data) if user_state and user_state.data else {}

            state_data['attendees'] = []
            
            # Очистить кнопки предыдущего сообщения
            if user_state.message_id:
                try:
                    await self.bot.mm.update_post(user_state.message_id, "Участники: ✅ _без участников_")
                except Exception:
                    pass

            # Переходим сразу к описанию встречи
            await self.bot.ask_meeting_description(user_id, channel_id, state_data)

        except Exception as e:
            logger.error(f"Error handling no_invite: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при обработке участников")

    async def cancel_wizard(self, user_id: str, channel_id: str):
        """Отмена мастера создания встречи"""
        try:
            self.bot.logic.clear_user_state(user_id)
            await self.bot.mm.send_message(channel_id, "Диалог создания встречи отменён.")
            await self.bot.show_main_menu(user_id, channel_id)
        except Exception as e:
            logger.error(f"Error cancelling wizard: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при отмене создания встречи")
    
    async def show_meeting_details(self, user_id: str, channel_id: str, meeting_id: str):
        """Показать детали встречи"""
        try:
            user = self.bot.logic.get_user(user_id)
            if not user:
                await self.bot.mm.send_message(channel_id, "Пожалуйста, авторизуйтесь сначала")
                return

            # Берём все встречи на сегодня и ищем нужную по uid
            meetings = await self.bot.logic.get_today_meetings(
                user_id,
                user.email,
                self.bot.logic.encryption.decrypt(user.encrypted_password),
            )
            meeting = None
            for m in meetings:
                if m.get("uid") == meeting_id:
                    meeting = m
                    break

            if not meeting:
                await self.bot.mm.send_message(channel_id, "Не удалось найти эту встречу")
                return

            from ui_messages import UIMessages
            from datetime import datetime

            start_dt = datetime.fromisoformat(meeting["start_time"])
            end_dt = datetime.fromisoformat(meeting["end_time"])
            attendees = meeting.get("attendees", [])
            description = meeting.get("description", "")
            location = meeting.get("location", "")
            status = meeting.get("status", "ACCEPTED")
            organizer = meeting.get("organizer", "")


            message = UIMessages.meeting_details(
                meeting.get("title", "Без названия"),
                start_dt,
                end_dt,
                attendees,
                description,
                location,
                status,
                organizer,
            )

            # Получаем состояние пользователя для хранения message_id
            user_state = self.bot.logic.get_user_state(user_id)
            if user_state and user_state.message_id:
                # Обновляем предыдущее сообщение
                await self.bot.mm.update_post(user_state.message_id, message)
                # message_id не меняется
            else:
                # Отправляем новое сообщение и сохраняем его id
                msg_id = await self.bot.mm.send_message(channel_id, message)
                self.bot.logic.set_user_state(user_id, user_state.state if user_state else None, message_id=msg_id)
        
        except Exception as e:
            logger.error(f"Error showing meeting details: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при получении деталей встречи")
    
    async def show_raw_caldav(self, user_id: str, channel_id: str):
        """Показать RAW CalDAV ответ"""
        try:
            user = self.bot.logic.get_user(user_id)
            if not user:
                await self.bot.mm.send_message(channel_id, "Пожалуйста, авторизуйтесь сначала")
                return
            
            from datetime import datetime, timedelta
            import pytz
            from config import Config
            
            # Получить события на сегодня
            tz = pytz.timezone(Config.TZ)
            now = datetime.now(tz)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            
            # Создать CalDAV manager
            from caldav_manager import CalDAVManager
            caldav_manager = CalDAVManager(
                user.email,
                self.bot.logic.encryption.decrypt(user.encrypted_password)
            )
            
            # Получить RAW XML
            raw_xml = await caldav_manager.get_raw_caldav(start, end)
            
            # Отправить в виде code block (разбить на куски если длинный)
            max_length = 3500
            if len(raw_xml) > max_length:
                chunks = [raw_xml[i:i+max_length] for i in range(0, len(raw_xml), max_length)]
                for i, chunk in enumerate(chunks):
                    await self.bot.mm.send_message(channel_id, f"```xml\\n{chunk}\\n```")
            else:
                await self.bot.mm.send_message(channel_id, f"```xml\\n{raw_xml}\\n```")
            
            await caldav_manager.close()
        
        except Exception as e:
            logger.error(f"Error showing raw caldav: {e}")
            await self.bot.mm.send_message(channel_id, f"Ошибка при получении RAW CalDAV: {e}")

    def _compose_meetings_response(self, title: str, meetings: list, user_id: str, control_id: str):
        table = self.bot.logic.format_meetings_table(meetings)
        message = f"{title}\n\n{table}"
        attachments = self._build_meeting_select_attachment(meetings, user_id, control_id)
        props = {"attachments": attachments} if attachments else None
        return message, props

    def _build_meeting_select_attachment(self, meetings: list, user_id: str, control_id: str):
        if not meetings:
            return None

        options = []
        for meeting in meetings:
            uid = meeting.get("uid")
            title = meeting.get("title", "Без названия")
            if not uid:
                continue
            options.append({
                "text": title,
                "value": uid,
            })

        if not options:
            return None

        return [{
            "text": "Откройте детали встречи:",
            "actions": [{
                "id": control_id,
                "name": "Выберите встречу",
                "type": "select",
                "options": options,
                "integration": {
                    "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                    "context": {
                        "action": ButtonActions.SELECT_MEETING,
                        "user_id": user_id,
                    },
                },
            }],
        }]


async def start_web_server(bot, host: str = "0.0.0.0", port: int = 8080):
    """Запустить веб-сервер для обработки действий"""
    app = web.Application()
    handler = ActionHandler(bot)
    
    # Совместимость с существующей инфраструктурой:
    # Mattermost бьёт в публичный URL вида <MM_ACTIONS_URL>/mattermost/actions,
    # поэтому здесь обрабатываем этот путь напрямую, а '/actions' оставляем как локальный.
    app.router.add_post('/mattermost/actions', handler.handle_action)
    app.router.add_post('/actions', handler.handle_action)
    app.router.add_get('/health', lambda r: web.json_response({"status": "ok"}))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"Web server started on {host}:{port}")
    return runner
