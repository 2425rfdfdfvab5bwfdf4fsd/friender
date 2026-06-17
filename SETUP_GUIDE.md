# Arix — Setup Guide

> Your personal AI digital employee. Give it tasks in plain English — it plans, acts, and reports back.

---

## Table of Contents

1. [Quick Start (5 minutes)](#1-quick-start-5-minutes)
2. [Requirements](#2-requirements)
3. [Install Python](#3-install-python)
4. [Download Arix](#4-download-arix)
5. [Install Dependencies](#5-install-dependencies)
6. [Configure Your API Key](#6-configure-your-api-key)
7. [Set Up Your .env File](#7-set-up-your-env-file)
8. [Start the Server](#8-start-the-server)
9. [Local Bridge (Desktop Control)](#9-local-bridge-desktop-control)
10. [Integrations (Gmail, Notion, Slack…)](#10-integrations-optional)
11. [Example Commands](#11-example-commands)
12. [Configuration Reference](#12-configuration-reference)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Quick Start (5 minutes)

Already have Python 3.11+? Here's the fastest path:

```bash
# 1. Enter the project folder (use whatever name you downloaded it as)
cd friender          # or: cd arix, cd pacca, etc.

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 3. Install everything
pip install -e .

# 4. Copy the example config and add your API key
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
# → Open .env in Notepad and paste your ANTHROPIC_API_KEY

# 5. Start Arix
python main.py
```

Then open **http://localhost:5000** in your browser.

---

## 2. Requirements

| What | Minimum |
|------|---------|
| Python | **3.11** or newer |
| pip | latest (comes with Python) |
| RAM | 512 MB free |
| Internet | Required for AI features |
| OS | Windows 10/11 · macOS 12+ · Ubuntu 20.04+ |

---

## 3. Install Python

### Windows

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and download Python 3.11+
2. Run the installer
3. **Important:** tick **"Add Python to PATH"** before clicking Install
4. Verify it worked:
   ```cmd
   python --version
   ```
   You should see `Python 3.11.x` or higher.

### macOS

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python@3.11
```

### Linux (Ubuntu / Debian)

```bash
sudo apt update && sudo apt install python3.11 python3.11-pip python3.11-venv -y
```

---

## 4. Download Arix

### Option A — Git clone (recommended)

```bash
git clone https://github.com/your-username/arix.git
cd arix
```

### Option B — ZIP download

1. Download the ZIP from Replit or GitHub and unzip it
2. Open a terminal inside the unzipped folder:

```bash
# The folder name will match whatever you called it when downloading
cd friender      # adjust to your actual folder name
```

---

## 5. Install Dependencies

### Step A — Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

You'll see `(.venv)` in your prompt — this means it's active.

### Step B — Install packages

```bash
pip install -e .
```

This installs FastAPI, the Anthropic SDK, document tools, memory, security, and all other core dependencies from `pyproject.toml`.

### Step C — Optional extras

| Feature | Install command |
|---------|----------------|
| Browser automation (web scraping, form filling) | `pip install playwright==1.49.1 playwright-stealth && playwright install chromium` |
| Desktop automation (bridge agent) | `pip install pyautogui pillow websockets` |
| Development tools (tests, linting) | `pip install -e ".[dev]"` |

---

## 6. Configure Your API Key

Arix needs at least one AI provider to understand and plan your tasks.

### Option A — Anthropic Claude *(recommended — best results)*

1. Go to **[console.anthropic.com](https://console.anthropic.com)** → sign up / log in
2. Click **API Keys** → **Create Key**
3. Copy the key — it starts with `sk-ant-...`

### Option B — OpenAI GPT-4

1. Go to **[platform.openai.com](https://platform.openai.com)** → sign up / log in
2. Go to **API Keys** → **Create new secret key**
3. Copy the key — it starts with `sk-...`

> **Bonus:** An OpenAI key also unlocks **semantic (vector) memory search** — Arix can find similar past tasks using AI embeddings instead of just keyword matching.

### Option C — Google Gemini *(free tier available)*

1. Go to **[aistudio.google.com](https://aistudio.google.com)**
2. Click **Get API key** and copy it

> **No key?** Arix still runs in demo mode using a built-in heuristic planner. You can try it without any API key.

---

## 7. Set Up Your .env File

The project ships with a `.env.example` file listing every available setting. Copy it to `.env` and fill in your values:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Then open `.env` in any text editor (Notepad, VS Code, etc.) and edit it. The minimal setup looks like this:

```env
# Paste your API key for whichever provider you chose
ANTHROPIC_API_KEY=sk-ant-your-key-here
# OPENAI_API_KEY=sk-your-key-here
# GEMINI_API_KEY=your-key-here
```

> **Never commit `.env` to Git.** It's already in `.gitignore`. Your keys stay on your machine.

### Full .env reference

```env
# ── AI Providers (set at least one) ──────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...        # Claude — default, best results
# OPENAI_API_KEY=sk-...            # GPT-4 + enables vector memory
# GEMINI_API_KEY=...               # Google Gemini

# ── Security (optional but recommended for production) ────────────────────────
# Protects all API endpoints with a Bearer token
# Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"
# PACCA_ADMIN_TOKEN=

# Comma-separated allowed WebSocket origins (leave blank = allow all, fine for local)
# PACCA_ALLOWED_ORIGINS=localhost,127.0.0.1

# ── Runtime Tuning ────────────────────────────────────────────────────────────
# How many seconds before a tool call times out (default: 60)
# PACCA_TOOL_TIMEOUT=60

# Override where the config file lives (default: ~/.arix/config.json)
# PACCA_CONFIG_PATH=

# ── Integrations (all optional — add only what you need) ──────────────────────
# See Section 10 for how to get each of these credentials
```

---

## 8. Start the Server

```bash
python main.py
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Open your browser and go to:

```
http://localhost:5000
```

On your first visit you'll see the **onboarding screen** — enter your name, timezone, and preferred communication style. This personalizes how Arix talks to you.

> **Replit users:** The server is already running. Open the Webview tab — no `python main.py` needed.

---

## 9. Local Bridge (Desktop Control)

The **Local Bridge** runs on *your actual computer* and gives Arix mouse and keyboard control — clicking buttons, typing text, taking screenshots, just like you would.

| Without bridge | With bridge |
|----------------|-------------|
| File management, web browsing, integrations, code | Everything left + click inside any app, fill forms, control OBS Studio, use TikTok/Instagram natively |

### Setup

**Step 1 — Install bridge dependencies** *(one time only)*

```bash
pip install pyautogui pillow websockets
```

**Step 2 — Run the bridge in a second terminal**

Keep the Arix server running in your first terminal, then open a second one:

```bash
# Local server
python local_bridge/bridge_agent.py --server ws://localhost:5000/ws/bridge

# Replit / cloud-hosted server
python local_bridge/bridge_agent.py --server wss://your-app.replit.app/ws/bridge
```

You'll see:
```
╔══════════════════════════════════════════╗
║   Arix Local Bridge Agent               ║
║   Server : ws://localhost:5000/ws/bridge ║
╚══════════════════════════════════════════╝
Connected to Arix server ✓
```

The header badge changes from **Bridge: Off** to **Bridge: On ✓**.

### Safety features

- **Failsafe:** Move your mouse to the **top-left corner** of the screen at any time to immediately stop all desktop automation.
- **Disconnect:** Press `Ctrl+C` in the bridge terminal.
- **Token protection:** Add `--token YOUR_TOKEN` to both the server and bridge if you set `PACCA_ADMIN_TOKEN` in your `.env`.

---

## 10. Integrations (Optional)

These connect Arix to external services. Add the relevant variables to your `.env` file — Arix auto-detects which services are configured when it starts.

---

### Gmail

Read, search, send, and delete emails.

**Get credentials:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Enable the **Gmail API**
3. Create an **OAuth 2.0 Client ID** (Desktop App type)
4. Use the client ID + secret to run the OAuth flow and obtain a refresh token

```env
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

**What you can then say:** *"Show my unread emails"*, *"Search Gmail for invoices"*, *"Send an email to…"*

---

### Google Drive

List, search, read, and upload files.

```env
GOOGLE_DRIVE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=your-client-secret
GOOGLE_DRIVE_REFRESH_TOKEN=your-refresh-token
```

*(Same OAuth app as Gmail — just enable the Drive API too.)*

---

### Google Calendar

List, create, and delete calendar events.

```env
GOOGLE_CALENDAR_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
GOOGLE_CALENDAR_REFRESH_TOKEN=your-refresh-token
```

*(Same OAuth app — enable the Calendar API.)*

---

### Notion

Read and search your Notion workspace.

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → **New Integration**
2. Copy the **Internal Integration Token**

```env
NOTION_API_KEY=secret_your-notion-token-here
```

---

### Slack

Send messages and interact with channels.

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create App** → From Scratch
2. Under **OAuth & Permissions**, add bot scopes: `chat:write`, `channels:read`, `users:read`
3. Install to workspace and copy the **Bot User OAuth Token**

```env
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
```

---

### Trello

Manage boards, lists, and cards.

1. Go to [trello.com/app-key](https://trello.com/app-key) and copy your API key
2. Generate a token on the same page

```env
TRELLO_API_KEY=your-trello-api-key
TRELLO_API_TOKEN=your-trello-token
```

---

### Spotify

Control playback, search music, manage playlists.

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → **Create App**
2. Copy the **Client ID** and **Client Secret**

```env
SPOTIFY_CLIENT_ID=your-client-id
SPOTIFY_CLIENT_SECRET=your-client-secret
```

---

### YouTube

Search videos, get channel info, manage playlists.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services
2. Enable **YouTube Data API v3** → create an **API Key**

```env
YOUTUBE_API_KEY=your-youtube-api-key
```

---

### WhatsApp

Send WhatsApp messages via Twilio.

1. Sign up at [twilio.com](https://www.twilio.com) → enable the **WhatsApp Sandbox**
2. Copy your Account SID and Auth Token

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_RECIPIENT=whatsapp:+1your-number
```

---

## 11. Example Commands

Once Arix is running, just type in plain English:

### Files & System
```
Delete temp files from my PC
Organize my Downloads folder by file type
Find all PDFs in my Documents
Zip the project folder
Free up disk space and show me the result
```

### Web & Research
```
Search the web for the best Python courses and save results to a file
Summarize the article at https://example.com/article
Download the file at https://example.com/report.pdf
What's the latest news about AI?
```

### Apps & Desktop *(requires Local Bridge)*
```
Open TikTok and go to the upload page
Open OBS Studio and start recording
Open Instagram and go to Reels
Open LinkedIn and check my messages
```

### Gmail & Calendar
```
Show my unread emails
Search Gmail for invoices from last month
Send an email to john@example.com about the project status
Show my calendar events for this week
Create a calendar event for Friday at 3pm — Team standup
```

### Notion / Slack / Trello
```
Search my Notion for project notes
Send a Slack message to #general: "Build passed!"
Show my Trello boards
```

### Code & AI
```
Generate a Python script that renames files by date
Explain what this code does
Analyze the quality of main.py
Run this snippet and show the output
Analyze the screenshot I took
```

### Multi-step Goals
```
Research the top 5 cloud storage services and create a comparison spreadsheet
Read my latest unread emails and create a task list in Notion
Clean up my PC, free disk space, and give me a report
Send a WhatsApp message to John saying I'll be 10 minutes late
```

---

## 12. Configuration Reference

Arix's config lives at **`~/.arix/config.json`** and is created automatically on first run. You can also change settings in the **Settings panel** inside the UI.

| Setting | What it does | Default |
|---------|--------------|---------|
| `provider` | Which AI to use: `anthropic`, `openai`, `gemini` | `anthropic` |
| `model` | Model name (auto-detected from your key) | `claude-sonnet-4-5` |
| `risk_proceed_threshold` | Risk score below this → auto-proceed (no popup) | `30` |
| `risk_confirm_threshold` | Risk score above this → must type YES | `100` |
| `offline_mode` | Skip all LLM calls; use heuristic planner only | `false` |

### Risk levels at a glance

| Level | Example actions | What Arix does |
|-------|----------------|----------------|
| Low | Read file, list directory, web search | Auto-proceeds silently |
| Medium | Move file, browser click, git add | Shows plan, waits for OK |
| High | Delete files, send message, git commit | Shows plan + risk warning |
| Critical | Bulk delete, send to many recipients | Requires typing **YES** |

---

## 13. Troubleshooting

### "Module not found" / import errors
```bash
pip install -e .
```
Make sure your virtual environment is **activated** first (you should see `(.venv)` in your prompt).

---

### Server won't start — port already in use
```bash
# Windows — find and kill the process on port 5000
netstat -ano | findstr :5000
taskkill /PID <PID_FROM_ABOVE> /F

# macOS / Linux
lsof -ti:5000 | xargs kill -9
```

---

### AI not working — responses are generic or slow
1. Check your key is loaded:
   ```bash
   # Windows
   echo %ANTHROPIC_API_KEY%
   # macOS / Linux
   echo $ANTHROPIC_API_KEY
   ```
2. Make sure `.env` is saved in the project root folder
3. Verify you have credits/quota on your API account
4. Try offline mode as a test — add `"offline_mode": true` to `~/.arix/config.json`

---

### Bridge not connecting
- The Arix server must be running **before** you start the bridge
- For local: use `ws://` (not `wss://`)
- For Replit / HTTPS: use `wss://`
- Check the header badge — "Bridge: Off" means the bridge script isn't running

---

### Desktop automation not working (click/type does nothing)
- Make sure the bridge is running and shows **Bridge: On ✓**
- **macOS:** Go to System Settings → Privacy & Security → Accessibility → allow Terminal or Python
- **Windows:** Try running the bridge terminal as **Administrator**
- Move mouse to the **top-left corner** to reset the failsafe if something is stuck

---

### Browser (Playwright) errors
```bash
pip install playwright==1.49.1 playwright-stealth
playwright install chromium
```

---

### Integration not responding (Gmail, Notion, Slack…)
1. Double-check the env var is set in `.env` and the file is saved
2. Restart the server after editing `.env` — it loads on startup
3. Check the **Integrations panel** in the UI for a connection status indicator
4. For Google OAuth: all three vars must be present (`CLIENT_ID`, `CLIENT_SECRET`, `REFRESH_TOKEN`)

---

## Quick Start Checklist

```
 Core setup
 ─────────────────────────────────────────────────────
 [ ] Python 3.11+ installed and on PATH
 [ ] Project folder opened in a terminal
 [ ] Virtual environment created (.venv) and activated
 [ ] pip install -e .  completed with no errors
 [ ] .env.example copied to .env
 [ ] API key pasted into .env (Anthropic / OpenAI / Gemini)
 [ ] python main.py running — no errors in terminal
 [ ] http://localhost:5000 opens in browser
 [ ] Onboarding completed (name, timezone, style)

 Optional features
 ─────────────────────────────────────────────────────
 [ ] pip install pyautogui pillow websockets     ← desktop control
 [ ] python local_bridge/bridge_agent.py running ← bridge connected
 [ ] playwright install chromium                 ← browser automation
 [ ] Integration credentials added to .env       ← Gmail, Notion, etc.
```

---

*Arix v8.2 — Personal AI Computer-Control Agent*
*For architecture details see `README.md` · For API docs see `docs/`*
