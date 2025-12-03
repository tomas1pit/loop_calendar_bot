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
    def _normalize_multiline(text: str) -> str:
        if not text:
            return text
        cleaned = text.replace("\\r", "")
        cleaned = cleaned.replace("\\n", "\n")
        cleaned = cleaned.replace("\\t", "\t")
        return cleaned
    
    @staticmethod
    def auth_required(email: str) -> str:
        email_text = email or "неизвестен"
        return (
            "**⚙️ Настроим доступ к календарю**\n\n"
            f"• **Логин:** `{email_text}`\n"
            "• **Пароль:** нужен пароль приложения Mail.ru\n\n"
            "1. Открой <https://account.mail.ru/user/2-step-auth/passwords/>.\n"
            "2. Создай новый пароль приложения (например, «CalDAV»).\n"
            "3. Скопируй пароль и пришли мне одним сообщением."
        )
    
    @staticmethod
    def main_menu_message() -> str:
        return (
            "**🏁 Главное меню**\n\n"
            "Выберите действие с помощью кнопок ниже:"
        )
    
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
        return (
            "**Шаг 1 / 7 · Название**\n\n"
            "Напиши короткое и понятное название одним сообщением.\n"
            "_Пример:_ `Демо релиза 2.5`"
        )
    
    @staticmethod
    def create_meeting_step_3(today_date: str) -> str:
        return (
            "**Шаг 2 / 7 · Дата**\n\n"
            f"Введи дату в формате `DD.MM.YYYY`.\n_Пример:_ `{today_date}`"
        )
    
    @staticmethod
    def create_meeting_step_5() -> str:
        return (
            "**Шаг 3 / 7 · Время начала**\n\n"
            "Во сколько стартуем? Укажи время в формате `HH:MM` (24 часа)."
        )
    
    @staticmethod
    def create_meeting_step_7() -> str:
        return (
            "**Шаг 4 / 7 · Длительность**\n\n"
            "Сколько минут займёт встреча? Напиши число от 1 до 1440."
        )
    
    @staticmethod
    def create_meeting_step_9() -> str:
        return """**Шаг 5 / 7 · Участники**

Кого пригласить?
• `@username` — найду e-mail сам
• `email@example.com` — можно несколько через запятую или построчно

Пример:
```
@ivanov, @petrova
external@mail.com
```

Если никого не нужно приглашать, нажми кнопку «Никого не приглашать»."""
    
    @staticmethod
    def create_meeting_step_11() -> str:
        return (
            "**Шаг 6 / 7 · Описание**\n\n"
            "Коротко опиши повестку или оставь заметки.\n"
            "Если текст не нужен — нажми «Не добавлять»."
        )
    
    @staticmethod
    def create_meeting_step_13() -> str:
        return (
            "**Шаг 7 / 7 · Локация**\n\n"
            "Добавь переговорку, адрес или ссылку на звонок.\n"
            "Если место не важно — нажми «Не добавлять»."
        )
    
    @staticmethod
    def meeting_created(title: str, start: datetime, end: datetime, 
                        attendees: list, description: str = "", 
                        location: str = "") -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        
        attendees_str = ", ".join(attendees) if attendees else "—"
        description_str = UIMessages._normalize_multiline(description) if description else "—"
        location_str = location if location else "—"
        
        return (
            "✅ **Встреча создана**\n\n"
            f"**{title}**\n"
            f"• **Когда:** {from_time} – {to_time}\n"
            f"• **Участники:** {attendees_str}\n"
            f"• **Описание:** {description_str}\n"
            f"• **Где:** {location_str}\n\n"
            "Напоминание по умолчанию настроено за 15 минут."
        )
    
    @staticmethod
    def meeting_cancelled(title: str, start: datetime, end: datetime) -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        return (
            "❌ **Встреча отменена**\n\n"
            f"**{title}**\n"
            f"Первоначально: {from_time} – {to_time}"
        )
    
    @staticmethod
    def meeting_rescheduled(title: str, old_start: datetime, old_end: datetime,
                           new_start: datetime, new_end: datetime) -> str:
        old_from = old_start.strftime("%d.%m.%Y %H:%M")
        old_to = old_end.strftime("%H:%M")
        new_from = new_start.strftime("%d.%m.%Y %H:%M")
        new_to = new_end.strftime("%H:%M")
        
        return (
            "🔁 **Встречу перенесли**\n\n"
            f"**{title}**\n"
            f"• **Было:** {old_from} – {old_to}\n"
            f"• **Стало:** {new_from} – {new_to}"
        )
    
    @staticmethod
    def new_meeting_notification(title: str, start: datetime, end: datetime,
                                attendees: list, description: str = "",
                                location: str = "") -> str:
        from_time = start.strftime("%d.%m.%Y %H:%M")
        to_time = end.strftime("%H:%M")
        
        attendees_str = ", ".join(attendees) if attendees else "—"
        description_str = UIMessages._normalize_multiline(description) if description else "—"
        location_str = location if location else "—"
        
        return (
            "🆕 **Новая встреча**\n\n"
            f"**{title}**\n"
            f"• **Когда:** {from_time} – {to_time}\n"
            f"• **Участники:** {attendees_str}\n"
            f"• **Описание:** {description_str}\n"
            f"• **Где:** {location_str}"
        )
    
    @staticmethod
    def reminder_notification(title: str, start: datetime, location: str = "") -> str:
        time_str = start.strftime("%d.%m.%Y %H:%M")
        message = (
            "⏰ **Напоминание о встрече**\n\n"
            f"**{title}**\n"
            f"Начало: {time_str}"
        )
        if location:
            message += f"\nГде: {location}"
        return message

    @staticmethod
    def meeting_start_notification(title: str, start: datetime, location: str = "") -> str:
        time_str = start.strftime("%d.%m.%Y %H:%M")
        message = (
            "🚀 **Встреча начинается прямо сейчас**\n\n"
            f"**{title}**\n"
            f"Старт: {time_str}"
        )
        if location:
            message += f"\nГде: {location}"
        return message

    @staticmethod
    def daily_digest(now: datetime, table: str) -> str:
        date_str = now.strftime("%d.%m.%Y")
        return (
            f"**🗓️ Дайджест встреч на сегодня ({date_str})**\n\n"
            f"{table}"
        )


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
