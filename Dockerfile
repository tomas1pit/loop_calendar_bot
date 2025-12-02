FROM python:3.11-slim

WORKDIR /app

# Установить зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копировать код приложения
COPY . .

# Создать директорию для данных
RUN mkdir -p /data

# Запустить бота
CMD ["python", "bot.py"]
