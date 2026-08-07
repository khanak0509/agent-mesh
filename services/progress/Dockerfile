FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY shared /app/shared
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e /app/shared

COPY services/progress /app/services/progress

ENV PYTHONPATH=/app/shared:/app/services/progress
EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
