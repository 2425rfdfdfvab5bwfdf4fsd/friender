@echo off
title Arix — First-Time Setup
color 0A

echo.
echo  ============================================
echo    Arix v8.2  —  First-Time Setup
echo  ============================================
echo.

:: ── Check Python 3.11 ──────────────────────────────────────────────────────
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.11 not found.
    echo.
    echo  Download it from: https://www.python.org/downloads/
    echo  Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo  [OK] Python 3.11 found.
echo.

:: ── Create virtual environment ─────────────────────────────────────────────
echo  [1/4] Creating virtual environment (.venv)...
if exist .venv (
    echo        Already exists — recreating for a clean install.
    rmdir /s /q .venv
)
py -3.11 -m venv .venv
if errorlevel 1 (
    echo  [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)
echo  [OK] Virtual environment created.
echo.

:: ── Activate venv ──────────────────────────────────────────────────────────
call .venv\Scripts\activate

:: ── Install dependencies ───────────────────────────────────────────────────
echo  [2/4] Installing dependencies (this takes 1-3 minutes)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo  [OK] All packages installed.
echo.

:: ── Create .env file ───────────────────────────────────────────────────────
echo  [3/4] Setting up .env config file...
if not exist .env (
    copy .env.example .env >nul
    echo  [OK] .env created from .env.example
) else (
    echo  [OK] .env already exists — keeping your existing settings.
)
echo.

:: ── Open .env in Notepad ───────────────────────────────────────────────────
echo  [4/4] Opening .env in Notepad...
echo.
echo  -------------------------------------------------------------------
echo   Paste your ANTHROPIC_API_KEY (or OPENAI/GEMINI key) into .env,
echo   then save and close Notepad to finish setup.
echo  -------------------------------------------------------------------
echo.
notepad .env

echo.
echo  ============================================
echo    Setup complete!
echo    Run launch.bat to start Arix.
echo  ============================================
echo.
pause
