import asyncio
import json
import logging
from websockets import connect, exceptions
from config import Config

logger = logging.getLogger(__name__)


class MattermostWebSocketListener:
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.running = False
    
    async def connect(self):
        """Подключиться к WebSocket Mattermost с автоматическим переподключением"""
        while self.running or not hasattr(self, '_connect_called'):
            self._connect_called = True
            try:
                # Получить WebSocket URL
                ws_url = Config.MATTERMOST_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
                ws_url += "/api/v4/websocket"
                
                logger.info(f"Connecting to WebSocket: {ws_url}")
                
                async with connect(ws_url, ping_interval=30) as ws:
                    self.ws = ws
                    
                    # Отправить токен аутентификации
                    auth_msg = {
                        "action": "authentication_challenge",
                        "data": {
                            "token": Config.MATTERMOST_BOT_TOKEN
                        }
                    }
                    await self.ws.send(json.dumps(auth_msg))
                    
                    logger.info("WebSocket connected and authenticated")
                    self.running = True
                    
                    # Запустить цикл прослушивания
                    await self.listen()
            
            except (exceptions.ConnectionClosed, ConnectionResetError) as e:
                logger.warning(f"WebSocket connection lost: {e}. Reconnecting in 5 seconds...")
                self.running = False
                await asyncio.sleep(5)
            
            except Exception as e:
                logger.error(f"Error connecting to WebSocket: {e}")
                self.running = False
                await asyncio.sleep(5)
    
    async def listen(self):
        """Слушать события от WebSocket"""
        try:
            while self.running and self.ws:
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=60)
                    data = json.loads(message)
                    
                    event_type = data.get('event')
                    
                    if event_type == "posted":
                        await self.handle_posted(data)
                    elif event_type == "status_change":
                        await self.handle_status_change(data)
                
                except asyncio.TimeoutError:
                    logger.debug("WebSocket timeout, sending ping...")
                    continue
        
        except Exception as e:
            logger.error(f"Error in WebSocket listen: {e}")
        
        finally:
            self.running = False
    
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
