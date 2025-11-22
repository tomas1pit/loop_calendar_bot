import threading
import json
import logging
import time
from websocket import create_connection, WebSocketConnectionClosedException
from config import Config

logger = logging.getLogger(__name__)


class MattermostWebSocketListener:
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.running = False
        self.thread = None
        self.reconnect_delay = 5
        self.seq = 1
    
    def connect(self):
        """Подключиться к WebSocket Mattermost (синхронно в отдельном потоке)"""
        self.thread = threading.Thread(target=self._connect_loop, daemon=True)
        self.thread.start()
    
    def _connect_loop(self):
        """Основной цикл подключения с переподключением"""
        self.running = True
        
        while self.running:
            try:
                # Получить WebSocket URL
                ws_url = Config.MATTERMOST_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
                ws_url += "/api/v4/websocket"
                
                logger.info(f"Connecting to WebSocket: {ws_url}")
                
                self.ws = create_connection(ws_url)
                self.ws.settimeout(10)
                
                logger.info("WebSocket connection established")
                
                # Сначала получить приветствие (hello) от сервера
                hello_response = self.ws.recv()
                if hello_response:
                    hello_data = json.loads(hello_response)
                    logger.debug(f"Received hello: {hello_data.get('event', 'unknown')}")
                
                # Отправить токен аутентификации
                auth_msg = {
                    "seq": self.seq,
                    "action": "authentication_challenge",
                    "data": {
                        "token": Config.MATTERMOST_BOT_TOKEN
                    }
                }
                self.seq += 1
                
                self.ws.send(json.dumps(auth_msg))
                logger.debug("Sent auth message")
                
                # Получить ответ на аутентификацию
                response = self.ws.recv()
                if response:
                    auth_response = json.loads(response)
                    logger.debug(f"Auth response: {auth_response}")
                    
                    # Проверяем статус аутентификации - может быть в разных полях
                    status = auth_response.get('status') or (auth_response.get('data', {}).get('status') if isinstance(auth_response.get('data'), dict) else None)
                    
                    if status == 'OK' or auth_response.get('event') == 'authenticated':
                        logger.info("WebSocket authenticated successfully")
                        # Запустить цикл слушания
                        self._listen()
                    else:
                        logger.error(f"Authentication failed: {auth_response}")
                        if self.ws:
                            self.ws.close()
                        time.sleep(self.reconnect_delay)
            
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
                    # Получить сообщение с timeout
                    message = self.ws.recv()
                    
                    if not message:
                        continue
                    
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        logger.debug(f"Invalid JSON received: {message}")
                        continue
                    
                    event_type = data.get('event')
                    
                    if event_type == "posted":
                        self.handle_posted(data)
                    elif event_type == "status_change":
                        self.handle_status_change(data)
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Error in WebSocket listen: {e}")
        
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
            broadcast = data.get('broadcast', {})
            post = json.loads(broadcast.get('post', '{}')) if isinstance(broadcast.get('post'), str) else broadcast.get('post', {})
            
            if not post:
                return
            
            message = post.get('message', '')
            user_id = post.get('user_id', '')
            channel_id = post.get('channel_id', '')
            
            logger.debug(f"Posted event: user={user_id}, channel={channel_id}, message={message[:50]}")
            
            # Проверить, упоминается ли бот
            if f"@{Config.BOT_NAME}" in message:
                logger.info(f"Bot mentioned by {user_id} in channel {channel_id}")
        
        except Exception as e:
            logger.error(f"Error handling posted event: {e}")
    
    def handle_status_change(self, data: dict):
        """Обработать изменение статуса"""
        try:
            broadcast = data.get('broadcast', {})
            logger.debug(f"Status change event: {broadcast}")
        
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
