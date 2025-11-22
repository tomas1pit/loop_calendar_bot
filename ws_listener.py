import threading
import json
import logging
import time
import requests
from websocket import create_connection, WebSocketConnectionClosedException
from config import Config

logger = logging.getLogger(__name__)


class MattermostWebSocketListener:
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.running = False
        self.thread = None
        self.reconnect_delay = 3
        self.seq = 1
    
    def connect(self):
        """Подключиться к WebSocket Mattermost (синхронно в отдельном потоке)"""
        self.thread = threading.Thread(target=self._connect_loop, daemon=True)
        self.thread.start()
        logger.info("WebSocket listener thread started")
    
    def _connect_loop(self):
        """Основной цикл подключения с переподключением"""
        self.running = True
        
        while self.running:
            try:
                # Получить WebSocket URL
                ws_url = Config.MATTERMOST_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
                ws_url += "/api/v4/websocket"
                
                logger.info(f"Connecting to WebSocket: {ws_url}")
                
                # Создать соединение БЕЗ timeout при подключении
                self.ws = create_connection(ws_url)
                
                logger.info("WebSocket connection established")
                
                # Отправить аутентификацию СРАЗУ (до получения hello)
                auth_msg = {
                    "seq": self.seq,
                    "action": "authentication_challenge",
                    "data": {
                        "token": Config.MATTERMOST_BOT_TOKEN
                    }
                }
                self.seq += 1
                
                self.ws.send(json.dumps(auth_msg))
                logger.debug("Sent authentication message")
                
                # Теперь запустить цикл слушания
                self._listen()
            
            except WebSocketConnectionClosedException:
                logger.warning(f"WebSocket connection closed. Reconnecting in {self.reconnect_delay} seconds...")
                if self.running:
                    time.sleep(self.reconnect_delay)
            
            except Exception as e:
                logger.error(f"Error in WebSocket connection: {e}")
                if self.running:
                    time.sleep(self.reconnect_delay)
    
    def _listen(self):
        """Слушать события от WebSocket (синхронно)"""
        try:
            while self.running and self.ws:
                try:
                    # Получить сообщение БЕЗ timeout (блокирующий вызов)
                    message = self.ws.recv()
                    
                    if not message:
                        continue
                    
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        logger.debug(f"Invalid JSON received: {message}")
                        continue
                    
                    event_type = data.get('event')
                    
                    # Логируем ВСЕ события с полной информацией
                    logger.info(f"=== WebSocket EVENT ===")
                    logger.info(f"Event type: {event_type}")
                    logger.info(f"Full data: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    logger.info(f"======================")
                    
                    if event_type == "posted":
                        logger.info(f"Posted event received - processing...")
                        self.handle_posted(data)
                    elif event_type == "status_change":
                        logger.info(f"Status change event received - processing...")
                        self.handle_status_change(data)
                    else:
                        # Логируем другие события
                        logger.info(f"Received other event: {event_type}")
                
                except WebSocketConnectionClosedException:
                    logger.info("WebSocket connection closed during listen")
                    break
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    break
        
        except Exception as e:
            logger.error(f"Error in WebSocket listen: {e}", exc_info=True)
        
        finally:
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            self.ws = None
    
    def handle_posted(self, data: dict):
        """Обработать событие posted (новое сообщение)"""
        try:
            # post находится в data.post, а не в broadcast.post
            post_data = data.get('data', {})
            post_str = post_data.get('post')
            
            if not post_str:
                logger.warning("Posted event has no post data in data.post")
                return
            
            # post - это JSON строка, парсируем её
            if isinstance(post_str, str):
                try:
                    post = json.loads(post_str)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse post JSON: {e}")
                    return
            else:
                post = post_str
            
            message = post.get('message', '')
            user_id = post.get('user_id', '')
            channel_id = post.get('channel_id', '')
            post_id = post.get('id', '')
            
            logger.info(f"=== POSTED MESSAGE ===")
            logger.info(f"User ID: {user_id}")
            logger.info(f"Channel ID: {channel_id}")
            logger.info(f"Post ID: {post_id}")
            logger.info(f"Message: {message}")
            logger.info(f"Full post: {json.dumps(post, ensure_ascii=False, indent=2)}")
            logger.info(f"======================")
            
            # Проверить, упоминается ли бот
            bot_name = Config.BOT_NAME.lower()
            message_lower = message.lower()

            # 1) Если бот явно упомянут — запускаем логику меню/авторизации
            if f"@{bot_name}" in message_lower or bot_name in message_lower:
                logger.info(f"✓ Bot @{bot_name} mentioned in message!")

                # Проверяем, авторизован ли пользователь
                try:
                    user = self.bot.logic.get_user(user_id)
                except Exception as e:
                    logger.error(f"Error checking user in DB: {e}", exc_info=True)
                    user = None

                if not user:
                    logger.info("User is not authorized yet, sending auth prompt instead of menu")
                    self._send_auth_prompt(user_id)
                else:
                    # Пользователь авторизован — отправляем главное меню
                    self._send_menu_reply(user_id, channel_id, post_id)
                return

            # 2) Если бот НЕ упомянут, но у пользователя есть активное состояние диалога,
            #    передаём сообщение в Bot.handle_dialog_step (пароль, шаги мастера и т.п.)
            try:
                user_state = self.bot.logic.get_user_state(user_id)
            except Exception as e:
                logger.error(f"Error getting user state: {e}", exc_info=True)
                user_state = None

            if user_state and user_state.state:
                logger.info(f"User {user_id} has active state '{user_state.state}', passing message to dialog handler")
                try:
                    # Вызываем асинхронный обработчик из sync-потока через asyncio.run
                    import asyncio
                    asyncio.run(self.bot.handle_dialog_step(user_id, channel_id, user_state, message))
                except RuntimeError:
                    # Если цикл уже запущен (например, в том же процессе), используем create_task
                    try:
                        loop = asyncio.get_event_loop()
                        loop.create_task(self.bot.handle_dialog_step(user_id, channel_id, user_state, message))
                    except Exception as e:
                        logger.error(f"Failed to schedule dialog handler task: {e}", exc_info=True)
                return

            logger.info(f"✗ Bot @{bot_name} NOT mentioned and no active state (message: {message[:100]})")
        
        except Exception as e:
            logger.error(f"Error handling posted event: {e}", exc_info=True)
    
    def handle_status_change(self, data: dict):
        """Обработать изменение статуса"""
        try:
            broadcast = data.get('broadcast', {})
            logger.debug(f"Status change: {broadcast}")
            
            # TODO: Обработать изменение статуса (если нужно)
        
        except Exception as e:
            logger.error(f"Error handling status change: {e}")
    
    def disconnect(self):
        """Отключиться от WebSocket"""
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        logger.info("WebSocket disconnected")

    def _send_auth_prompt(self, user_id: str):
        """Отправить сообщение с инструкцией по авторизации в личный чат"""
        try:
            logger.info(f"Sending auth prompt to user {user_id}")

            from ui_messages import UIMessages

            base_url = Config.MATTERMOST_BASE_URL.rstrip('/')
            headers = {
                'Authorization': f'Bearer {Config.MATTERMOST_BOT_TOKEN}',
                'Content-Type': 'application/json'
            }

            # Получить email пользователя из Mattermost через HTTP API
            try:
                user_resp = requests.get(
                    f"{base_url}/api/v4/users/{user_id}",
                    headers=headers,
                    timeout=10,
                    verify=False
                )
                if user_resp.status_code != 200:
                    logger.error(f"Failed to get MM user: HTTP {user_resp.status_code}, response: {user_resp.text}")
                    email = ""
                else:
                    email = user_resp.json().get('email', '')
            except Exception as e:
                logger.error(f"Error requesting MM user info: {e}", exc_info=True)
                email = ""

            # Текст по ТЗ
            try:
                message_text = UIMessages.auth_required(email)
            except Exception:
                # Фоллбек, если UIMessages недоступен
                message_text = (
                    "Привет! Для начала надо авторизоваться в календаре.\n\n"
                    "1) Создайте пароль приложения для почты Mail.ru.\n"
                    "2) Отправьте мне этот пароль одним сообщением."
                )

            # Создаем/получаем личный канал: Mattermost ждёт [bot_id, user_id]
            channel_resp = requests.post(
                f"{base_url}/api/v4/channels/direct",
                headers=headers,
                json=[self.bot.mm.user.get('id'), user_id] if getattr(self.bot, 'mm', None) and getattr(self.bot.mm, 'user', None) else [user_id],
                timeout=10,
                verify=False
            )
            if channel_resp.status_code not in [200, 201]:
                logger.error(f"Failed to get direct channel for auth prompt: HTTP {channel_resp.status_code}, response: {channel_resp.text}")
                return

            dm_channel = channel_resp.json()
            dm_channel_id = dm_channel.get('id')

            post_data = {
                'channel_id': dm_channel_id,
                'message': message_text
            }

            resp = requests.post(
                f"{base_url}/api/v4/posts",
                headers=headers,
                json=post_data,
                timeout=10,
                verify=False
            )

            if resp.status_code == 201:
                logger.info("Auth prompt sent successfully to direct channel")
            else:
                logger.error(f"Failed to send auth prompt: HTTP {resp.status_code}, response: {resp.text}")

            # Зафиксировать состояние пользователя как ожидающего пароль
            try:
                self.bot.logic.set_user_state(user_id, "awaiting_password", {"email": email})
            except Exception as e:
                logger.error(f"Failed to set user state awaiting_password: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in _send_auth_prompt: {e}", exc_info=True)
    
    def _send_menu_reply(self, user_id: str, channel_id: str, root_id: str):
        """Отправить главное меню в ответ на упоминание (в личный чат)"""
        try:
            logger.info(f"Sending menu to user {user_id}")
            
            # Используем синхронный HTTP запрос напрямую
            base_url = Config.MATTERMOST_BASE_URL.rstrip('/')
            headers = {
                'Authorization': f'Bearer {Config.MATTERMOST_BOT_TOKEN}',
                'Content-Type': 'application/json'
            }
            
            # Получить прямой канал с пользователем: Mattermost ждёт [bot_id, user_id]
            logger.info(f"Getting direct channel with user {user_id}...")
            channel_response = requests.post(
                f"{base_url}/api/v4/channels/direct",
                headers=headers,
                json=[self.bot.mm.user.get('id'), user_id] if getattr(self.bot, 'mm', None) and getattr(self.bot.mm, 'user', None) else [user_id],
                timeout=10,
                verify=False
            )
            
            if channel_response.status_code not in [200, 201]:
                logger.error(f"Failed to get direct channel: HTTP {channel_response.status_code}, response: {channel_response.text}")
                return
            
            dm_channel = channel_response.json()
            dm_channel_id = dm_channel.get('id')
            logger.info(f"Direct channel ID: {dm_channel_id}")
            
            # Создать меню с кнопками (attachments)
            menu_text = "**Главное меню**\n\nВыберите действие:"
            
            attachments = [
                {
                    "text": "Выберите действие:",
                    "actions": [
                        {
                            "id": "show_today_all",
                            "name": "📅 Все встречи на сегодня",
                            "type": "button",
                            "style": "primary",
                            "integration": {
                                "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                                "context": {
                                    "action": "show_today_all_meetings",
                                    "user_id": user_id
                                }
                            }
                        },
                        {
                            "id": "show_today_current",
                            "name": "⏱️ Текущие встречи",
                            "type": "button",
                            "integration": {
                                "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                                "context": {
                                    "action": "show_today_current_meetings",
                                    "user_id": user_id
                                }
                            }
                        },
                        {
                            "id": "create_meeting",
                            "name": "➕ Создать встречу",
                            "type": "button",
                            "style": "primary",
                            "integration": {
                                "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                                "context": {
                                    "action": "create_meeting",
                                    "user_id": user_id
                                }
                            }
                        },
                        {
                            "id": "logout",
                            "name": "🚪 Разлогиниться",
                            "type": "button",
                            "style": "danger",
                            "integration": {
                                "url": f"{Config.MM_ACTIONS_URL}/mattermost/actions",
                                "context": {
                                    "action": "logout",
                                    "user_id": user_id
                                }
                            }
                        }
                    ]
                }
            ]
            
            post_data = {
                'channel_id': dm_channel_id,
                'message': menu_text,
                'props': {
                    'attachments': attachments
                }
            }
            
            logger.info("Sending menu with buttons...")
            response = requests.post(
                f"{base_url}/api/v4/posts",
                headers=headers,
                json=post_data,
                timeout=10,
                verify=False
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 201:
                logger.info("Menu sent successfully to direct channel")
            else:
                logger.error(f"Failed to send menu: HTTP {response.status_code}, response: {response.text}")
        
        except Exception as e:
            logger.error(f"Error in _send_menu_reply: {e}", exc_info=True)
