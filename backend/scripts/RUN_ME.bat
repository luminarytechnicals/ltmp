@echo off
title LTMP - Launcher
color 0A
echo.
echo  ==========================================
echo   LTMP - Luminary Telegram Management Panel
echo  ==========================================
echo.

cd /d "%~dp0\.."

REM ── Check Python ──────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo  Download from: https://python.org/downloads
    echo  Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo  [OK] Python found

REM ── Create data folders if missing ────────────────────────────
if not exist "data" mkdir data
if not exist "data\sessions" mkdir data\sessions

REM ── Install packages if not already installed ─────────────────
python -c "import telethon" >nul 2>&1
if errorlevel 1 (
    echo  [SETUP] Installing packages for the first time...
    python -m pip install -r requirements.txt --quiet
    echo  [OK] Packages installed
) else (
    echo  [OK] Packages already installed
)

REM ── Open browser after 3 seconds ──────────────────────────────
echo.
echo  [STARTING] Launching backend...
echo  [BROWSER]  Opening http://localhost:3421 in 4 seconds...
echo.
start "" /b cmd /c "timeout /t 4 >nul && start http://localhost:3421"

REM ── Start the server (this window stays open showing logs) ────
python server.py

pause
