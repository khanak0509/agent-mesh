#!/bin/sh
set -e

echo "waiting for postgres..."
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
  sleep 1
done

echo "running alembic..."
cd /app
alembic -c migrations/alembic.ini upgrade head
echo "migrations done"
