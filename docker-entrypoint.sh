#!/bin/sh
set -e

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"

# Wait for the database named by DATABASE_URL.
until python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection()" 2>/dev/null; do
  echo "Waiting for database..."
  sleep 2
done

# `docker compose run --rm dummy seed`: the demo directory, in dependency order (make seed).
if [ "$1" = "seed" ]; then
  python manage.py signing_keys ensure
  python scripts/seed_admin.py
  python scripts/seed_clients.py
  python scripts/seed_companies.py
  python scripts/seed_employees.py
  python scripts/show_demo.py
  exit 0
fi

# Only the web container migrates; the delivery loop sets SKIP_MIGRATIONS=1.
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running migrations..."
  python manage.py migrate --noinput
  # The JWKS must hold a key for each purpose before the Marketplace asks for it.
  python manage.py signing_keys ensure
fi

exec "$@"
