import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Mattermost
    MATTERMOST_BASE_URL = os.getenv("MATTERMOST_BASE_URL", "https://wave.loop.ru")
    MATTERMOST_BOT_TOKEN = os.getenv("MATTERMOST_BOT_TOKEN", "")
    MM_ACTIONS_URL = os.getenv("MM_ACTIONS_URL", "https://cb.wave-solutions.ru")
    
    # CalDAV
    CALDAV_BASE_URL = os.getenv("CALDAV_BASE_URL", "https://calendar.mail.ru")
    CALDAV_PRINCIPAL_PATH = "/principals/"
    
    # Database
    DB_PATH = os.getenv("DB_PATH", "/data/calendar_bot.db")
    
    # Encryption
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "DKlIT2WC3n9ke/oq8E3pAkQUQ4ITZ1J+uK4lix++ZPU=")
    
    # Timezone
    TZ = os.getenv("TZ", "Europe/Moscow")
    
    # Bot behavior
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # seconds
    REMINDER_MINUTES = int(os.getenv("REMINDER_MINUTES", "15"))  # minutes

    # Debug flags
    CALDAV_LOG_FULL_RAW = os.getenv("CALDAV_LOG_FULL_RAW", "1") == "1"  # Включить полный вывод REPORT XML
    CALDAV_LOG_PARSE_ERRORS = os.getenv("CALDAV_LOG_PARSE_ERRORS", "1") == "1"  # Логировать ошибки парсинга VEVENT
    
    # Bot name
    BOT_NAME = "calendar_bot"
