@echo off
REM ClipNova GTA 6 Edition - Windows PC one-time setup.
REM Isko clipnova-gta6 folder ke andar se double-click karke chalao.
title ClipNova GTA 6 - PC Setup
setlocal EnableDelayedExpansion
cd /d %~dp0

echo ============================================
echo  ClipNova GTA 6 - PC Setup
echo ============================================
echo.

REM --- 1. Python check ---
python --version >nul 2>&1
if errorlevel 1 (
  echo [1/4] Python nahi mila. Download page khul raha hai...
  echo       Python 3.11+ install karo, aur install karte waqt
  echo       "Add python.exe to PATH" wala tick ON rakhna.
  start https://www.python.org/downloads/
  echo.
  echo Python install karke ye setup dobara chalao.
  pause
  exit /b 1
)
echo [1/4] Python mil gaya:
python --version

REM --- 2. ffmpeg check (winget se install) ---
ffmpeg -version >nul 2>&1
if errorlevel 1 (
  echo [2/4] ffmpeg nahi mila - winget se install ho raha hai...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  call :refreshpath
  ffmpeg -version >nul 2>&1
  if errorlevel 1 (
    echo       ffmpeg install nahi ho paya. Ye window band karke setup
    echo       dobara chalao, ya https://www.gyan.dev/ffmpeg/builds/
    echo       se ffmpeg manually install karo.
    pause
    exit /b 1
  )
)
echo [2/4] ffmpeg mil gaya.

REM --- 3. Virtual environment + packages ---
echo [3/4] Python packages install ho rahe hain (pehli baar 2-3 minute lag sakte hain)...
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo       Package install fail ho gaya. Upar wala error dekho aur dobara try karo.
  pause
  exit /b 1
)

REM --- 4. .env ---
if not exist .env copy .env.example .env >nul
echo [4/4] .env ready.

echo.
echo ============================================
echo  Setup ho gaya!
echo  Ab start-clipnova.bat double-click karo.
echo  Dashboard: http://localhost:8000
echo ============================================
pause
exit /b 0

:refreshpath
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
set "PATH=%SYS_PATH%;%USER_PATH%"
exit /b 0
