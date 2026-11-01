#!/bin/bash
# ========================================================
# SubGame Backend Production Deploy Script for Ubuntu VPS
# ========================================================
set -e

echo ">>> [1/5] Updating packages and checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    apt-get update && apt-get install -y docker-compose-plugin docker-compose
fi

echo ">>> [2/5] Checking .env configuration..."
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Iltimos, .env faylini ochib CLICK_SECRET_KEY va parollarni tekshiring!"
fi

echo ">>> [3/5] Building and launching Docker containers..."
docker compose down || true
docker compose up -d --build

echo ">>> [4/5] Running migrations and initial setup..."
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py create_admin || true
docker compose exec -T web python scripts/import_firestore_data.py || true

echo ">>> [5/5] SubGame Backend muvaffaqiyatli ishga tushdi!"
docker compose ps
