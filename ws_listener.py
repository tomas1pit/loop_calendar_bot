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
                    logger.info(f"Auth response: {auth_response.get('status', 'unknown')}")
                    
                    if auth_response.get('status') == 'OK':
                        logger.info("WebSocket authenticated successfully")
                        # Запустить цикл слушания
                        self._listen()
                    else:
                        logger.error(f"Authentication failed: {auth_response}")
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
                    self.ws.settimeout(10)
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
    
    async def listen(self):
        """Слушать события от WebSocket"""
        try:
            while self.running and self.ws:
                try:
                    message = await self.ws.recv()
                    
                    if not message:
                        continue
                    
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        logger.debug(f"Invalid JSON received: {message}")
                        continue
                    
                    event_type = data.get('event')
                    
                    if event_type == "posted":
                        await self.handle_posted(data)
                    elif event_type == "status_change":
                        await self.handle_status_change(data)
                
                except exceptions.ConnectionClosed:
                    logger.info("WebSocket connection closed by server")
                    break
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Error in WebSocket listen: {e}")
        
        finally:
            self.ws = None
    
    async def handle_posted(self, data: dict):
        """Обработать событие posted (новое сообщение)"""
        try:
            broadcast = data.get('broadcast', {})
            post = json.loads(broadcast.get('post', '{}')) if isinstance(broadcast.get('post'), str) else broadcast.get('post', {})
            
            if not post:
                return
            
            message = post.get('message', '')
            user_id = post.get('user_id', '')
            channel_id = post.get('channel_id', '')
            
            # Проверить, упоминается ли бот
            if f"@{Config.BOT_NAME}" in message:
                logger.info(f"Bot mentioned by {user_id} in channel {channel_id}")
                
                # Обработать сообщение
                await self.bot.handle_message(user_id, message, channel_id)
        
        except Exception as e:
            logger.error(f"Error handling posted event: {e}")
    
    async def handle_status_change(self, data: dict):
        """Обработать изменение статуса"""
        try:
            broadcast = data.get('broadcast', {})
            # TODO: Обработать изменения статусов встреч
            pass
        
        except Exception as e:
            logger.error(f"Error handling status change: {e}")
    
    async def disconnect(self):
        """Отключиться от WebSocket"""
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        logger.info("WebSocket disconnected")
