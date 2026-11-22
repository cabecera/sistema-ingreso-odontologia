#!/bin/sh
set -e

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py createcachetable

# Agrega esta línea para crear el superusuario automáticamente
python manage.py createsuperuser --noinput || true

exec gunicorn core.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 60 --max-requests 1000 --max-requests-jitter 100