#!/usr/bin/env bash
# Arix v9.3 — Local Bridge: Desktop Control (Mac / Linux)
# Run in a SECOND terminal AFTER launch.sh is already running.

BOLD="\033[1m"
YELLOW="\033[0;33m"
GREEN="\033[0;32m"
RED="\033[0;31m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}  ============================================${RESET}"
echo -e "${BOLD}    Arix Local Bridge  —  Desktop Control${RESET}"
echo -e "${BOLD}  ============================================${RESET}"
echo ""
echo "  Gives Arix mouse + keyboard control over your PC."
echo ""
echo -e "  ${BOLD}REQUIREMENTS:${RESET}"
echo "    • Arix server must already be running (launch.sh)"
echo "    • This runs in a SECOND terminal window"
echo ""
echo -e "  ${YELLOW}SAFETY: Move mouse to TOP-LEFT corner at any time${RESET}"
echo -e "  ${YELLOW}to immediately stop all automation (failsafe).${RESET}"
echo ""
echo "  ─────────────────────────────────────────────────────────────"
echo ""

# ── Check venv ────────────────────────────────────────────────────────────────
if [ ! -f ".venv/bin/activate" ]; then
    echo -e "  ${RED}[ERROR]${RESET} Virtual environment not found. Run  bash setup.sh  first."
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ── Install pyautogui if missing ─────────────────────────────────────────────
if ! python -c "import pyautogui" &>/dev/null; then
    echo "  [INFO] Installing pyautogui (first time only)..."
    pip install pyautogui --quiet
    echo -e "  ${GREEN}[OK]${RESET} pyautogui installed."
    echo ""
fi

# ── macOS: warn about accessibility permissions ───────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "  ${YELLOW}[macOS]${RESET} Desktop automation requires Accessibility permission."
    echo "         System Settings → Privacy & Security → Accessibility"
    echo "         Add your terminal app (Terminal, iTerm2, etc.) to the list."
    echo ""
fi

# ── Choose server ────────────────────────────────────────────────────────────
echo "  Connect to which Arix server?"
echo ""
echo "    1. Local PC (default)  — ws://localhost:5000/ws/bridge"
echo "    2. Replit / cloud      — wss://your-app.replit.app/ws/bridge"
echo ""
read -rp "  Enter 1 or 2 (or press Enter for local): " SERVER_CHOICE

if [ "$SERVER_CHOICE" == "2" ]; then
    read -rp "  Paste your server URL (e.g. wss://arix.yourname.replit.app): " SERVER_BASE
    BRIDGE_URL="${SERVER_BASE}/ws/bridge"
else
    BRIDGE_URL="ws://localhost:5000/ws/bridge"
fi

echo ""
echo "  Connecting to: $BRIDGE_URL"
echo "  Press Ctrl+C to disconnect."
echo ""

python local_bridge/bridge_agent.py --server "$BRIDGE_URL"

echo ""
echo "  Bridge disconnected."
echo ""
