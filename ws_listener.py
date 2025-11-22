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
        self.reconnect_delay = 5
        self.heartbeat_interval = 30
    
    async def connect(self):
        """Подключиться к WebSocket Mattermost с автоматическим переподключением"""
        self.running = True
        message_id = 1
        
        while self.running:
            try:
                # Получить WebSocket URL
                ws_url = Config.MATTERMOST_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
                ws_url += "/api/v4/websocket"
                
                logger.info(f"Connecting to WebSocket: {ws_url}")
                
                self.ws = await connect(ws_url, ping_interval=None, pong_timeout=None)
                
                # Отправить токен аутентификации
                auth_msg = {
                    "seq": message_id,
                    "action": "authentication_challenge",
                    "data": {
                        "token": Config.MATTERMOST_BOT_TOKEN
                    }
                }
                message_id += 1
                await self.ws.send(json.dumps(auth_msg))
                logger.debug(f"Sent auth message")
                
                # Получить ответ на аутентификацию
                response = await asyncio.wait_for(self.ws.recv(), timeout=5)
                auth_response = json.loads(response)
                logger.info(f"Auth response: {auth_response.get('status', 'unknown')}")
                
                if auth_response.get('status') == 'OK':
                    logger.info("WebSocket authenticated successfully")
                else:
                    logger.error(f"Authentication failed: {auth_response}")
                    await asyncio.sleep(self.reconnect_delay)
                    continue
                
                # Запустить задачи слушания и heartbeat
                listen_task = asyncio.create_task(self.listen(message_id))
                heartbeat_task = asyncio.create_task(self.send_heartbeat(message_id))
                
                # Ждём, пока одна из них не завершится
                await asyncio.gather(listen_task, heartbeat_task)
            
            except exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}. Reconnecting in {self.reconnect_delay} seconds...")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
            
            except asyncio.TimeoutError:
                logger.error("Authentication timeout")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
            
            except asyncio.CancelledError:
                logger.info("WebSocket connection cancelled")
                self.running = False
                break
            
            except Exception as e:
                logger.error(f"Error in WebSocket connection: {e}")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
    
    async def send_heartbeat(self, initial_message_id):
        """Отправлять периодические heartbeat сообщения для поддержки соединения"""
        message_id = initial_message_id
        
        while self.running and self.ws:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.running and self.ws:
                    # Отправить user_typing как heartbeat для поддержки соединения
                    heartbeat_msg = {
                        "seq": message_id,
                        "action": "user_typing",
                        "data": {}
                    }
                    message_id += 1
                    await self.ws.send(json.dumps(heartbeat_msg))
                    logger.debug("Heartbeat sent")
            except Exception as e:
                logger.debug(f"Error sending heartbeat: {e}")
                break
    
    async def listen(self, initial_message_id):
        """Слушать события от WebSocket"""
        message_id = initial_message_id
        
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
