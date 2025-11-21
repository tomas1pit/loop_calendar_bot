# 🚀 Deployment Guide

Полное руководство по развертыванию Calendar Bot в production.

## 📋 Предварительные требования

- Docker & Docker Compose установлены
- Mattermost сервер v5.0+
- Доступ к Mail.ru календарю
- IP адрес для внешнего доступа к боту

## 🔐 Подготовка

### 1. Сгенерировать ENCRYPTION_KEY

```bash
python3 -c "from encryption import EncryptionManager; print(EncryptionManager.generate_key())"
```

Сохраните результат - это будет значение `ENCRYPTION_KEY` в .env

### 2. Создать Bot Token в Mattermost

1. Перейдите в System Console → Integrations → Bot Accounts
2. Create New Bot Account
3. Установите имя: `calendar_bot`
4. Скопируйте Token - это `MATTERMOST_BOT_TOKEN`
5. Убедитесь, что бот может отправлять DM

### 3. Определить URLs

- `MATTERMOST_BASE_URL` - URL вашего Mattermost (например: https://mattermost.company.com)
- `MM_ACTIONS_URL` - Внешний URL для вебхука действий кнопок

## 🐳 Deploy с Docker Compose

### Option 1: На машине с Docker

```bash
# Клонировать репозиторий
git clone https://github.com/USERNAME/calendar_bot.git
cd calendar_bot

# Создать .env файл
cp .env.example .env

# Отредактировать .env
nano .env

# Запустить
docker-compose up -d

# Проверить логи
docker-compose logs -f loop-calendar-bot
```

### Option 2: Portainer Stacks (рекомендуется)

1. **Перейти в Portainer**
   - Open Portainer UI
   - Navigate to Stacks

2. **Создать Stack**
   - Click "Add Stack"
   - Выберите "Web editor"
   - Скопируйте содержимое docker-compose.yml
   - Нажмите "Deploy the stack"

3. **Установить переменные окружения**
   - В разделе Environment переменных заполните:
     - `MATTERMOST_BASE_URL`
     - `MATTERMOST_BOT_TOKEN`
     - `MM_ACTIONS_URL`
     - `ENCRYPTION_KEY`

4. **Другие переменные (опционально)**
   ```
   CALDAV_BASE_URL=https://calendar.mail.ru
   TZ=Europe/Moscow
   CHECK_INTERVAL=60
   REMINDER_MINUTES=15
   ```

### Option 3: Kubernetes

```bash
# Создать namespace
kubectl create namespace calendar-bot

# Создать secret с переменными окружения
kubectl create secret generic calendar-bot-secrets \
  --from-literal=MATTERMOST_BOT_TOKEN=your_token \
  --from-literal=ENCRYPTION_KEY=your_key \
  -n calendar-bot

# Развернуть deployment
kubectl apply -f k8s-deployment.yaml -n calendar-bot
```

## ✅ Проверка после развертывания

```bash
# 1. Проверить статус контейнера
docker ps | grep calendar

# 2. Проверить логи
docker logs -f loop-calendar-bot

# 3. Проверить подключение к Mattermost
docker exec loop-calendar-bot curl -X GET http://localhost:8080/health

# 4. Тест в Mattermost
# Отправьте личное сообщение: "@calendar_bot"
# Бот должен ответить
```

## 📊 Мониторинг

### Логи

```bash
# Real-time logs
docker-compose logs -f loop-calendar-bot

# Last 100 lines
docker-compose logs --tail=100 loop-calendar-bot

# За последний час
docker-compose logs --since 1h loop-calendar-bot
```

### Health Check

```bash
# Проверить здоровье приложения
curl http://localhost:8080/health

# Проверить БД
docker exec loop-calendar-bot ls -la /data/
```

### Метрики

```bash
# Размер контейнера
docker ps --no-trunc | grep calendar

# Использование памяти
docker stats loop-calendar-bot
```

## 🔧 Обновление бота

```bash
# Вытащить последние изменения
git pull origin main

# Перестроить образ
docker-compose build --no-cache

# Перезапустить
docker-compose up -d

# Проверить логи
docker-compose logs -f loop-calendar-bot
```

## 🚨 Обработка проблем

### Бот не запускается

```bash
# 1. Проверить логи
docker-compose logs loop-calendar-bot

# 2. Проверить конфигурацию .env
cat .env

# 3. Проверить коннектор
docker exec loop-calendar-bot python -c "from bot import Bot; print('OK')"

# 4. Перезапустить
docker-compose restart loop-calendar-bot
```

### Ошибка подключения к Mattermost

```bash
# Проверить доступность Mattermost
curl -I https://your-mattermost.com

# Проверить токен
echo "MATTERMOST_BOT_TOKEN должен быть действительным"

# Проверить URL
echo "MATTERMOST_BASE_URL должен быть полным URL"
```

### Ошибка CalDAV

```bash
# Проверить доступность календаря
curl -I https://calendar.mail.ru

# Проверить данные пользователя
# Пароль должен быть пароль приложения (не пароль аккаунта)
```

### Проблемы с БД

```bash
# Проверить права доступа
ls -la /data/

# Переинициализировать БД
docker exec loop-calendar-bot python init_db.py

# Очистить БД (осторожно!)
rm /data/calendar_bot.db
docker exec loop-calendar-bot python init_db.py
```

## 📈 Production Best Practices

### 1. Резервные копии

```bash
# Ежедневное резервное копирование БД
0 2 * * * docker exec loop-calendar-bot cp /data/calendar_bot.db /backup/calendar_bot.db.$(date +\%Y\%m\%d)
```

### 2. Логирование

```bash
# Сохранять логи
docker-compose logs loop-calendar-bot > logs/bot-$(date +%Y%m%d).log
```

### 3. Обновления

```bash
# Регулярно обновлять зависимости
docker-compose pull
docker-compose up -d
```

### 4. Мониторинг

- Используйте Prometheus/Grafana для метрик
- Настройте alerts в Slack/Telegram
- Регулярно проверяйте логи

## 🔒 Security Hardening

### 1. Firewall

```bash
# Разрешить только необходимые порты
sudo ufw allow 8080/tcp  # Bot actions
sudo ufw allow 443/tcp   # HTTPS
```

### 2. SSL/TLS

```bash
# Использовать Let's Encrypt для MM_ACTIONS_URL
# Пример с nginx reverse proxy
```

### 3. Network

```bash
# Запустить в изолированной сети
docker network create calendar-bot-network
docker-compose --network calendar-bot-network up -d
```

## 📞 Support

При проблемах:
1. Проверьте логи
2. Откройте [Issue](../../issues) с логами и конфигурацией
3. Напишите в [Discussions](../../discussions)

---

**Важно:** Никогда не коммитьте .env файл с реальными значениями в репозиторий!
