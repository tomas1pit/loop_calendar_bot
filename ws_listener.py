import threading
import json
import logging
import time
import asyncio
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
            
            if f"@{bot_name}" in message_lower or bot_name in message_lower:
                logger.info(f"✓ Bot @{bot_name} mentioned in message!")
                # Отправить меню в ответ
                self._send_menu_reply(user_id, channel_id, post_id)
            else:
                logger.info(f"✗ Bot @{bot_name} NOT mentioned (message: {message[:100]})")
        
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
    
    def _send_menu_reply(self, user_id: str, channel_id: str, root_id: str):
        """Отправить главное меню в ответ на упоминание"""
        try:
            logger.info(f"Sending menu reply to user {user_id} in channel {channel_id}")
            
            # Простое меню в виде текста
            menu_text = """**Календарь Бот Главное Меню**

Выберите действие:
1️⃣ Показать встречи на сегодня
2️⃣ Создать встречу
3️⃣ Настройки"""
            
            # Используем HTTP API для отправки сообщения
            # Вызываем метод бота через asyncio
            if self.bot:
                logger.info("Calling bot.mm.send_message...")
                # Запускаем асинхронный вызов в отдельном потоке
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self.bot.mm.send_message(channel_id, menu_text, root_id=root_id)
                    )
                    logger.info("Menu sent successfully")
                except Exception as e:
                    logger.error(f"Failed to send menu: {e}", exc_info=True)
                finally:
                    loop.close()
            else:
                logger.warning("Bot reference is None, cannot send menu")
        
        except Exception as e:
            logger.error(f"Error in _send_menu_reply: {e}", exc_info=True)
