@echo off
title TGControl - Setup
echo.
echo  ========================================
echo   TGControl - First Time Setup
echo  ========================================
echo.

cd /d "%~dp0\.."

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)
echo  [OK] Python found

REM Create data dir
if not exist "data" mkdir data
if not exist "data\sessions" mkdir data\sessions
if not exist "data\logs" mkdir data\logs

REM Install dependencies
echo.
echo  Installing Python packages...
pip install -r requirements.txt --quiet

echo.
echo  ========================================
echo   NEXT STEP: Edit config.js (inside backend)
echo   Fill in your api_id and api_hash from
echo   https://my.telegram.org
echo  ========================================
echo.
pause
