# Calendar Bot - Mattermost to CalDAV Bot

Календарный бот для Mattermost, который синхронизирует встречи с Mail.ru CalDAV.

## Возможности

✅ Авторизация по email и паролю приложения Mail.ru CalDAV
✅ Просмотр встреч на сегодня
✅ Просмотр текущих и будущих встреч
✅ Создание новых встреч через пошаговый мастер
✅ Уведомления об отмене и переносе встреч
✅ Напоминания перед встречами
✅ Безопасное хранение паролей (зашифровано)

## Требования

- Python 3.11+
- Docker & Docker Compose
- Mattermost сервер
- Mail.ru календарь с CalDAV поддержкой

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd loop_calendar_bot
```

### 2. Подготовить конфигурацию

```bash
cp .env.example .env
```

Отредактировать `.env` файл с вашими параметрами:
- `MATTERMOST_BOT_TOKEN` - токен бота Mattermost
- `ENCRYPTION_KEY` - ключ шифрования (или сгенерировать новый)

### 3. Запустить бота

```bash
docker-compose up -d
```

## Использование

### Авторизация

1. Напишите @calendar_bot в личном сообщении
2. Бот запросит пароль приложения Mail.ru
3. Перейдите по ссылке и создайте пароль приложения
4. Пришлите пароль боту

### Главное меню

После авторизации бот показывает главное меню с кнопками:

- 📅 **Все встречи на сегодня** - просмотр всех встреч
- ⏱️ **Текущие встречи** - встречи, которые идут сейчас
- ➕ **Создать встречу** - пошаговый мастер
- 🚪 **Разлогиниться** - удалить данные доступа

### Создание встречи

Следуйте пошаговому мастеру:
1. Укажите название встречи
2. Выберите дату (DD.MM.YYYY)
3. Укажите время начала (HH:MM)
4. Укажите продолжительность (минуты)
5. Добавьте участников (@username или email)
6. Добавьте описание встречи
7. Добавьте место встречи или ссылку

## Структура проекта

```
loop_calendar_bot/
├── bot.py                 # Главный класс бота
├── bot_logic.py          # Логика бота
├── config.py             # Конфигурация
├── database.py           # Модели БД
├── mattermost_manager.py # Менеджер Mattermost API
├── caldav_manager.py     # Менеджер CalDAV
├── encryption.py         # Управление шифрованием
├── ui_messages.py        # Сообщения и кнопки UI
├── requirements.txt      # Зависимости Python
├── Dockerfile            # Docker образ
├── docker-compose.yml    # Docker Compose конфиг
└── .env.example          # Пример конфигурации

```

## API Endpoints

Бот слушает Mattermost events и обрабатывает:
- Личные сообщения с упоминанием @calendar_bot
- Интерактивные кнопки (actions)

## Переменные окружения

| Переменная | Описание | По умолчанию |
|----------|---------|--------------|
| MATTERMOST_BASE_URL | URL Mattermost сервера | https://wave.loop.ru |
| MATTERMOST_BOT_TOKEN | Токен бота Mattermost | - |
| MM_ACTIONS_URL | URL для обработки действий | https://cb.wave-solutions.ru |
| CALDAV_BASE_URL | URL CalDAV сервера | https://calendar.mail.ru |
| TZ | Временная зона | Europe/Moscow |
| DB_PATH | Путь к БД SQLite | /data/calendar_bot.db |
| ENCRYPTION_KEY | Ключ шифрования | - |
| CHECK_INTERVAL | Интервал проверки изменений (сек) | 60 |
| REMINDER_MINUTES | За сколько минут напомнить | 15 |

## Генерация ENCRYPTION_KEY

```bash
python3 -c "from encryption import EncryptionManager; print(EncryptionManager.generate_key())"
```

## Лицензия

MIT

## Поддержка

Для вопросов и проблем используйте Issues в репозитории.
