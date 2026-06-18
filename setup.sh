#!/usr/bin/env bash
# Arix v9.3 — First-Time Setup (Mac / Linux)
# Run once: bash setup.sh

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

ok()   { echo -e "  ${GREEN}[OK]${RESET} $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${RESET} $*"; }
err()  { echo -e "  ${RED}[ERROR]${RESET} $*"; }
info() { echo -e "  $*"; }

echo ""
echo -e "${BOLD}  ============================================${RESET}"
echo -e "${BOLD}    Arix v9.3  —  First-Time Setup${RESET}"
echo -e "${BOLD}  ============================================${RESET}"
echo ""

# ── Detect Python ─────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null)
        if "$cmd" -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "Python 3.11+ not found."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        info "Install via Homebrew:  brew install python@3.11"
        info "Or download from:      https://www.python.org/downloads/"
    else
        info "Install via apt:       sudo apt install python3.11 python3.11-venv"
        info "Or download from:      https://www.python.org/downloads/"
    fi
    echo ""
    exit 1
fi

ok "$($PYTHON --version) found at $(command -v $PYTHON)"
echo ""

# ── Virtual environment ───────────────────────────────────────────────────────
echo "  [1/5] Setting up virtual environment (.venv)..."
if [ -d ".venv" ]; then
    info "       .venv already exists — skipping (delete it manually for a fresh install)."
else
    $PYTHON -m venv .venv
    ok "Virtual environment created."
fi
echo ""

# shellcheck disable=SC1091
source .venv/bin/activate

# ── Upgrade pip ───────────────────────────────────────────────────────────────
python -m pip install --upgrade pip --quiet

# ── Install Python packages ───────────────────────────────────────────────────
echo "  [2/5] Installing Python packages (1-3 minutes)..."
pip install -r requirements.txt --quiet
ok "All Python packages installed."
echo ""

# ── Playwright ────────────────────────────────────────────────────────────────
echo "  [3/5] Installing Playwright browser (Chromium, ~130 MB)..."
if python -m playwright install chromium 2>/dev/null; then
    ok "Playwright Chromium installed."
else
    warn "Playwright install failed or was skipped."
    info "      Web browsing tools will be unavailable."
    info "      You can run later:  source .venv/bin/activate && playwright install chromium"
fi
echo ""

# ── .env file ─────────────────────────────────────────────────────────────────
echo "  [4/5] Setting up .env config file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    ok ".env created from .env.example"
else
    ok ".env already exists — keeping your settings."
fi
echo ""

# ── API key ───────────────────────────────────────────────────────────────────
echo "  [5/5] Add your AI provider key to .env"
echo ""
echo -e "  ${BOLD}┌─────────────────────────────────────────────────────────────────┐${RESET}"
echo -e "  ${BOLD}│  Paste your key into .env:                                      │${RESET}"
echo -e "  ${BOLD}│                                                                  │${RESET}"
echo -e "  ${BOLD}│  • Anthropic Claude (best):  ANTHROPIC_API_KEY=sk-ant-...      │${RESET}"
echo -e "  ${BOLD}│  • OpenAI GPT-4:             OPENAI_API_KEY=sk-...             │${RESET}"
echo -e "  ${BOLD}│  • Google Gemini (free):     GEMINI_API_KEY=...                │${RESET}"
echo -e "  ${BOLD}│  • No key? Arix auto-uses local Ollama if it is running        │${RESET}"
echo -e "  ${BOLD}└─────────────────────────────────────────────────────────────────┘${RESET}"
echo ""

# Try to open .env in a sensible editor
if command -v code &>/dev/null; then
    info "Opening .env in VS Code..."
    code .env
elif command -v nano &>/dev/null; then
    info "Opening .env in nano (save with Ctrl+O, exit with Ctrl+X)..."
    nano .env
elif command -v open &>/dev/null; then
    info "Opening .env in default editor..."
    open .env
else
    info "Edit .env manually with your favourite text editor."
fi
echo ""

# ── Optional pyautogui ────────────────────────────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────────────────────────────────"
echo "  Optional: Desktop Control (mouse + keyboard automation)"
echo "  ─────────────────────────────────────────────────────────────────────"
echo "  Enables: 'Open TikTok', 'Click the Submit button', 'Type into app', etc."
echo ""
read -rp "  Install pyautogui for desktop control? [y/N]: " INSTALL_BRIDGE
if [[ "$INSTALL_BRIDGE" =~ ^[Yy]$ ]]; then
    pip install pyautogui --quiet
    ok "pyautogui installed. Use launch_bridge.sh to enable desktop control."
else
    info "Skipped. You can install later: source .venv/bin/activate && pip install pyautogui"
fi

echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo -e "${BOLD}    Setup complete!${RESET}"
echo -e "${BOLD}  ============================================================${RESET}"
echo ""
echo "    Next step:  bash launch.sh"
echo "    Then open:  http://localhost:5000"
echo ""
echo "    For desktop control: run  bash launch_bridge.sh  in a second terminal"
echo ""
