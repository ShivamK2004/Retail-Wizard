#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-web.txt
export SECRET_KEY="${SECRET_KEY:-$(python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
if [[ -z "${INITIAL_ADMIN_SETUP_KEY:-}" ]]; then
  export INITIAL_ADMIN_SETUP_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  echo
  echo "One-time administrator setup key for a NEW local database:"
  echo "$INITIAL_ADMIN_SETUP_KEY"
  echo "Keep this key private. It is not needed after the first administrator is created."
  echo
fi
export APP_TIMEZONE="${APP_TIMEZONE:-Asia/Kolkata}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export RETAIL_WIZARD_DB="${RETAIL_WIZARD_DB:-$PWD/data/retail_wizard_web.db}"
exec python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --reload
