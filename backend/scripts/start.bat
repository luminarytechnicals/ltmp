@echo off
title TGControl - Running
echo.
echo  Starting TGControl...
echo  Open browser at: http://localhost:3421
echo.
cd /d "%~dp0\.."
python server.py
pause
