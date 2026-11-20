@echo off
REM ClipNova GTA 6 Edition - server start karo (double-click).
REM Pehle setup-pc.bat ek baar chala lo.
title ClipNova GTA 6 Server
cd /d %~dp0
if not exist .venv\Scripts\activate.bat (
  echo Pehle setup-pc.bat chalao - virtual environment nahi mila.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
echo.
echo  ClipNova GTA 6 chal raha hai:  http://localhost:8000
echo  Band karne ke liye Ctrl+C dabao, phir is window ko band kar do.
echo.
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
pause
