#!/usr/bin/env sh
set -e

# Ensure the SQLite directory exists (bind-mounted from the host)
mkdir -p "$(dirname "${SQLITE_PATH:-/bcmp/data/db.sqlite3}")"

echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Starting gunicorn"
exec gunicorn bcmp.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile -
