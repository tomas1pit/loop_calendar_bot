import asyncio
import logging
from datetime import datetime, timedelta, time as _time
import json
from typing import Dict
import threading
import time
from config import Config
from database import DatabaseManager, User
from mattermost_manager import MattermostManager
from bot_logic import BotLogic
from ui_messages import UIMessages, ButtonActions
from notification_manager import NotificationManager
from ws_listener import MattermostWebSocketListener
from web_handler import start_web_server
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Bot:
    def __init__(self):
        self.db = DatabaseManager(Config.DB_PATH)
        self.mm = MattermostManager(Config.MATTERMOST_BASE_URL, 
                                    Config.MATTERMOST_BOT_TOKEN,
                                    Config.BOT_NAME)
        self.logic = BotLogic(self.db, self.mm)
        self.notification_manager = NotificationManager(self.db, self.mm, self.logic)
        self.ws_listener = MattermostWebSocketListener(self)
        self.running = False
        self.web_runner = None
        # Основной event loop будет сохранён при старте
        self.loop = None
        self.loop_ready = threading.Event()

    async def ask_meeting_title(self, user_id: str, channel_id: str, state_data: Dict = None):
        """Попросить название встречи с кнопкой Отменить"""
        message = UIMessages.create_meeting_step_1()
        attachments = [{
            "fallback": "Cancel",
            "actions": [{
                "name": "Отменить",
                "style": "danger",
                "type": "button",
                "integration": {
                    "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                    "context": {
                        "action": ButtonActions.CANCEL_WIZARD,
                        "user_id": user_id,
                    },
                },
            }],
        }]
        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = post.get('id') if isinstance(post, dict) else post
        self.logic.set_user_state(user_id, "creating_meeting_title", state_data or {}, post_id)
    
    def start(self):
        """Запустить бота"""
        logger.info("Starting calendar bot...")
        
        self.running = True
        self.loop_ready.clear()
        
        # Запустить основной цикл
        try:
            asyncio.run(self.run_main_loop())
        except KeyboardInterrupt:
            logger.info("Bot interrupted")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """Остановить бота"""
        logger.info("Stopping bot...")
        if not self.running:
            return

        self.running = False
        asyncio.run(self._cleanup())
        self.db.close()
    
    async def _cleanup(self):
        """Очистка ресурсов"""
        # Остановить WebSocket
        self.ws_listener.running = False
        
        # Остановить Mattermost сессию
        await self.mm.disconnect()
        
        # Остановить веб-сервер
        if self.web_runner:
            await self.web_runner.cleanup()
    
    async def run_main_loop(self):
        """Основной цикл бота"""
        # Сохранить текущий event loop, чтобы использовать его из других потоков
        self.loop = asyncio.get_running_loop()
        self.loop_ready.set()
        # Подключиться к Mattermost
        if not await self.mm.connect():
            logger.error("Failed to connect to Mattermost")
            return False
        
        logger.info("Bot connected successfully")
        
        # Запустить WebSocket слушатель (синхронный в отдельном потоке)
        self.ws_listener.connect()
        logger.info("WebSocket listener started")
        
        # Запустить веб-сервер для обработки действий (вебхуки и интерактивные кнопки)
        self.web_runner = await start_web_server(self, "0.0.0.0", 8080)
        logger.info("Waiting for webhooks and button actions...")
        
        # Запустить цикл проверки уведомлений
        check_task = asyncio.create_task(self.check_notifications_loop())
        
        try:
            await check_task
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.running = False
    
    async def check_notifications_loop(self):
        """Цикл проверки и отправки уведомлений"""
        interval = max(1, Config.CHECK_INTERVAL)
        next_tick = self._next_schedule_tick(interval)

        while self.running:
            await self._sleep_until(next_tick)
            if not self.running:
                break

            try:
                session = self.db.get_session()
                try:
                    users = session.query(User).all()
                finally:
                    session.close()

                notification_count = await self.notification_manager.check_and_notify(users)

                if notification_count > 0:
                    logger.info(f"Sent {notification_count} notifications")

            except Exception as e:
                logger.error(f"Error in notifications loop: {e}")

            next_tick = self._next_schedule_tick(interval)
    
    async def handle_message(self, user_id: str, message: str, channel_id: str):
        """Обработать входящее сообщение"""
        logger.info(f"Message from {user_id}: {message}")
        
        # Проверить, упоминается ли бот
        if f"@{Config.BOT_NAME}" not in message:
            return
        
        # Получить пользователя
        user = self.logic.get_user(user_id)
        
        if not user:
            # Пользователь не авторизован
            await self.show_auth_prompt(user_id, channel_id)
            return
        
        # Получить состояние пользователя
        user_state = self.logic.get_user_state(user_id)
        
        if user_state:
            # Пользователь находится в процессе диалога
            await self.handle_dialog_step(user_id, channel_id, user_state, message)
        else:
            # Показать главное меню
            await self.show_main_menu(user_id, channel_id)
    
    async def handle_auth_message(self, user_id: str, channel_id: str, password: str):
        """Обработать ввод пароля при авторизации"""
        user = self.logic.get_user(user_id)

        if not user:
            # Попробовать взять email из сохранённого стейта (его кладёт ws_listener._send_auth_prompt)
            user_state = self.logic.get_user_state(user_id)
            email = ''
            if user_state and user_state.data:
                try:
                    state_data = json.loads(user_state.data)
                    email = state_data.get('email', '')
                except Exception:
                    email = ''

            if not email:
                # Фоллбек: берём email из текущего пользователя Mattermost (self.mm.user)
                email = (self.mm.user or {}).get('email', '')

            if not email:
                await self.mm.send_message(channel_id,
                    "Не удалось получить ваш email. Пожалуйста, попробуйте позже.")
                return

            # Создать пользователя с новым паролем
            self.logic.create_user(user_id, email, password)
            logger.info(f"User {user_id} authenticated with email {email}")

            # Очистить состояние авторизации
            self.logic.clear_user_state(user_id)

            # Показать главное меню
            await self.show_main_menu(user_id, channel_id)
    
    async def show_auth_prompt(self, user_id: str, channel_id: str):
        """Показать запрос авторизации"""
        try:
            # В актуальной логике WS уже отправляет auth prompt и ставит состояние,
            # поэтому здесь можно просто продублировать сообщение при необходимости.
            mm_user_email = (self.mm.user or {}).get('email', '')
            message = UIMessages.auth_required(mm_user_email)
            await self.mm.send_message(channel_id, message)
        except Exception as e:
            logger.error(f"Error showing auth prompt: {e}")
            await self.mm.send_message(channel_id, "Произошла ошибка. Пожалуйста, попробуйте позже.")
    
    async def show_main_menu(self, user_id: str, channel_id: str):
        """Показать главное меню"""
        try:
            message = UIMessages.main_menu_message()
            
            # Создать интерактивные кнопки
            attachments = [{
                "fallback": "Main Menu",
                "color": "#3AA3E3",
                "actions": [
                    {
                        "name": "Все встречи на сегодня",
                        "integration": {
                            "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                            "context": {
                                "action": ButtonActions.TODAY_ALL_MEETINGS,
                                "user_id": user_id
                            }
                        }
                    },
                    {
                        "name": "Текущие встречи",
                        "integration": {
                            "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                            "context": {
                                "action": ButtonActions.TODAY_CURRENT_MEETINGS,
                                "user_id": user_id
                            }
                        }
                    },
                    {
                        "name": "Создать встречу",
                        "integration": {
                            "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                            "context": {
                                "action": ButtonActions.CREATE_MEETING,
                                "user_id": user_id
                            }
                        }
                    },
                    {
                        "name": "RAW CALDAV",
                        "integration": {
                            "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                            "context": {
                                "action": ButtonActions.RAW_CALDAV,
                                "user_id": user_id
                            }
                        }
                    },
                    {
                        "name": "Разлогиниться",
                        "integration": {
                            "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                            "context": {
                                "action": ButtonActions.LOGOUT,
                                "user_id": user_id
                            }
                        },
                        "style": "danger"
                    }
                ]
            }]
            
            await self.mm.create_post_with_attachments(channel_id, message, attachments)
            
            # Очистить состояние пользователя
            self.logic.clear_user_state(user_id)
        except Exception as e:
            logger.error(f"Error showing main menu: {e}")
    
    async def handle_dialog_step(self, user_id: str, channel_id: str, 
                                user_state, message: str):
        """Обработать шаг диалога"""
        current_state = user_state.state
        state_data = json.loads(user_state.data) if user_state.data else {}
        
        if current_state == "awaiting_password":
            await self.handle_auth_message(user_id, channel_id, message.strip())
        
        elif current_state == "creating_meeting_title":
            state_data['title'] = message.strip()
            # Скрыть кнопку Отменить после ввода названия
            if user_state.message_id:
                try:
                    await self.mm.update_post(user_state.message_id, f"Название встречи: ✅ {message.strip()}")
                except Exception:
                    pass
            await self.ask_meeting_date(user_id, channel_id, state_data)
        
        elif current_state == "creating_meeting_date":
            date_obj = self.logic.validate_date(message.strip())
            if date_obj:
                state_data['date'] = date_obj.isoformat()
                # Очистить кнопки предыдущего сообщения
                if user_state.message_id:
                    try:
                        await self.mm.update_post(user_state.message_id, f"Дата встречи: ✅ {message.strip()}")
                    except Exception:
                        pass
                await self.ask_meeting_time(user_id, channel_id, state_data)
            else:
                await self.mm.send_message(channel_id, 
                    "❌ Некорректный формат даты. Попробуйте снова (DD.MM.YYYY)")
        
        elif current_state == "creating_meeting_time":
            time_obj = self.logic.validate_time(message.strip())
            if time_obj:
                state_data['time'] = time_obj.isoformat()
                # Очистить кнопки
                if user_state.message_id:
                    try:
                        await self.mm.update_post(user_state.message_id, f"Время начала: ✅ {message.strip()}")
                    except Exception:
                        pass
                await self.ask_meeting_duration(user_id, channel_id, state_data)
            else:
                await self.mm.send_message(channel_id,
                    "❌ Некорректный формат времени. Попробуйте снова (HH:MM)")
        
        elif current_state == "creating_meeting_duration":
            minutes = self.logic.validate_minutes(message.strip())
            if minutes:
                state_data['duration'] = minutes
                # Очистить кнопки
                if user_state.message_id:
                    try:
                        await self.mm.update_post(user_state.message_id, f"Длительность: ✅ {message.strip()} мин")
                    except Exception:
                        pass
                await self.ask_meeting_attendees(user_id, channel_id, state_data)
            else:
                await self.mm.send_message(channel_id,
                    "❌ Введите корректное количество минут (1-1440)")
        
        elif current_state == "creating_meeting_attendees":
            attendees = await self.logic.parse_attendees(message)
            state_data['attendees'] = attendees
            # Очистить кнопки
            if user_state.message_id:
                try:
                    att_str = ", ".join(attendees) if attendees else "без участников"
                    await self.mm.update_post(user_state.message_id, f"Участники: ✅ {att_str}")
                except Exception:
                    pass
            await self.ask_meeting_description(user_id, channel_id, state_data)
        
        elif current_state == "creating_meeting_description":
            state_data['description'] = message.strip()
            # Очистить кнопки
            if user_state.message_id:
                try:
                    desc_preview = message.strip()[:50] + "..." if len(message.strip()) > 50 else message.strip()
                    await self.mm.update_post(user_state.message_id, f"Описание: ✅ {desc_preview}")
                except Exception:
                    pass
            await self.ask_meeting_location(user_id, channel_id, state_data)
        
        elif current_state == "creating_meeting_location":
            state_data['location'] = message.strip()
            # Очистить кнопки
            if user_state.message_id:
                try:
                    loc_preview = message.strip()[:50] + "..." if len(message.strip()) > 50 else message.strip()
                    await self.mm.update_post(user_state.message_id, f"Место: ✅ {loc_preview}")
                except Exception:
                    pass
            await self.create_meeting(user_id, channel_id, state_data)
    
    async def ask_meeting_date(self, user_id: str, channel_id: str, state_data: Dict):
        """Попросить дату встречи"""
        today_dt = datetime.now()
        today = today_dt.strftime("%d.%m.%Y")
        tomorrow = (today_dt + timedelta(days=1)).strftime("%d.%m.%Y")
        after_tomorrow = (today_dt + timedelta(days=2)).strftime("%d.%m.%Y")
        message = UIMessages.create_meeting_step_3(today)
        attachments = [{
            "fallback": "Быстрый выбор даты",
            "actions": [
                {"name": "Сегодня", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": "quick_date", "user_id": user_id, "date": today}}},
                {"name": "Завтра", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": "quick_date", "user_id": user_id, "date": tomorrow}}},
                {"name": "Послезавтра", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": "quick_date", "user_id": user_id, "date": after_tomorrow}}},
                {"name": "Отменить", "style": "danger", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": ButtonActions.CANCEL_WIZARD, "user_id": user_id}}}
            ]
        }]
        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = post.get('id') if isinstance(post, dict) else post
        self.logic.set_user_state(user_id, "creating_meeting_date", state_data, post_id)
    
    async def ask_meeting_time(self, user_id: str, channel_id: str, state_data: Dict):
        """Попросить время начала встречи"""
        message = UIMessages.create_meeting_step_5()
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0).strftime("%H:%M")
        plus_60 = (now + timedelta(minutes=60)).strftime("%H:%M")
        attachments = [{
            "fallback": "Быстрый выбор времени",
            "actions": [
                {"name": "В следующий час", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": "quick_time", "user_id": user_id, "time": next_hour}}},
                {"name": "Через час", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": "quick_time", "user_id": user_id, "time": plus_60}}},
                {"name": "Отменить", "style": "danger", "type": "button", "integration": {"url": f"{Config.MM_ACTIONS_URL}/mattermost/actions", "context": {"action": ButtonActions.CANCEL_WIZARD, "user_id": user_id}}}
            ]
        }]
        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = post.get('id') if isinstance(post, dict) else post
        self.logic.set_user_state(user_id, "creating_meeting_time", state_data, post_id)
    
    async def ask_meeting_duration(self, user_id: str, channel_id: str, state_data: Dict):
        """Попросить продолжительность встречи"""
        message = UIMessages.create_meeting_step_7()

        attachments = [{
            "fallback": "Cancel",
            "actions": [{
                "name": "Отменить",
                "style": "danger",
                "type": "button",
                "integration": {
                    "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                    "context": {
                        "action": ButtonActions.CANCEL_WIZARD,
                        "user_id": user_id,
                    },
                },
            }],
        }]

        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = None
        if post:
            post_id = post.get('id') if isinstance(post, dict) else post
        
        self.logic.set_user_state(user_id, "creating_meeting_duration", state_data, post_id)
    
    async def ask_meeting_attendees(self, user_id: str, channel_id: str, state_data: Dict):
        """Попросить участников встречи"""
        message = UIMessages.create_meeting_step_9()

        # Кнопки «Никого не приглашать» и «Отменить»
        attachments = [{
            "fallback": "Attendees actions",
            "actions": [
                {
                    "name": "Никого не приглашать",
                    "style": "primary",
                    "type": "button",
                    "integration": {
                        "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                        "context": {
                            "action": ButtonActions.NO_INVITE,
                            "user_id": user_id,
                        },
                    },
                },
                {
                    "name": "Отменить",
                    "style": "danger",
                    "type": "button",
                    "integration": {
                        "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                        "context": {
                            "action": ButtonActions.CANCEL_WIZARD,
                            "user_id": user_id,
                        },
                    },
                },
            ],
        }]

        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = None
        if post:
            post_id = post.get('id') if isinstance(post, dict) else post
        
        self.logic.set_user_state(user_id, "creating_meeting_attendees", state_data, post_id)
    
    async def ask_meeting_description(self, user_id: str, channel_id: str, state_data: Dict):
        """Попросить описание встречи"""
        message = UIMessages.create_meeting_step_11()
        
        attachments = [{
            "fallback": "Description actions",
            "actions": [
                {
                    "name": "Не добавлять",
                    "type": "button",
                    "integration": {
                        "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                        "context": {
                            "action": "skip_description",
                            "user_id": user_id,
                        },
                    },
                },
                {
                    "name": "Отменить",
                    "style": "danger",
                    "type": "button",
                    "integration": {
                        "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                        "context": {
                            "action": ButtonActions.CANCEL_WIZARD,
                            "user_id": user_id,
                        },
                    },
                },
            ],
        }]
        
        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = None
        if post:
            post_id = post.get('id') if isinstance(post, dict) else post
        
        self.logic.set_user_state(user_id, "creating_meeting_description", state_data, post_id)
    
    async def ask_meeting_location(self, user_id: str, channel_id: str, state_data: Dict):
        """Попросить место встречи"""
        message = UIMessages.create_meeting_step_13()
        
        attachments = [{
            "fallback": "Location actions",
            "actions": [
                {
                    "name": "Не добавлять",
                    "type": "button",
                    "integration": {
                        "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                        "context": {
                            "action": "skip_location",
                            "user_id": user_id,
                        },
                    },
                },
                {
                    "name": "Отменить",
                    "style": "danger",
                    "type": "button",
                    "integration": {
                        "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                        "context": {
                            "action": ButtonActions.CANCEL_WIZARD,
                            "user_id": user_id,
                        },
                    },
                },
            ],
        }]
        
        post = await self.mm.create_post_with_attachments(channel_id, message, attachments)
        post_id = None
        if post:
            post_id = post.get('id') if isinstance(post, dict) else post
        
        self.logic.set_user_state(user_id, "creating_meeting_location", state_data, post_id)
    
    async def create_meeting(self, user_id: str, channel_id: str, state_data: Dict):
        """Создать встречу в календаре"""
        try:
            user = self.logic.get_user(user_id)
            if not user:
                await self.mm.send_message(channel_id, "Ошибка: пользователь не авторизован")
                return
            
            title = state_data.get('title', '')
            attendees = state_data.get('attendees', []) or []
            description = state_data.get('description', '') or ''
            location = state_data.get('location', '') or ''

            # Собираем дату/время начала и конца с учётом TZ
            date_iso = state_data.get('date')  # iso строки из validate_date
            time_iso = state_data.get('time')  # iso строки из validate_time
            duration_min = state_data.get('duration', 30)

            if not date_iso or not time_iso:
                await self.mm.send_message(channel_id, "Ошибка: не удалось распознать дату или время встречи")
                return

            # date_iso содержит локализованный datetime (с таймзоной), time_iso — время без TZ
            start_date = datetime.fromisoformat(date_iso)
            try:
                time_only = _time.fromisoformat(time_iso)
            except ValueError:
                await self.mm.send_message(channel_id, "Ошибка: неверный формат времени встречи")
                return

            start = start_date.replace(hour=time_only.hour, minute=time_only.minute,
                                       second=0, microsecond=0)
            end = start + timedelta(minutes=int(duration_min))

            from caldav_manager import CalDAVManager

            caldav = CalDAVManager(user.email, self.logic.encryption.decrypt(user.encrypted_password))
            created_ok = await caldav.create_event(
                title=title,
                start=start,
                end=end,
                attendees=attendees,
                description=description,
                location=location,
            )
            await caldav.close()

            if not created_ok:
                await self.mm.send_message(channel_id, "Не удалось создать встречу в календаре")
                return

            message = UIMessages.meeting_created(title,
                                                start,
                                                end,
                                                attendees,
                                                description,
                                                location)
            
            await self.mm.send_message(channel_id, message)
            
            # Показать главное меню
            await self.show_main_menu(user_id, channel_id)
        except Exception as e:
            logger.error(f"Error creating meeting: {e}")
            await self.mm.send_message(channel_id, "Ошибка при создании встречи")

    def _next_schedule_tick(self, interval: int) -> float:
        """Рассчитать ближайший запуск с выравниванием по интервалу (секунды -> 00)."""
        now = time.time()
        slot = int(now // interval) * interval
        tolerance = 0.05
        if now - slot > tolerance:
            slot += interval
        return slot

    async def _sleep_until(self, timestamp: float):
        """Асинхронно дождаться заданного времени перед запуском задач."""
        delay = max(0.0, timestamp - time.time())
        if delay > 0:
            await asyncio.sleep(delay)


if __name__ == "__main__":
    bot = Bot()
    bot.start()
