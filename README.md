# Calendar Bot - Mattermost to CalDAV Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)](https://www.docker.com/)

Надежный, простой и минималистичный Mattermost-бот для управления встречами через Mail.ru CalDAV. Бот работает только в личных сообщениях и предоставляет полный набор инструментов для синхронизации календарей.

## 🎯 Возможности

- ✅ **Авторизация** - Email + пароль приложения Mail.ru CalDAV
- ✅ **Просмотр встреч** - Все встречи на сегодня и текущие встречи
- ✅ **Создание встреч** - Пошаговый мастер с валидацией
- ✅ **Уведомления** - об отмене, переносе и новых встречах  
- ✅ **Напоминания** - перед встречами (по умолчанию за 15 минут)
- ✅ **Безопасность** - Зашифрованное хранение паролей (Fernet)
- ✅ **Хранение данных** - Персистентное хранение через SQLite

## 📋 Требования

- Python 3.11+
- Docker & Docker Compose
- Mattermost сервер (v5.0+)
- Доступ к Mail.ru календарю (CalDAV)

## 🚀 Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/yourusername/calendar_bot.git
cd calendar_bot
```

### 2. Создать конфигурацию

```bash
cp .env.example .env
```

Отредактировать `.env` файл:

```env
MATTERMOST_BASE_URL=https://your-mattermost.com
MATTERMOST_BOT_TOKEN=your_bot_token_here
MM_ACTIONS_URL=https://your-actions-url.com
CALDAV_BASE_URL=https://calendar.mail.ru
ENCRYPTION_KEY=your_encryption_key_here
TZ=Europe/Moscow
```

### 3. Запустить бота

```bash
# С Docker Compose
docker-compose up -d

# Или вручную (требует Python 3.11+)
pip install -r requirements.txt
python bot.py
```

## 📖 Использование

### Авторизация

1. Напишите `@calendar_bot` в личном сообщении Mattermost
2. Бот отправит инструкцию с ссылкой на Mail.ru
3. Создайте пароль приложения на https://account.mail.ru/user/2-step-auth/passwords/
4. Отправьте пароль боту

### Главное меню

После авторизации доступны кнопки:

- 📅 **Все встречи на сегодня** - полный список встреч дня
- ⏱️ **Текущие встречи** - встречи, которые идят сейчас и будущие до конца дня
- ➕ **Создать встречу** - пошаговый мастер создания
- 🚪 **Разлогиниться** - удалить все данные доступа

### Создание встречи

Следуйте пошаговому процессу:

1. **Название** - укажите название встречи
2. **Дата** - выберите дату (формат: DD.MM.YYYY)
3. **Время** - укажите время начала (формат: HH:MM, 24-часовой)
4. **Продолжительность** - минуты встречи
5. **Участники** - используйте @username или email@example.com
6. **Описание** - опциональная повестка встречи
7. **Место** - опциональная ссылка на созвон или локация

## 🏗️ Структура проекта

```
calendar_bot/
├── bot.py                      # Главный класс бота
├── bot_logic.py                # Бизнес-логика бота
├── config.py                   # Конфигурация (переменные окружения)
├── database.py                 # Модели БД (SQLAlchemy)
├── encryption.py               # Управление шифрованием (Fernet)
├── mattermost_manager.py       # API клиент Mattermost
├── caldav_manager.py           # Менеджер CalDAV (Mail.ru)
├── notification_manager.py     # Система уведомлений и проверки изменений
├── ui_messages.py              # Сообщения и кнопки UI
├── web_handler.py              # HTTP обработчик действий
├── ws_listener.py              # WebSocket слушатель Mattermost
├── requirements.txt            # Зависимости Python
├── Dockerfile                  # Docker образ
├── docker-compose.yml          # Docker Compose конфигурация
├── generate_key.py             # Генератор ключей шифрования
├── init_db.py                  # Инициализатор БД
├── .env.example                # Шаблон конфигурации
├── .gitignore                  # Git исключения
└── README.md                   # Этот файл
```

## ⚙️ Переменные окружения

| Переменная | Описание | Обязательная | По умолчанию |
|----------|---------|:-----------:|:----------:|
| `MATTERMOST_BASE_URL` | URL Mattermost сервера | ✅ | - |
| `MATTERMOST_BOT_TOKEN` | Токен бота Mattermost | ✅ | - |
| `MM_ACTIONS_URL` | URL для обработки действий | ✅ | - |
| `CALDAV_BASE_URL` | URL CalDAV сервера | ❌ | `https://calendar.mail.ru` |
| `ENCRYPTION_KEY` | Base64 ключ шифрования Fernet | ✅ | - |
| `TZ` | Временная зона | ❌ | `Europe/Moscow` |
| `DB_PATH` | Путь к БД SQLite | ❌ | `/data/calendar_bot.db` |
| `CHECK_INTERVAL` | Интервал проверки (сек) | ❌ | `60` |
| `REMINDER_MINUTES` | Минут напоминание | ❌ | `15` |

## 🔐 Генерация ENCRYPTION_KEY

```bash
python generate_key.py
```

Или:

```bash
python -c "from encryption import EncryptionManager; print(EncryptionManager.generate_key())"
```

## 🐳 Docker развертывание

### С Docker Compose

```bash
# Создать образ и запустить контейнер
docker-compose up -d

# Просмотр логов
docker-compose logs -f loop-calendar-bot

# Остановить бота
docker-compose down
```

### С Portainer Stacks

1. Откройте Portainer
2. Перейдите в Stacks
3. Create Stack
4. Загрузите содержимое `docker-compose.yml`
5. Установите переменные окружения в разделе Environment
6. Deploy

## 📊 API Endpoints

Бот обрабатывает:

- **WebSocket события** от Mattermost
- **HTTP POST /actions** - обработка интерактивных кнопок

## 📁 Модели данных

### User
```python
- mattermost_id: str (primary key)
- email: str (unique)
- encrypted_password: str
- created_at: datetime
- updated_at: datetime
```

### UserState
```python
- mattermost_id: str (primary key)
- state: str (диалоговое состояние)
- data: JSON (данные диалога)
- message_id: str (ID сообщения для обновления)
```

### MeetingCache
```python
- id: int (primary key)
- user_id: str
- uid: str (уникальный ID события)
- title: str
- start_time: datetime
- end_time: datetime
- status: str (CONFIRMED, CANCELLED, TENTATIVE)
- hash_value: str (для отслеживания изменений)
```

## 🛡️ Безопасность

- **Шифрование паролей** - Fernet (симметричное шифрование)
- **Никогда не логируем пароли** - Логирование только действий
- **Переменные окружения** - Все конфиденциальные данные через .env
- **HTTPS** - Рекомендуется использовать для production

## 🐛 Решение проблем

### Бот не получает сообщения
- Проверьте токен бота в Mattermost
- Убедитесь, что бот добавлен в ваш DirectMessage канал
- Проверьте логи: `docker-compose logs loop-calendar-bot`

### Ошибка авторизации CalDAV
- Проверьте email и пароль приложения
- Пароль должен быть создан на https://account.mail.ru/user/2-step-auth/passwords/
- Проверьте доступность https://calendar.mail.ru

### БД ошибки
- Проверьте права доступа на директорию `/data`
- Выполните инициализацию БД: `python init_db.py`

## 📝 Логирование

Логи отправляются в stdout. Для production рекомендуется:

```bash
# Сохранение логов
docker-compose logs loop-calendar-bot > bot.log
```

## 🔄 Жизненный цикл бота

1. **Инициализация** - Подключение к Mattermost и инициализация БД
2. **WebSocket слушатель** - Ожидание входящих сообщений
3. **HTTP сервер** - Прием действий от кнопок (порт 8080)
4. **Проверка уведомлений** - Каждые 60 секунд (по умолчанию)
5. **Отправка напоминаний** - 15 минут до встречи (по умолчанию)

## 🤝 Контрибьютинг

Приветствуем pull requests! Для больших изменений сначала откройте issue.

## 📄 Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE) для деталей.

## 📞 Поддержка

Для вопросов и проблем используйте [Issues](../../issues) в репозитории.
