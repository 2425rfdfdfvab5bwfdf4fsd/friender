@echo off
title Arix — Local Bridge (Desktop Control)
color 0B

echo.
echo  ============================================
echo    Arix Local Bridge  —  Desktop Control
echo  ============================================
echo.
echo  Gives Arix mouse + keyboard control over your PC.
echo.
echo  REQUIREMENTS:
echo    • Arix server must already be running (launch.bat)
echo    • Run this in a SECOND window alongside launch.bat
echo.
echo  SAFETY:
echo    Move mouse to TOP-LEFT corner at any time to
echo    immediately stop all automation (failsafe).
echo.
echo  ─────────────────────────────────────────────────────────────
echo.

:: ── Check venv ───────────────────────────────────────────────────────────────
if not exist .venv\Scripts\activate (
    echo  [ERROR] Virtual environment not found.
    echo  Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate

:: ── Install pyautogui if missing ─────────────────────────────────────────────
pip show pyautogui >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Installing pyautogui for desktop control (first time only)...
    pip install pyautogui --quiet
    if errorlevel 1 (
        echo  [ERROR] pyautogui install failed.
        echo  Try running:  pip install pyautogui
        pause
        exit /b 1
    )
    echo  [OK] pyautogui installed.
    echo.
)

:: ── Ask for server address ───────────────────────────────────────────────────
echo  Connect to which Arix server?
echo.
echo    1. Local PC (default)  — ws://localhost:5000/ws/bridge
echo    2. Replit / cloud      — wss://your-app.replit.app/ws/bridge
echo.
set /p SERVER_CHOICE="  Enter 1 or 2 (or press Enter for local): "

if "%SERVER_CHOICE%"=="2" (
    set /p SERVER_URL="  Paste your Replit URL (e.g. wss://arix.your-name.replit.app): "
    set BRIDGE_URL=%SERVER_URL%/ws/bridge
) else (
    set BRIDGE_URL=ws://localhost:5000/ws/bridge
)

echo.
echo  Connecting to: %BRIDGE_URL%
echo  Press Ctrl+C to disconnect.
echo.

python local_bridge/bridge_agent.py --server %BRIDGE_URL%

echo.
echo  Bridge disconnected.
pause
