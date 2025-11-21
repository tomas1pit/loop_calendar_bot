from cryptography.fernet import Fernet
from config import Config
import base64
import hashlib


class EncryptionManager:
    def __init__(self):
        # Валидируем и используем ключ из конфига
        try:
            self.cipher = Fernet(Config.ENCRYPTION_KEY.encode())
        except Exception:
            # Если ключ невалиден, генерируем новый
            self.cipher = Fernet(Fernet.generate_key())
    
    def encrypt(self, data: str) -> str:
        """Зашифровать строку"""
        if isinstance(data, str):
            data = data.encode()
        encrypted = self.cipher.encrypt(data)
        return encrypted.decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Расшифровать строку"""
        try:
            if isinstance(encrypted_data, str):
                encrypted_data = encrypted_data.encode()
            decrypted = self.cipher.decrypt(encrypted_data)
            return decrypted.decode()
        except Exception:
            return None
    
    @staticmethod
    def generate_key() -> str:
        """Сгенерировать новый ключ шифрования"""
        return Fernet.generate_key().decode()
