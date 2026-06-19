@echo off
title Arix - Local Bridge (Desktop Control)
color 0B

echo.
echo  =====================================================
echo    Arix Local Bridge  -  Desktop Control
echo  =====================================================
echo.
echo  Gives Arix mouse + keyboard control over your PC.
echo.
echo  REQUIREMENTS:
echo    - Arix server must already be running  (launch.bat)
echo    - Run this in a SECOND window alongside launch.bat
echo.
echo  SAFETY:
echo    Move mouse to TOP-LEFT corner at any time to
echo    immediately stop all automation (failsafe).
echo.
echo  -----------------------------------------------------
echo.

:: Check .venv exists
if not exist .venv\Scripts\activate (
    echo  [ERROR] Virtual environment not found.
    echo          Run setup.bat first, then re-run this script.
    echo.
    pause
    exit /b 1
)

:: Activate venv
call .venv\Scripts\activate

:: Install pyautogui if missing
pip show pyautogui >nul 2>&1
if errorlevel 1 (
    echo  [INFO] pyautogui not found - installing now (first time only)...
    pip install pyautogui --quiet
    if errorlevel 1 (
        echo.
        echo  [ERROR] pyautogui install failed.
        echo          Try installing it manually:
        echo            .venv\Scripts\activate
        echo            pip install pyautogui
        echo.
        pause
        exit /b 1
    )
    echo  [OK] pyautogui installed.
    echo.
)

:: Choose server
echo  Connect to which Arix server?
echo.
echo    1. Local PC   -  ws://localhost:5000/ws/bridge
echo    2. Remote     -  wss://your-app.replit.app/ws/bridge
echo.
set /p SERVER_CHOICE="  Enter 1 or 2 (default = 1): "

if "%SERVER_CHOICE%"=="2" goto :remote_server

:: Local (default)
set BRIDGE_URL=ws://localhost:5000/ws/bridge
goto :do_connect

:remote_server
set /p REMOTE_HOST="  Paste your server hostname (e.g. arix.your-name.replit.app): "
set BRIDGE_URL=wss://%REMOTE_HOST%/ws/bridge

:do_connect
echo.
echo  Connecting to: %BRIDGE_URL%
echo  Press Ctrl+C to disconnect.
echo.

python local_bridge/bridge_agent.py --server %BRIDGE_URL%

echo.
echo  Bridge disconnected.
echo  Press any key to close this window.
pause
