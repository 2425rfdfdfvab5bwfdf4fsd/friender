@echo off
title Arix — Local Bridge (Desktop Control)
color 0B

echo.
echo  ============================================
echo    Arix Local Bridge  —  Desktop Control
echo  ============================================
echo.
echo  This gives Arix mouse and keyboard control
echo  over your PC. Make sure Arix server is
echo  already running (launch.bat) first.
echo.
echo  SAFETY: Move mouse to TOP-LEFT corner at
echo  any time to immediately stop automation.
echo  ─────────────────────────────────────────
echo.

:: ── Check venv ─────────────────────────────────────────────────────────────
if not exist .venv\Scripts\activate (
    echo  [ERROR] Virtual environment not found.
    echo  Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate

:: ── Install pyautogui if missing ───────────────────────────────────────────
pip show pyautogui >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Installing pyautogui (first time only)...
    pip install pyautogui --quiet
    echo  [OK] pyautogui installed.
    echo.
)

:: ── Start bridge ───────────────────────────────────────────────────────────
echo  Connecting to Arix at ws://localhost:5000/ws/bridge ...
echo  Press Ctrl+C to disconnect.
echo.
python local_bridge/bridge_agent.py --server ws://localhost:5000/ws/bridge

echo.
echo  Bridge disconnected.
pause
