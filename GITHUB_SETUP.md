# 📤 Инструкция для загрузки на GitHub

Следуйте этим шагам, чтобы создать новый публичный репозиторий и загрузить проект.

## Шаг 1: Создать новый репозиторий на GitHub

1. Перейдите на https://github.com/new
2. Заполните:
   - **Repository name**: `calendar_bot`
   - **Description**: `Mattermost to CalDAV Calendar Bot - reliable, simple and minimalist Mattermost bot for managing meetings via Mail.ru CalDAV`
   - **Visibility**: Public
   - **Initialize this repository with**: НЕ выбирайте ничего (у нас уже есть коммиты локально)
3. Нажмите "Create repository"

## Шаг 2: Добавить remote и загрузить

Выполните команды в терминале:

```bash
cd /Users/admin/yougile_loop_bot/loop_calendar_bot

# Добавить remote репозиторий (замените USERNAME на ваше имя пользователя)
git remote add origin https://github.com/USERNAME/calendar_bot.git

# Загрузить ветку main
git branch -M main
git push -u origin main
```

## Шаг 3: Проверить на GitHub

1. Откройте https://github.com/USERNAME/calendar_bot
2. Убедитесь, что:
   - ✅ Все файлы загружены
   - ✅ README.md отображается на главной
   - ✅ 2 коммита в истории
   - ✅ Репозиторий публичный

## Шаг 4: Добавить теги (опционально)

```bash
# Создать tag для версии 1.0.0
git tag -a v1.0.0 -m "Initial release"
git push origin v1.0.0
```

## Шаг 5: Настроить репозиторий (опционально)

### Topics
Добавьте на странице Settings → Topics:
- `mattermost`
- `caldav`
- `calendar`
- `bot`
- `mail-ru`
- `docker`
- `python`

### About
Обновите описание в About (значок шестеренки):
- Description: `Mattermost Calendar Bot with CalDAV integration`
- Website: `(оставить пусто или указать документацию)`

## Готово! 🎉

Ваш репозиторий теперь доступен на:
```
https://github.com/USERNAME/calendar_bot
```

## Дополнительные команды

### Синхронизировать локальные изменения

```bash
cd /Users/admin/yougile_loop_bot/loop_calendar_bot

# Добавить изменения
git add .

# Создать коммит
git commit -m "your message"

# Загрузить на GitHub
git push origin main
```

### Просмотреть статус

```bash
git status
git log --oneline
git remote -v
```

### Если что-то пошло не так

```bash
# Отменить последний коммит (но не удаляя файлы)
git reset --soft HEAD~1

# Просмотреть историю
git log -p

# Очистить неустанные файлы
git clean -fd
```

---

**Примечание:** Замените `USERNAME` на ваше имя пользователя GitHub везде, где указано.
