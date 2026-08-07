FROM node:20-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN mkdir -p /src/services/gateway/static && npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY shared /app/shared
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e /app/shared

COPY services/gateway /app/services/gateway
COPY --from=frontend /src/services/gateway/static /app/services/gateway/static

ENV PYTHONPATH=/app/shared:/app/services/gateway
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
