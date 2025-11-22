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
                    
                    if event_type == "posted":
                        logger.debug(f"Posted event received")
                        self.handle_posted(data)
                    elif event_type == "status_change":
                        logger.debug(f"Status change event received")
                        self.handle_status_change(data)
                    else:
                        # Игнорируем другие события (hello, auth_ok, и т.д.)
                        logger.debug(f"Received event: {event_type}")
                
                except WebSocketConnectionClosedException:
                    logger.info("WebSocket connection closed during listen")
                    break
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
            post = broadcast.get('post')
            
            # post может быть JSON строкой или объектом
            if isinstance(post, str):
                post = json.loads(post)
            
            if not post:
                return
            
            message = post.get('message', '')
            user_id = post.get('user_id', '')
            channel_id = post.get('channel_id', '')
            
            logger.debug(f"Posted: user={user_id}, channel={channel_id}, message={message[:50] if message else 'empty'}")
            
            # TODO: Обработать сообщение от бота (если нужно)
        
        except Exception as e:
            logger.error(f"Error handling posted event: {e}")
    
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
