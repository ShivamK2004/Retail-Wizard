@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-web.txt
if "%SECRET_KEY%"=="" for /f %%i in ('python -c "import secrets; print(secrets.token_urlsafe(48))"') do set SECRET_KEY=%%i
if "%INITIAL_ADMIN_SETUP_KEY%"=="" (
  for /f %%i in ('python -c "import secrets; print(secrets.token_urlsafe(32))"') do set INITIAL_ADMIN_SETUP_KEY=%%i
  echo.
  echo One-time administrator setup key for a NEW local database:
  echo %INITIAL_ADMIN_SETUP_KEY%
  echo Keep this key private. It is not needed after the first administrator is created.
  echo.
)
if "%APP_TIMEZONE%"=="" set APP_TIMEZONE=Asia/Kolkata
if "%COOKIE_SECURE%"=="" set COOKIE_SECURE=false
if "%RETAIL_WIZARD_DB%"=="" set RETAIL_WIZARD_DB=%CD%\data\retail_wizard_web.db
python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --reload
