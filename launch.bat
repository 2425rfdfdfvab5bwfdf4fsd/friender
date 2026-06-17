@echo off
title Arix — AI Computer Control Agent
color 0A

echo.
echo  ============================================
echo    Arix v8.2  —  Starting...
echo  ============================================
echo.

:: ── Check venv exists ──────────────────────────────────────────────────────
if not exist .venv\Scripts\activate (
    echo  [ERROR] Virtual environment not found.
    echo.
    echo  Run setup.bat first to install Arix.
    echo.
    pause
    exit /b 1
)

:: ── Check .env exists ──────────────────────────────────────────────────────
if not exist .env (
    echo  [WARNING] No .env file found.
    echo  Arix will run in demo mode (no AI key).
    echo  Run setup.bat to create your .env file.
    echo.
    timeout /t 3 >nul
)

:: ── Activate venv ──────────────────────────────────────────────────────────
call .venv\Scripts\activate

:: ── Open browser automatically after 2 seconds ────────────────────────────
start "" /b powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:5000'"

:: ── Start server ───────────────────────────────────────────────────────────
echo  Server starting at http://localhost:5000
echo  Your browser will open automatically.
echo.
echo  Press Ctrl+C to stop Arix.
echo  ─────────────────────────────────────────
echo.
python main.py

echo.
echo  Arix has stopped.
pause
