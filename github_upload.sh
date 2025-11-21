#!/bin/bash

# Скрипт для быстрой загрузки календарного бота на GitHub

echo "🚀 Calendar Bot GitHub Upload Script"
echo "======================================"
echo ""

# Получить имя пользователя
read -p "Введите ваше имя пользователя GitHub (USERNAME): " GITHUB_USERNAME

if [ -z "$GITHUB_USERNAME" ]; then
    echo "❌ Ошибка: имя пользователя не может быть пусто"
    exit 1
fi

echo ""
echo "Инструкции:"
echo "1. Откройте https://github.com/new"
echo "2. Заполните:"
echo "   - Repository name: calendar_bot"
echo "   - Visibility: Public"
echo "   - НЕ выбирайте 'Initialize this repository'"
echo "3. Нажмите 'Create repository'"
echo "4. После создания, вернитесь сюда"
echo ""
read -p "Нажмите Enter когда репозиторий создан..."

echo ""
echo "Загрузка на GitHub..."
echo ""

cd /Users/admin/yougile_loop_bot/loop_calendar_bot

# Добавить remote
git remote add origin https://github.com/$GITHUB_USERNAME/calendar_bot.git
echo "✓ Remote добавлена"

# Убедиться, что на ветке main
git branch -M main
echo "✓ Ветка переименована в main"

# Загрузить на GitHub
git push -u origin main
echo "✓ Репозиторий загружен на GitHub"

# Создать tag для версии 1.0.0
git tag -a v1.0.0 -m "Initial release - Calendar Bot v1.0.0"
git push origin v1.0.0
echo "✓ Tag v1.0.0 создан и загружен"

echo ""
echo "✅ УСПЕШНО!"
echo ""
echo "Ваш репозиторий доступен на:"
echo "   https://github.com/$GITHUB_USERNAME/calendar_bot"
echo ""
echo "Дальше можете:"
echo "1. Добавить Topics на странице Settings"
echo "2. Включить Discussions"
echo "3. Создать Issues"
echo "4. Пригласить участников проекта"
echo ""
