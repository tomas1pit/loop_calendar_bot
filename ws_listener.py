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
        self._loop_wait_timeout = 5
        self._base_url = Config.MATTERMOST_BASE_URL.rstrip('/')

    def _get_bot_loop(self):
        """Получить event loop бота, дождавшись его готовности при необходимости."""
        loop = getattr(self.bot, "loop", None)
        if loop is not None:
            return loop
        loop_ready = getattr(self.bot, "loop_ready", None)
        if loop_ready:
            loop_ready.wait(timeout=self._loop_wait_timeout)
            loop = getattr(self.bot, "loop", None)
        return loop
    
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
                    
                    # # Логируем ВСЕ события с полной информацией
                    # logger.info(f"=== WebSocket EVENT ===")
                    # logger.info(f"Event type: {event_type}")
                    # logger.info(f"Full data: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    # logger.info(f"======================")
                    
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
            
            # logger.info(f"=== POSTED MESSAGE ===")
            # logger.info(f"User ID: {user_id}")
            # logger.info(f"Channel ID: {channel_id}")
            # logger.info(f"Post ID: {post_id}")
            # logger.info(f"Message: {message}")
            # logger.info(f"Full post: {json.dumps(post, ensure_ascii=False, indent=2)}")
            # logger.info(f"======================")
            
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
                    # Пользователь авторизован — показываем единое главное меню через Bot.show_main_menu
                    try:
                        import asyncio
                        loop = self._get_bot_loop()
                        if loop is None:
                            logger.error("Bot loop is not set; cannot show main menu")
                            return

                        dm_channel_id = self._ensure_direct_channel(user_id)
                        if not dm_channel_id:
                            return

                        def _schedule_menu():
                            asyncio.create_task(self.bot.show_main_menu(user_id, dm_channel_id))

                        loop.call_soon_threadsafe(_schedule_menu)
                    except Exception as e:
                        logger.error(f"Failed to schedule main menu from WS: {e}", exc_info=True)
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
                    import asyncio
                    # Используем главный event loop, сохранённый в боте
                    loop = self._get_bot_loop()
                    if loop is None:
                        logger.error("Bot loop is not set; cannot schedule dialog handler")
                        return

                    def _schedule_dialog_step():
                        asyncio.create_task(
                            self.bot.handle_dialog_step(user_id, channel_id, user_state, message)
                        )

                    loop.call_soon_threadsafe(_schedule_dialog_step)
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

            headers = self._api_headers()

            # Получить email пользователя из Mattermost через HTTP API
            try:
                user_resp = requests.get(
                    f"{self._base_url}/api/v4/users/{user_id}",
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
            dm_channel_id = self._ensure_direct_channel(user_id)
            if not dm_channel_id:
                return

            post_data = {
                'channel_id': dm_channel_id,
                'message': message_text
            }

            resp = requests.post(
                f"{self._base_url}/api/v4/posts",
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
    
    # _send_menu_reply больше не используется; логика главного меню вынесена в Bot.show_main_menu

    def _api_headers(self):
        return {
            'Authorization': f'Bearer {Config.MATTERMOST_BOT_TOKEN}',
            'Content-Type': 'application/json'
        }

    def _direct_channel_payload(self, user_id: str):
        mm = getattr(self.bot, 'mm', None)
        bot_id = mm.user.get('id') if mm and getattr(mm, 'user', None) else None
        return [bot_id, user_id] if bot_id else [user_id]

    def _ensure_direct_channel(self, user_id: str):
        try:
            response = requests.post(
                f"{self._base_url}/api/v4/channels/direct",
                headers=self._api_headers(),
                json=self._direct_channel_payload(user_id),
                timeout=10,
                verify=False
            )
            if response.status_code in (200, 201):
                channel_id = response.json().get('id')
                if channel_id:
                    return channel_id
            logger.error(
                "Failed to get direct channel: HTTP %s, response: %s",
                response.status_code,
                response.text
            )
        except Exception as e:
            logger.error(f"Error creating direct channel for user {user_id}: {e}")
        return None
