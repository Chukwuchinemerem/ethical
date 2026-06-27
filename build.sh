#!/usr/bin/env bash
set -o errexit

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Running migrations..."
python3 manage.py migrate --noinput

echo "==> Collecting static files..."
python3 manage.py collectstatic --noinput

echo "==> Build complete ✅"
