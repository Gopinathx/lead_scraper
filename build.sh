#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

# Install ONLY the chromium browser binary without requiring root privileges
playwright install chromium