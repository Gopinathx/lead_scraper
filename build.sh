#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

# Install Playwright browser binary & dependencies
playwright install chromium --with-deps