# Contribution Guide

Спасибо за интерес к разработке Calendar Bot! Мы приветствуем вклады от сообщества.

## Как внести свой вклад

### Сообщение об ошибках

1. Проверьте [Issues](../../issues) - возможно, баг уже зафиксирован
2. Если нет, создайте новый issue с:
   - Описанием проблемы
   - Шагами для воспроизведения
   - Версией Python и Docker
   - Логами ошибки

### Предложение функций

1. Откройте [Issue](../../issues) с меткой `enhancement`
2. Описите идею и использование
3. Ждите обсуждения и одобрения

### Pull Requests

1. **Fork** репозиторий
2. **Clone** ваш fork: `git clone https://github.com/YOUR_USERNAME/calendar_bot.git`
3. **Create** ветку: `git checkout -b feature/your-feature`
4. **Commit** изменения: `git commit -am 'Add your feature'`
5. **Push**: `git push origin feature/your-feature`
6. **Open** Pull Request с описанием

## Требования к коду

### Python Style Guide

Следуем [PEP 8](https://www.python.org/dev/peps/pep-0008/):

```bash
# Форматирование (если используете)
black *.py

# Проверка
pylint *.py
```

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat` - новая функция
- `fix` - исправление бага
- `docs` - документация
- `style` - форматирование кода
- `refactor` - переструктуризация
- `test` - тесты
- `chore` - сборка, зависимости

**Примеры:**
```
feat: добавить экспорт встреч в CSV

fix: исправить обработку ошибок авторизации CalDAV

docs: обновить README с примерами Portainer
```

## Структура проекта

```
calendar_bot/
├── bot.py                    # Главный класс
├── bot_logic.py              # Бизнес-логика
├── caldav_manager.py         # CalDAV интеграция
├── mattermost_manager.py     # Mattermost интеграция
├── notification_manager.py   # Система уведомлений
├── web_handler.py            # HTTP endpoints
├── ws_listener.py            # WebSocket слушатель
├── database.py               # БД модели
├── encryption.py             # Шифрование
├── ui_messages.py            # UI константы
└── config.py                 # Конфигурация
```

## Тестирование

```bash
# Локально
python -m pytest tests/

# С Docker
docker-compose up -d
docker-compose exec loop-calendar-bot pytest tests/
```

## Документация

- Обновляйте README при добавлении новых функций
- Добавляйте docstrings в функции
- Используйте type hints

Пример:

```python
def get_user(self, user_id: str) -> Optional[User]:
    """Получить пользователя из БД.
    
    Args:
        user_id: Mattermost ID пользователя
        
    Returns:
        Объект User или None если не найден
    """
    session = self.db.get_session()
    try:
        user = session.query(User).filter_by(mattermost_id=user_id).first()
        return user
    finally:
        session.close()
```

## Процесс Review

1. Минимум 1 approval от maintainer
2. Все checks должны пройти
3. Нет конфликтов с main веткой
4. Код соответствует style guide

## Лицензия

Все контрибьюции лицензируются под MIT License.

## Вопросы?

Откройте [Discussion](../../discussions) или свяжитесь с maintainer.

Спасибо за вклад! 🎉
