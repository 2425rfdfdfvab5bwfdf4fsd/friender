@echo off
:: Re-launch inside a persistent cmd window so it never closes unexpectedly
if not defined _ARIX_LAUNCHED (
    set _ARIX_LAUNCHED=1
    cmd /k "%~f0"
    exit /b
)
title Arix v9.5 - First-Time Setup
color 0A

echo.
echo  =====================================================
echo    Arix v9.5  -  First-Time Setup
echo  =====================================================
echo.
echo  This script will:
echo    1. Create a Python virtual environment
echo    2. Install all dependencies
echo    3. Install Playwright (browser automation)
echo    4. Create your .env config file
echo    5. (Optional) Install desktop control
echo.
pause

:: -------------------------------------------------------
:: Check Python 3.11+
:: -------------------------------------------------------
echo.
echo  Checking for Python 3.11+...
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=py -3.11 & goto :python_ok )
py -3.12 --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=py -3.12 & goto :python_ok )
py -3.13 --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=py -3.13 & goto :python_ok )
python --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=python  & goto :python_ok )

echo.
echo  [ERROR] Python 3.11 or later was not found on this PC.
echo.
echo  Download and install from:
echo    https://www.python.org/downloads/
echo.
echo  IMPORTANT: On the first installer screen,
echo  tick "Add Python to PATH" before clicking Install.
echo.
echo  After installing, close this window and re-run setup.bat.
echo.
pause
exit /b 1

:python_ok
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo  [OK] %%v found.
echo.

:: -------------------------------------------------------
:: [1/4] Virtual environment
:: -------------------------------------------------------
echo  [1/4] Creating virtual environment (.venv)...
if exist .venv (
    echo        .venv already exists - skipping creation.
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

:: Activate venv and upgrade pip silently
call .venv\Scripts\activate
python -m pip install --upgrade pip --quiet

:: -------------------------------------------------------
:: [2/4] Install Python packages
:: -------------------------------------------------------
echo  [2/4] Installing Python packages (this may take 1-3 minutes)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  [ERROR] pip install failed.
    echo  Check your internet connection and try again.
    echo  If the problem persists, see SETUP_GUIDE.md for manual steps.
    pause
    exit /b 1
)
echo  [OK] All Python packages installed.
echo.

:: -------------------------------------------------------
:: [3/4] Install Playwright (Chromium)
:: -------------------------------------------------------
echo  [3/4] Installing Playwright browser (Chromium, ~130 MB)...
echo        Press Ctrl+C to skip if you are on a slow connection.
echo.
python -m playwright install chromium
if errorlevel 1 (
    echo  [WARNING] Playwright install failed or was cancelled.
    echo            Web browsing tools will be unavailable until you run:
    echo              .venv\Scripts\activate
    echo              playwright install chromium
) else (
    echo  [OK] Playwright Chromium installed.
)
echo.

:: -------------------------------------------------------
:: [4/4] Create .env config file
:: -------------------------------------------------------
echo  [4/4] Setting up .env config file...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo  [OK] .env created from .env.example
    ) else (
        echo  ANTHROPIC_API_KEY=> .env
        echo  GEMINI_API_KEY=>> .env
        echo  GROQ_API_KEY=>> .env
        echo  OPENAI_API_KEY=>> .env
        echo  [OK] .env created (blank template)
    )
) else (
    echo  [OK] .env already exists - keeping your existing settings.
)
echo.

echo  -------------------------------------------------------
echo  Add your AI provider key (choose one to get started):
echo  -------------------------------------------------------
echo.
echo    Anthropic Claude (recommended)  -- ANTHROPIC_API_KEY=sk-ant-...
echo      Get key: https://console.anthropic.com/settings/keys
echo.
echo    Google Gemini   (free tier)     -- GEMINI_API_KEY=AIza...
echo      Get key: https://aistudio.google.com/app/apikey
echo.
echo    Groq / Llama 3  (free tier)     -- GROQ_API_KEY=gsk_...
echo      Get key: https://console.groq.com/keys
echo.
echo    OpenAI GPT-4o                   -- OPENAI_API_KEY=sk-...
echo      Get key: https://platform.openai.com/api-keys
echo.
echo    No key? Arix runs offline with a local Ollama model.
echo      Install Ollama: https://ollama.com  (then: ollama pull llama3)
echo.
echo  TIP: You can also add or switch keys inside the Arix web UI
echo       after launch -- open Settings and click any "+" provider card.
echo.
echo  Opening .env in Notepad now (save and close when done)...
notepad .env

:: -------------------------------------------------------
:: Optional: Desktop Control (pyautogui)
:: -------------------------------------------------------
echo.
echo  -------------------------------------------------------
echo  Optional: Desktop Control
echo  -------------------------------------------------------
echo  Enables commands like "Open TikTok", "Click Submit button",
echo  "Take a screenshot of my screen", etc.
echo.
set /p INSTALL_BRIDGE="  Install desktop control support? [y/N]: "
if /i "%INSTALL_BRIDGE%"=="y" (
    echo.
    echo  Installing pyautogui...
    pip install pyautogui --quiet
    if errorlevel 1 (
        echo  [WARNING] pyautogui install failed. You can try again later:
        echo            .venv\Scripts\activate
        echo            pip install pyautogui
    ) else (
        echo  [OK] pyautogui installed.
        echo       Run launch_bridge.bat in a second window after Arix starts.
    )
) else (
    echo.
    echo  [SKIPPED] You can enable desktop control later by running:
    echo    .venv\Scripts\activate
    echo    pip install pyautogui
    echo  Then use launch_bridge.bat alongside launch.bat.
)

:: -------------------------------------------------------
:: Done
:: -------------------------------------------------------
echo.
echo  =====================================================
echo    Setup complete!
echo  =====================================================
echo.
echo    Next steps:
echo      1. Double-click launch.bat to start Arix
echo      2. Open http://localhost:5000 in your browser
echo      3. To enable desktop control, also run launch_bridge.bat
echo         in a second window after the main server is running
echo.
echo    Full setup guide: SETUP_GUIDE.md
echo.
pause
