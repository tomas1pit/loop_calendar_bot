from mattermostdriver import Driver
from typing import List, Dict, Optional, Tuple
import json
import re


class MattermostManager:
    def __init__(self, base_url: str, token: str, bot_name: str):
        # Remove trailing slash if present
        base_url = base_url.rstrip('/')
        
        self.driver = Driver({
            'url': base_url,
            'token': token,
            'basePath': '/api/v4',
            'verify': True
        })
        self.bot_name = bot_name
        self.user = None
    
    def connect(self) -> bool:
        """Подключиться к Mattermost"""
        try:
            self.user = self.driver.users.get_user('me')
            return True
        except Exception as e:
            print(f"Error connecting to Mattermost: {e}")
            return False
    
    def disconnect(self):
        """Отключиться от Mattermost"""
        if self.driver:
            self.driver.disconnect()
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Получить информацию о пользователе по username"""
        try:
            return self.driver.users.get_user_by_username(username)
        except:
            return None
    
    def get_direct_channel(self, user_id: str) -> str:
        """Получить ID прямого канала с пользователем"""
        try:
            channel = self.driver.channels.create_direct_message_channel([user_id])
            return channel['id']
        except:
            return None
    
    def send_message(self, channel_id: str, message: str, props: Dict = None) -> str:
        """Отправить сообщение в канал"""
        try:
            post_data = {
                'channel_id': channel_id,
                'message': message
            }
            if props:
                post_data['props'] = props
            
            response = self.driver.posts.create_post(post_data)
            return response['id']
        except Exception as e:
            print(f"Error sending message: {e}")
            return None
    
    def update_message(self, post_id: str, message: str, props: Dict = None) -> bool:
        """Обновить сообщение"""
        try:
            update_data = {
                'id': post_id,
                'message': message
            }
            if props:
                update_data['props'] = props
            
            self.driver.posts.update_post(post_data=update_data)
            return True
        except Exception as e:
            print(f"Error updating message: {e}")
            return False
    
    def create_post_with_attachments(self, channel_id: str, message: str, 
                                     attachments: List[Dict]) -> str:
        """Отправить сообщение с интерактивными элементами"""
        props = {
            'attachments': attachments
        }
        return self.send_message(channel_id, message, props)
    
    def get_channel_id(self, user_id: str) -> str:
        """Получить канал для личного сообщения"""
        try:
            # Получаем список каналов пользователя
            channels = self.driver.channels.get_channels_for_user(user_id)
            
            # Ищем прямой канал
            for channel in channels:
                if channel['type'] == 'D':  # Direct message
                    return channel['id']
            
            # Если не найдено, создаем новый
            return self.get_direct_channel(user_id)
        except:
            return None
