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
            
            elif action == "skip_description":
                await self.skip_description(user_id, channel_id)
            
            elif action == "skip_location":
                await self.skip_location(user_id, channel_id)

            elif action == ButtonActions.NO_INVITE:
                await self.no_invite(user_id, channel_id)

            elif action == ButtonActions.CANCEL_WIZARD:
                await self.cancel_wizard(user_id, channel_id)
            
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

            # Таблица по ТЗ: название | когда | статус
            table = self.bot.logic.format_meetings_table(meetings)
            message = "**Все встречи на сегодня**\n\n" + table

            props = None
            if meetings:
                # Выпадающий список выбора встречи
                options = []
                for m in meetings:
                    uid = m.get("uid")
                    title = m.get("title", "Без названия")
                    if not uid:
                        continue
                    options.append({
                        "text": title,
                        "value": uid,
                    })

                if options:
                    attachments = [{
                        "text": "Откройте детали встречи:",
                        "actions": [{
                            "id": "selectMeeting",
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
                    props = {"attachments": attachments}

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

            table = self.bot.logic.format_meetings_table(meetings)
            message = "**Текущие и будущие встречи на сегодня**\n\n" + table

            props = None
            if meetings:
                options = []
                for m in meetings:
                    uid = m.get("uid")
                    title = m.get("title", "Без названия")
                    if not uid:
                        continue
                    options.append({
                        "text": title,
                        "value": uid,
                    })

                if options:
                    attachments = [{
                        "text": "Откройте детали встречи:",
                        "actions": [{
                            "id": "selectMeetingCurrent",
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
                    props = {"attachments": attachments}

            await self.bot.mm.send_message(channel_id, message, props=props)
        
        except Exception as e:
            logger.error(f"Error showing current meetings: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при получении встреч")
    
    async def start_create_meeting(self, user_id: str, channel_id: str):
        """Начать создание встречи"""
        try:
            from ui_messages import UIMessages
            
            message = UIMessages.create_meeting_step_1()
            await self.bot.mm.send_message(channel_id, message)
            
            # Установить состояние
            self.bot.logic.set_user_state(user_id, "creating_meeting_title")
        
        except Exception as e:
            logger.error(f"Error starting create meeting: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при создании встречи")
    
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

            await self.bot.mm.send_message(channel_id, message)
        
        except Exception as e:
            logger.error(f"Error showing meeting details: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при получении деталей встречи")


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
