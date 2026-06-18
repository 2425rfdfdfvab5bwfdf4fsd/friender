#!/usr/bin/env bash
# Arix v9.5 — Launch Server (Mac / Linux)
# Usage: bash launch.sh

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}  ============================================${RESET}"
echo -e "${BOLD}    Arix v9.5  —  Starting...${RESET}"
echo -e "${BOLD}  ============================================${RESET}"
echo ""

# ── Check venv ────────────────────────────────────────────────────────────────
if [ ! -f ".venv/bin/activate" ]; then
    echo -e "  ${BOLD}[ERROR]${RESET} Virtual environment not found."
    echo ""
    echo "  Run first:  bash setup.sh"
    echo ""
    exit 1
fi

# ── Check .env ────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo -e "  ${YELLOW}[INFO]${RESET} No .env file found."
    echo ""
    echo "  Arix will use:"
    echo "    • Local Ollama  (if you have it installed and running)"
    echo "    • Heuristic demo mode  (if no Ollama detected)"
    echo ""
    echo "  To add an AI key: run  bash setup.sh  or create .env manually."
    echo ""
    sleep 3
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "  Server : http://localhost:5000"
echo "  Stop   : Ctrl+C"
echo "  Bridge : run  bash launch_bridge.sh  in a second terminal for desktop control"
echo ""
echo "  ─────────────────────────────────────────────────────────────"
echo ""

# ── Auto-open browser (background, after 2.5s) ────────────────────────────────
(
    sleep 2.5
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:5000" &>/dev/null
    elif command -v open &>/dev/null; then
        open "http://localhost:5000"
    fi
) &

# ── Start server ──────────────────────────────────────────────────────────────
python main.py

echo ""
echo "  ─────────────────────────────────────────────────────────────"
echo "  Arix has stopped."
echo ""
