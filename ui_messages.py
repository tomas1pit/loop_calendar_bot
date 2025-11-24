from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
import json


class UserState(Enum):
    """Состояния пользователя"""
    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATED = "authenticated"
    CREATING_MEETING_TITLE = "creating_meeting_title"
    CREATING_MEETING_DATE = "creating_meeting_date"
    CREATING_MEETING_TIME = "creating_meeting_time"
    CREATING_MEETING_DURATION = "creating_meeting_duration"
    CREATING_MEETING_ATTENDEES = "creating_meeting_attendees"
    CREATING_MEETING_DESCRIPTION = "creating_meeting_description"
    CREATING_MEETING_LOCATION = "creating_meeting_location"
    VIEWING_MEETINGS = "viewing_meetings"
    VIEWING_MEETING_DETAILS = "viewing_meeting_details"


class UIMessages:
    """Константы сообщений для UI"""
    
    @staticmethod
    def auth_required(email: str) -> str:
        return f"""Привет! Для начала надо авторизоваться в твоём календаре.

Логин я твой уже знаю: `{email}`

А вот с паролем немного сложнее. Перейди по ссылке:
https://account.mail.ru/user/2-step-auth/passwords/

и создай пароль приложения. Скопируй его и пришли мне в ответ одним сообщением."""
    
    @staticmethod
    def main_menu_message() -> str:
        return """**Главное меню**

Выберите действие:"""
    
    @staticmethod
    def today_all_meetings_template() -> str:
        return """**Все встречи на сегодня**

| Встреча | Время | Статус |
|---------|-------|--------|
"""
    
    @staticmethod
    def today_current_meetings_template() -> str:
        return """**Текущие и будущие встречи на сегодня**

| Встреча | Время | Статус |
|---------|-------|--------|
"""
    
    @staticmethod
    def meeting_details(title: str, start: datetime, end: datetime, 
                       attendees: list, description: str = "", 
                       location: str = "", status: str = "ACCEPTED",
                       organizer_email: str = "") -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        
        # Маппинг статусов на emoji + текст
        status_map = {
            "ACCEPTED": "✅ Принято",
            "DECLINED": "❌ Отклонено",
            "TENTATIVE": "❓ Возможно",
            "NEEDS-ACTION": "⏳ Ожидает действия",
            "CONFIRMED": "✅ Подтверждено",
            "CANCELLED": "🚫 Отменено",
        }
        status_display = status_map.get(status.upper(), status)
        
        message = f"""**Название встречи:** {title}

**Когда:** {from_time} - {to_time}

**Участники:**
"""
        if attendees:
            organizer_lower = organizer_email.lower() if organizer_email else ""
            for attendee in attendees:
                attendee_lower = attendee.lower() if isinstance(attendee, str) else ""
                if organizer_lower and attendee_lower == organizer_lower:
                    message += f"• {attendee} (организатор)\n"
                else:
                    message += f"• {attendee}\n"
        else:
            message += "_Нет участников_\n"
        
        if description:
            # Replace escaped \n with actual newlines
            description = description.replace('\\n', '\n')
            message += f"\n**Описание:**\n{description}"
        
        if location:
            message += f"\n\n**Где:**\n{location}"
        
        message += f"\n\n**Ваш статус:** {status_display}"
        
        return message
    
    @staticmethod
    def create_meeting_step_1() -> str:
        return "Как назвать встречу? Напишите одним сообщением."
    
    @staticmethod
    def create_meeting_step_3(today_date: str) -> str:
        return f"Введи дату встречи в формате DD.MM.YYYY, например {today_date}"
    
    @staticmethod
    def create_meeting_step_5() -> str:
        return "Во сколько начать? Формат HH:MM (24 часа)."
    
    @staticmethod
    def create_meeting_step_7() -> str:
        return "Сколько длится встреча? В минутах. Например: 30 или 60."
    
    @staticmethod
    def create_meeting_step_9() -> str:
        return """Кого пригласить на встречу?
Можно указывать участников в любом формате:
• @username — бот сам найдёт e-mail
• email@example.com — можно несколько через запятую или с новой строки

Пример:
```
@ivanov, @petrova
external@mail.com
```

Если никого не нужно приглашать, нажми кнопку «Никого не приглашать»."""
    
    @staticmethod
    def create_meeting_step_11() -> str:
        return """Добавь описание встречи (повестка и т.п.).
Если не нужно — нажми кнопку «Не добавлять»."""
    
    @staticmethod
    def create_meeting_step_13() -> str:
        return """Добавь место встречи или ссылку на созвон.
Если не нужно — нажми кнопку «Не добавлять»."""
    
    @staticmethod
    def meeting_created(title: str, start: datetime, end: datetime, 
                        attendees: list, description: str = "", 
                        location: str = "") -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        
        attendees_str = ", ".join(attendees) if attendees else "—"
        description_str = description if description else "—"
        location_str = location if location else "—"
        
        return f"""✅ Встреча создана в календаре

**{title}**
Когда: {from_time} - {to_time}
Участники: {attendees_str}
Описание: {description_str}
Где: {location_str}
Напоминание о встрече по умолчанию (за 15 минут установлено)"""
    
    @staticmethod
    def meeting_cancelled(title: str, start: datetime, end: datetime) -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        return f"""❌ Встреча отменена
**{title}**
Когда было запланировано: {from_time} - {to_time}"""
    
    @staticmethod
    def meeting_rescheduled(title: str, old_start: datetime, old_end: datetime,
                           new_start: datetime, new_end: datetime) -> str:
        old_from = old_start.strftime("%d.%m.%Y %H:%M")
        old_to = old_end.strftime("%H:%M")
        new_from = new_start.strftime("%d.%m.%Y %H:%M")
        new_to = new_end.strftime("%H:%M")
        
        return f"""🔁 Встреча перенесена
**{title}**
Было: {old_from} - {old_to}
Стало: {new_from} - {new_to}"""
    
    @staticmethod
    def new_meeting_notification(title: str, start: datetime, end: datetime,
                                attendees: list, description: str = "",
                                location: str = "") -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        
        attendees_str = ", ".join(attendees) if attendees else "—"
        description_str = description if description else "—"
        location_str = location if location else "—"
        
        return f"""🆕 Новая встреча
**{title}**
Когда: {from_time} - {to_time}
Участники: {attendees_str}
Описание: {description_str}
Где: {location_str}"""
    
    @staticmethod
    def reminder_notification(title: str, start: datetime, location: str = "") -> str:
        time_str = start.strftime("%d.%m.%Y %H:%M")
        message = f"""⏰ Напоминание о встрече
**{title}**
Когда: {time_str}"""
        if location:
            message += f"\nГде: {location}"
        return message


class ButtonActions:
    """Константы для кнопок"""
    MAIN_MENU = "main_menu"
    TODAY_ALL_MEETINGS = "today_all_meetings"
    TODAY_CURRENT_MEETINGS = "today_current_meetings"
    CREATE_MEETING = "create_meeting"
    LOGOUT = "logout"
    NO_INVITE = "no_invite"
    NO_DESCRIPTION = "no_description"
    NO_LOCATION = "no_location"
    MEETING_DETAIL = "meeting_detail_"
    SELECT_MEETING = "select_meeting_"
    CANCEL_WIZARD = "cancel_wizard"
    RAW_CALDAV = "raw_caldav"


def create_main_menu_buttons() -> list:
    """Создать кнопки главного меню"""
    return [
        {
            "name": "📅 Все встречи на сегодня",
            "integration": {
                "url": f"action_url",
                "context": {
                    "action": ButtonActions.TODAY_ALL_MEETINGS
                }
            }
        },
        {
            "name": "⏱️ Текущие встречи",
            "integration": {
                "url": f"action_url",
                "context": {
                    "action": ButtonActions.TODAY_CURRENT_MEETINGS
                }
            }
        },
        {
            "name": "➕ Создать встречу",
            "integration": {
                "url": f"action_url",
                "context": {
                    "action": ButtonActions.CREATE_MEETING
                }
            }
        },
        {
            "name": "🚪 Разлогиниться",
            "integration": {
                "url": f"action_url",
                "context": {
                    "action": ButtonActions.LOGOUT
                }
            }
        }
    ]
