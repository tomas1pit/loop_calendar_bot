import aiohttp
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


class MattermostManager:
    def __init__(self, base_url: str, token: str, bot_name: str):
        """Инициализация менеджера Mattermost через HTTP API"""
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.bot_name = bot_name
        self.user = None
        self.session = None
        # Для совместимости со старым кодом
        self.driver = self
    
    async def _ensure_session(self):
        """Создать session если необходимо"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _get_headers(self) -> Dict:
        """Получить заголовки для API запроса"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    async def connect(self) -> bool:
        """Проверить подключение к Mattermost"""
        try:
            session = await self._ensure_session()
            async with session.get(
                f"{self.base_url}/api/v4/users/me",
                headers=self._get_headers(),
                ssl=False
            ) as resp:
                if resp.status == 200:
                    self.user = await resp.json()
                    logger.info(f"Connected to Mattermost as {self.user.get('username')}")
                    return True
                else:
                    logger.error(f"Failed to connect: HTTP {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Error connecting to Mattermost: {e}")
            return False
    
    async def disconnect(self):
        """Отключиться от Mattermost"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    # Wrapper для совместимости
    class UsersAPI:
        def __init__(self, manager):
            self.manager = manager
        
        def get_user(self, user_id: str) -> Dict:
            """Синхронный wrapper для получения пользователя"""
            # Возвращаем текущего пользователя если это 'me'
            if user_id == 'me' and self.manager.user:
                return self.manager.user
            return {}
    
    @property
    def users(self):
        """Для совместимости с драйвером"""
        return self.UsersAPI(self)
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Получить информацию о пользователе по username"""
        try:
            session = await self._ensure_session()
            async with session.get(
                f"{self.base_url}/api/v4/users/username/{username}",
                headers=self._get_headers(),
                ssl=False
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"Error getting user {username}: {e}")
            return None
    
    async def get_direct_channel(self, user_id: str) -> Optional[str]:
        """Получить ID прямого канала с пользователем"""
        try:
            session = await self._ensure_session()
            # Создать или получить прямой канал
            async with session.post(
                f"{self.base_url}/api/v4/channels/direct",
                headers=self._get_headers(),
                json=[user_id],
                ssl=False
            ) as resp:
                if resp.status == 201:
                    channel = await resp.json()
                    return channel.get('id')
                return None
        except Exception as e:
            logger.error(f"Error creating direct channel: {e}")
            return None
    
    async def send_message(self, channel_id: str, message: str, props: Dict = None, root_id: str = None) -> Optional[str]:
        """Отправить сообщение в канал"""
        try:
            session = await self._ensure_session()
            post_data = {
                'channel_id': channel_id,
                'message': message
            }
            if props:
                post_data['props'] = props
            if root_id:
                post_data['root_id'] = root_id
            
            async with session.post(
                f"{self.base_url}/api/v4/posts",
                headers=self._get_headers(),
                json=post_data,
                ssl=False
            ) as resp:
                if resp.status == 201:
                    response = await resp.json()
                    return response.get('id')
                return None
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    async def update_message(self, post_id: str, message: str, props: Dict = None) -> bool:
        """Обновить сообщение"""
        try:
            session = await self._ensure_session()
            update_data = {
                'id': post_id,
                'message': message
            }
            if props:
                update_data['props'] = props
            
            async with session.put(
                f"{self.base_url}/api/v4/posts/{post_id}",
                headers=self._get_headers(),
                json=update_data,
                ssl=False
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            return False
    
    async def create_post_with_attachments(self, channel_id: str, message: str, 
                                          attachments: List[Dict]) -> Optional[str]:
        """Отправить сообщение с интерактивными элементами"""
        props = {'attachments': attachments}
        return await self.send_message(channel_id, message, props)
    
    async def get_channel_id(self, user_id: str) -> Optional[str]:
        """Получить канал для личного сообщения"""
        try:
            session = await self._ensure_session()
            # Получить список каналов пользователя
            async with session.get(
                f"{self.base_url}/api/v4/users/me/channels",
                headers=self._get_headers(),
                ssl=False
            ) as resp:
                if resp.status == 200:
                    channels = await resp.json()
                    # Ищем прямой канал с этим пользователем
                    for channel in channels:
                        if channel['type'] == 'D' and user_id in channel.get('name', ''):
                            return channel['id']
            
            # Если не найдено, создаем новый
            return await self.get_direct_channel(user_id)
        except Exception as e:
            logger.error(f"Error getting channel: {e}")
            return None
    
    async def update_post(self, post_id: str, message: str, props: Dict = None) -> Optional[Dict]:
        """Обновить пост (для очистки кнопок)"""
        try:
            session = await self._ensure_session()
            update_data = {
                'id': post_id,
                'message': message
            }
            if props is not None:
                update_data['props'] = props
            else:
                # Очищаем props (кнопки)
                update_data['props'] = {}
            
            async with session.put(
                f"{self.base_url}/api/v4/posts/{post_id}",
                headers=self._get_headers(),
                json=update_data,
                ssl=False
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"Error updating post: {e}")
            return None
