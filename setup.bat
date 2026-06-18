@echo off
title Arix — First-Time Setup
color 0A

echo.
echo  ============================================
echo    Arix v9.5  —  First-Time Setup
echo  ============================================
echo.
echo  This script will:
echo    1. Create a Python virtual environment
echo    2. Install all dependencies
echo    3. Install Playwright (browser automation)
echo    4. Create your .env config file
echo    5. Offer to install desktop control (optional)
echo.
pause

:: ── Check Python ────────────────────────────────────────────────────────────
echo.
echo  Checking for Python 3.11+...
py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3.11
    goto :python_ok
)
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3.12
    goto :python_ok
)
py -3.13 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3.13
    goto :python_ok
)
python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
    goto :python_ok
)
echo.
echo  [ERROR] Python 3.11+ not found on this PC.
echo.
echo  Download and install it from:
echo    https://www.python.org/downloads/
echo.
echo  IMPORTANT: On the installer's first screen,
echo  tick "Add Python to PATH" before clicking Install.
echo.
echo  After installing, re-run this script.
pause
exit /b 1

:python_ok
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo  [OK] %%v found.
echo.

:: ── Create virtual environment ───────────────────────────────────────────────
echo  [1/5] Creating virtual environment (.venv)...
if exist .venv (
    echo        .venv already exists — skipping (delete it manually for a fresh install).
) else (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)
echo.

:: ── Activate venv ────────────────────────────────────────────────────────────
call .venv\Scripts\activate

:: ── Upgrade pip quietly ──────────────────────────────────────────────────────
python -m pip install --upgrade pip --quiet

:: ── Install dependencies ─────────────────────────────────────────────────────
echo  [2/5] Installing Python packages (1-3 minutes)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check your internet connection and try again.
    pause
    exit /b 1
)
echo  [OK] All Python packages installed.
echo.

:: ── Install Playwright browsers ─────────────────────────────────────────────
echo  [3/5] Installing Playwright browser (Chromium)...
echo        This downloads ~130 MB. Press Ctrl+C to skip if on a slow connection.
python -m playwright install chromium
if errorlevel 1 (
    echo  [WARNING] Playwright install failed or was skipped.
    echo            Web browsing tools will be unavailable.
    echo            You can run this later:  .venv\Scripts\activate  then  playwright install chromium
) else (
    echo  [OK] Playwright Chromium installed.
)
echo.

:: ── Create .env file ─────────────────────────────────────────────────────────
echo  [4/5] Setting up .env config file...
if not exist .env (
    copy .env.example .env >nul
    echo  [OK] .env created from .env.example
) else (
    echo  [OK] .env already exists — keeping your settings.
)
echo.

:: ── Open .env in Notepad ─────────────────────────────────────────────────────
echo  [5/5] Opening .env in Notepad to add your API key...
echo.
echo  ┌─────────────────────────────────────────────────────────────────┐
echo  │  Paste your AI provider key and save the file:                 │
echo  │                                                                  │
echo  │  • Anthropic Claude (best):  ANTHROPIC_API_KEY=sk-ant-...      │
echo  │  • OpenAI GPT-4:             OPENAI_API_KEY=sk-...             │
echo  │  • Google Gemini (free):     GEMINI_API_KEY=...                │
echo  │  • No key?  Arix works with local Ollama (see SETUP_GUIDE.md)  │
echo  └─────────────────────────────────────────────────────────────────┘
echo.
notepad .env

:: ── Optional: pyautogui for desktop control ──────────────────────────────────
echo.
echo  ─────────────────────────────────────────────────────────────────────
echo  Optional: Desktop Control (mouse + keyboard automation)
echo  ─────────────────────────────────────────────────────────────────────
echo  Enables commands like "Open TikTok", "Click the Submit button", etc.
echo.
set /p INSTALL_BRIDGE="  Install pyautogui for desktop control? [y/N]: "
if /i "%INSTALL_BRIDGE%"=="y" (
    pip install pyautogui --quiet
    echo  [OK] pyautogui installed. Use launch_bridge.bat to enable desktop control.
) else (
    echo  [SKIPPED] You can install it later by running:
    echo            .venv\Scripts\activate
    echo            pip install pyautogui
)

echo.
echo  ============================================================
echo    Setup complete!
echo  ============================================================
echo.
echo    Next step: double-click  launch.bat  to start Arix.
echo    Then open http://localhost:5000 in your browser.
echo.
echo    For desktop control: also run  launch_bridge.bat
echo    in a second window after the main server is running.
echo.
pause
