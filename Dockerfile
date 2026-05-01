FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Cache bust: force fresh copy
ARG CACHEBUST=1
COPY backend /app/backend

WORKDIR /app/backend
CMD ["python", "-m", "bot.main"]
