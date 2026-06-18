@echo off
title Arix — AI Computer Control Agent
color 0A

echo.
echo  ============================================
echo    Arix v9.5  —  Starting...
echo  ============================================
echo.

:: ── Check venv exists ────────────────────────────────────────────────────────
if not exist .venv\Scripts\activate (
    echo  [ERROR] Virtual environment not found.
    echo.
    echo  Run setup.bat first to install Arix.
    echo.
    pause
    exit /b 1
)

:: ── Check .env exists ────────────────────────────────────────────────────────
if not exist .env (
    echo  [INFO] No .env file found.
    echo.
    echo  Arix will run using:
    echo    • Local Ollama  (if you have it installed and running)
    echo    • Heuristic demo mode  (if no Ollama detected)
    echo.
    echo  To add an AI key, run setup.bat or create a .env file manually.
    echo  See SETUP_GUIDE.md for instructions.
    echo.
    timeout /t 4 >nul
)

:: ── Activate venv ────────────────────────────────────────────────────────────
call .venv\Scripts\activate

:: ── Show status ──────────────────────────────────────────────────────────────
echo  Server : http://localhost:5000
echo  Stop   : Press Ctrl+C in this window
echo  Bridge : Run launch_bridge.bat in a second window for desktop control
echo.
echo  ─────────────────────────────────────────────────────────────
echo.

:: ── Open browser automatically after 2.5 seconds ─────────────────────────────
start "" /b powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 2.5; Start-Process 'http://localhost:5000'"

:: ── Start server ─────────────────────────────────────────────────────────────
python main.py

echo.
echo  ─────────────────────────────────────────────────────────────
echo  Arix has stopped.
echo  ─────────────────────────────────────────────────────────────
pause
