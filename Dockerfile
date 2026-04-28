FROM python:3.12-slim

# Робоча директорія
WORKDIR /app

# Встановлюємо системні залежності для psycopg/asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо requirements і встановлюємо
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Копіюємо весь код
COPY backend /app/backend

# Запускаємо бот
WORKDIR /app/backend
CMD ["python", "-m", "bot.main"]
