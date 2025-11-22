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
            
            elif action and action.startswith(ButtonActions.SELECT_MEETING):
                meeting_id = action.replace(ButtonActions.SELECT_MEETING, "")
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
            meetings = self.bot.logic.get_today_meetings(user_id, user.email, 
                                                         self.bot.logic.encryption.decrypt(user.encrypted_password))
            
            # Форматировать таблицу
            message = "**Все встречи на сегодня**\n\n"
            message += self.bot.logic.format_meetings_table(meetings)
            
            # Показать выпадающее меню для выбора встречи
            if meetings:
                await self.bot.mm.send_message(channel_id, message)
                # TODO: Добавить интерактивное меню выбора встречи
        
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
            meetings = self.bot.logic.get_current_meetings(user_id, user.email,
                                                          self.bot.logic.encryption.decrypt(user.encrypted_password))
            
            # Форматировать таблицу
            message = "**Текущие и будущие встречи на сегодня**\n\n"
            message += self.bot.logic.format_meetings_table(meetings)
            
            await self.bot.mm.send_message(channel_id, message)
        
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
            
            # Создать встречу
            await self.bot.create_meeting(user_id, channel_id, state_data)
        
        except Exception as e:
            logger.error(f"Error skipping location: {e}")
            await self.bot.mm.send_message(channel_id, "Ошибка при пропуске места")
    
    async def show_meeting_details(self, user_id: str, channel_id: str, meeting_id: str):
        """Показать детали встречи"""
        try:
            # TODO: Получить детали встречи по ID
            pass
        
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
