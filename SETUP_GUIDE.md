# Arix — Setup Guide

> Your personal AI digital employee. Give it tasks in plain English — it plans, acts, and reports back.

---

## The Fastest Way — Launcher Scripts

Six double-clickable files do everything for you. No command-line knowledge required.

| File | Platform | What it does | When to use |
|------|----------|-------------|-------------|
| `setup.bat` | Windows | Installs everything + creates `.env` | **Once**, on first run |
| `launch.bat` | Windows | Starts Arix + opens browser | **Every day** |
| `launch_bridge.bat` | Windows | Connects desktop control (mouse & keyboard) | When you want Arix to control your PC |
| `setup.sh` | Mac / Linux | Installs everything + creates `.env` | **Once**, on first run |
| `launch.sh` | Mac / Linux | Starts Arix + opens browser | **Every day** |
| `launch_bridge.sh` | Mac / Linux | Connects desktop control | When you want Arix to control your PC |

**First time:**

- **Windows:** Double-click `setup.bat` → then `launch.bat`
- **Mac/Linux:** Run `bash setup.sh` in a terminal → then `bash launch.sh`

**Every day after that:**

- **Windows:** Double-click `launch.bat`
- **Mac/Linux:** `bash launch.sh`

---

## Table of Contents

1. [Requirements](#1-requirements)
2. [Install Python](#2-install-python)
3. [Download & Install Arix](#3-download--install-arix)
4. [AI Provider Options](#4-ai-provider-options)
5. [Configure Your .env File](#5-configure-your-env-file)
6. [Start the Server](#6-start-the-server)
7. [Local Bridge (Desktop Control)](#7-local-bridge-desktop-control)
8. [Integrations](#8-integrations-optional)
9. [Example Commands](#9-example-commands)
10. [Configuration Reference](#10-configuration-reference)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Requirements

| What | Minimum |
|------|---------|
| OS | Windows 10/11 · macOS 12+ · Ubuntu 20.04+ / Debian 11+ |
| Python | **3.11** or newer |
| RAM | 512 MB free |
| Internet | Required for cloud AI features (not needed for local Ollama) |

---

## 2. Install Python

### Windows

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and download **Python 3.11** or newer.
2. Run the installer. **Critical:** on the first screen tick **"Add Python to PATH"**.
3. Verify: open Command Prompt and run `python --version` (should show 3.11+).

### macOS

```bash
# With Homebrew (recommended)
brew install python@3.11

# Without Homebrew — download from python.org
```

### Linux (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

---

## 3. Download & Install Arix

### Step 1 — Get the files

**Option A — ZIP from Replit (easiest)**

Download the ZIP from Replit and unzip it to a folder of your choice (e.g. `C:\Users\You\arix` or `~/arix`).

**Option B — Git clone**

```bash
git clone https://github.com/your-username/arix.git
cd arix
```

### Step 2 — Run setup

**Windows:** Double-click `setup.bat`

**Mac / Linux:**
```bash
cd /path/to/arix
bash setup.sh
```

The setup script will:
- Create a Python virtual environment (`.venv`)
- Install all dependencies from `requirements.txt`
- Install Playwright's Chromium browser (~130 MB)
- Create your `.env` config file
- Open `.env` for you to add an API key (optional — see below)
- Offer to install `pyautogui` for desktop control

---

## 4. AI Provider Options

Arix works with any of these. **You don't need to pay for anything to get started.**

### Option A — Local Ollama *(free, fully private, no API key needed)*

If you have [Ollama](https://ollama.com) installed and running, Arix automatically detects it and uses it — **no configuration needed at all.**

```bash
# Install Ollama from https://ollama.com
# Then pull a model (do this once):
ollama pull llama3.2        # fast, good quality (~2 GB)
# or: ollama pull mistral, gemma2, qwen2.5, etc.

# Then just run Arix — it finds Ollama automatically:
bash launch.sh
```

The terminal shows: `🦙 No cloud key found — using local Ollama (llama3.2) for planning`

Your prompts never leave your PC. No API costs.

---

### Option B — Anthropic Claude *(recommended for best results)*

1. Go to **[console.anthropic.com](https://console.anthropic.com)** → sign up / log in
2. Click **API Keys** → **Create Key** (starts with `sk-ant-...`)
3. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-your-key-here`

---

### Option C — OpenAI GPT-4

1. Go to **[platform.openai.com](https://platform.openai.com)** → API Keys → Create new secret key
2. Add to `.env`: `OPENAI_API_KEY=sk-your-key-here`

> An OpenAI key also enables **vector memory search** — Arix finds similar past tasks using AI embeddings.

---

### Option D — Google Gemini *(free tier available)*

1. Go to **[aistudio.google.com](https://aistudio.google.com)** → Get API Key
2. Add to `.env`: `GEMINI_API_KEY=your-key-here`

---

### Option E — Demo mode *(no AI, no Ollama)*

Run Arix with no keys at all — it uses a built-in heuristic planner for common tasks (file management, system info, etc.). Good for exploring the UI before committing to a provider.

---

## 5. Configure Your .env File

### Create it

**Windows:** `setup.bat` does this automatically, or run:
```cmd
copy .env.example .env
notepad .env
```

**Mac / Linux:** `setup.sh` does this automatically, or run:
```bash
cp .env.example .env
nano .env     # or: code .env / open .env
```

### Minimal .env (single AI key)

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Full .env reference

```env
# ── AI Providers (set at least one; or use local Ollama with no key) ──────────
ANTHROPIC_API_KEY=sk-ant-...          # Claude — default, best results
# OPENAI_API_KEY=sk-...              # GPT-4 + enables vector memory
# GEMINI_API_KEY=...                 # Google Gemini (free tier available)
# GROQ_API_KEY=...                   # Groq (very fast, free tier)

# ── Security (recommended if others can access your network) ──────────────────
# Arix_ADMIN_TOKEN=your-secret-token
# Generate one: python -c "import secrets; print(secrets.token_urlsafe(32))"

# ── Integrations (all optional — add only what you need) ─────────────────────
# Gmail / Drive / Calendar:  see Section 8 below for how to obtain credentials
# GMAIL_CLIENT_ID=...
# GMAIL_CLIENT_SECRET=...
# GMAIL_REFRESH_TOKEN=...
# NOTION_API_KEY=secret_...
# SLACK_BOT_TOKEN=xoxb-...
# TRELLO_API_KEY=...
# TRELLO_API_TOKEN=...
# SPOTIFY_CLIENT_ID=...
# SPOTIFY_CLIENT_SECRET=...
# YOUTUBE_API_KEY=...
```

> `.env` is already in `.gitignore` — it won't be accidentally uploaded to GitHub.

---

## 6. Start the Server

**Windows:** Double-click `launch.bat`

**Mac / Linux:**
```bash
bash launch.sh
```

**Manual (any OS):**
```bash
# Activate venv first:
source .venv/bin/activate      # Mac/Linux
.venv\Scripts\activate         # Windows

python main.py
```

Expected output:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5000
```

Open **http://localhost:5000** in your browser.

On first visit you'll see the **onboarding screen** — enter your name, timezone, and preferred style. This personalises how Arix talks to you.

### To stop

Press **Ctrl+C** in the terminal window.

---

## 7. Local Bridge (Desktop Control)

The Local Bridge gives Arix mouse and keyboard control over your PC — clicking buttons, typing text, reading the screen — like a human would.

| Without bridge | With bridge |
|----------------|-------------|
| File management, web browsing, Gmail, Notion, Slack, code… | Everything + click inside any app, fill forms, control OBS Studio, use TikTok/Instagram, type anywhere |

### Setup

1. Make sure the **Arix server is already running** (`launch.bat` or `launch.sh`)
2. Open a **second terminal** window
3. Run the bridge:

**Windows:** Double-click `launch_bridge.bat`

**Mac / Linux:**
```bash
bash launch_bridge.sh
```

**Manual:**
```bash
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
python local_bridge/bridge_agent.py --server ws://localhost:5000/ws/bridge
```

Expected output:
```
╔══════════════════════════════════════════╗
║   Arix Local Bridge Agent               ║
║   Server : ws://localhost:5000/ws/bridge ║
╚══════════════════════════════════════════╝
Connected to Arix server ✓
```

The header badge in the browser changes from **Bridge: Off** to **Bridge: On ✓**.

### Connecting to a cloud-hosted Arix (Replit)

```bash
python local_bridge/bridge_agent.py --server wss://your-app.replit.app/ws/bridge
```

### macOS note

Desktop automation requires **Accessibility permission**. Go to:
**System Settings → Privacy & Security → Accessibility** → add your terminal app (Terminal, iTerm2, etc.).

### Safety

- **Failsafe:** Move mouse to the **top-left corner** to immediately stop all automation.
- Press **Ctrl+C** in the bridge terminal to disconnect.

---

## 8. Integrations (Optional)

Add these lines to your `.env` and restart the server. Arix auto-detects which services are configured.

---

### Gmail (5 tools)

*Read, search, send, delete emails.*

1. [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services** → Enable **Gmail API**
2. Create **OAuth 2.0 Client ID** (Application type: Desktop App)
3. Download the JSON, run the OAuth flow to get a refresh token

```env
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

---

### Google Drive (4 tools)

*List, read, search, upload files.*

Same Google Cloud project as Gmail — just also enable the Drive API.

```env
GOOGLE_DRIVE_CLIENT_ID=...
GOOGLE_DRIVE_CLIENT_SECRET=...
GOOGLE_DRIVE_REFRESH_TOKEN=...
```

---

### Google Calendar (3 tools)

*List, create, delete events.*

Same project — enable Calendar API.

```env
GOOGLE_CALENDAR_CLIENT_ID=...
GOOGLE_CALENDAR_CLIENT_SECRET=...
GOOGLE_CALENDAR_REFRESH_TOKEN=...
```

---

### Notion (4 tools)

*Search, read, create, append to pages.*

1. [notion.so/my-integrations](https://www.notion.so/my-integrations) → **New Integration** → copy the Internal Integration Token

```env
NOTION_API_KEY=secret_your-notion-token-here
```

---

### Slack (4 tools)

*Send messages, list channels, search.*

1. [api.slack.com/apps](https://api.slack.com/apps) → **Create App** → **From Scratch**
2. **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `channels:read`, `channels:history`, `search:read`
3. Install to workspace → copy **Bot User OAuth Token**

```env
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
```

---

### Trello (4 tools)

*List boards, create cards, manage lists.*

1. [trello.com/app-key](https://trello.com/app-key) → copy **API Key**, generate **Token**

```env
TRELLO_API_KEY=your-trello-api-key
TRELLO_API_TOKEN=your-trello-token
```

---

### Spotify (3 tools)

*Search music, current track, play/pause.*

1. [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → **Create App** → copy Client ID + Secret

```env
SPOTIFY_CLIENT_ID=your-client-id
SPOTIFY_CLIENT_SECRET=your-client-secret
```

---

### YouTube (3 tools)

*Search videos, get video info, search channels.*

1. [console.cloud.google.com](https://console.cloud.google.com) → Enable **YouTube Data API v3** → create **API Key**

```env
YOUTUBE_API_KEY=your-youtube-api-key
```

---

### WhatsApp (1 tool)

*Send messages.*

1. [twilio.com](https://www.twilio.com) → enable **WhatsApp Sandbox** → copy Account SID + Auth Token

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_RECIPIENT=whatsapp:+1your-number
```

---

## 9. Example Commands

Type in plain English in the browser terminal:

### Files & System
```
Delete temp files from my PC
Organize my Downloads folder by file type
Find all PDFs in my Documents folder
Zip the project folder and save it to Desktop
Free up disk space and give me a report
Compare the two config files and show differences
Copy text from my clipboard and reformat it
```

### Web & Research
```
Search the web for the best Python courses and save results to a file
Summarize the article at https://example.com/article
Download the file at https://example.com/report.pdf
Fetch the GitHub API and show my latest repos
```

### Apps & Desktop  *(requires Local Bridge)*
```
Open TikTok and go to the upload page
Open OBS Studio and start recording
Open Instagram and go to Reels
Open LinkedIn and check my messages
Open Notepad and type a quick note
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
Create a Trello card "Review PRs" in the To Do list
```

### Code & AI
```
Generate a Python script that renames files by date
Explain what this code does
Analyze the quality of main.py
Run this snippet and show the output
```

### Multi-step Goals
```
Research the top 5 cloud storage services and create a comparison spreadsheet
Read my latest unread emails and create a task list in Notion
Clean up my PC, free disk space, and send me a summary
Send a WhatsApp message to John saying I'll be 10 minutes late
```

---

## 10. Configuration Reference

Config file: `~/.arix/config.json` (created automatically on first run). Most settings are also editable from the **Settings panel** inside the browser UI.

| Setting | What it does | Default |
|---------|--------------|---------|
| `provider` | AI provider: `anthropic`, `openai`, `gemini`, `ollama`, `groq`… | `anthropic` |
| `model` | Model name (auto-selected from your key) | `claude-opus-4-5` |
| `risk_proceed_threshold` | Risk score below this → auto-proceed | `30` |
| `risk_confirm_threshold` | Risk score above this → must type YES | `100` |
| `offline_mode` | Skip all LLM calls; heuristic planner only | `false` |
| `browser_headless` | Run Playwright without a visible window | `true` |
| `tool_timeout_seconds` | Kill a tool call after this many seconds | `60` |

### Risk levels

| Level | Example | Behaviour |
|-------|---------|-----------|
| Low | Read file, web search | Auto-proceeds silently |
| Medium | Move file, browser click, git add | Shows plan, waits for OK |
| High | Delete file, send message, git commit | Shows plan + risk warning |
| Critical | Bulk delete, send to many recipients | Requires typing **YES** |

---

## 11. Troubleshooting

### "Module not found" / import errors

Activate the virtual environment first, then reinstall:

```bash
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

---

### "python is not recognized" (Windows)

Python is not on your PATH. Re-run the installer and tick **"Add Python to PATH"**, or use `py -3.11` instead of `python`.

---

### Port 5000 already in use

**Mac/Linux:**
```bash
lsof -i :5000
kill -9 <PID>
```

**Windows:**
```cmd
netstat -ano | findstr :5000
taskkill /PID 12345 /F
```

---

### AI not working (generic or no responses)

1. Check the key is loaded:
   - Mac/Linux: `echo $ANTHROPIC_API_KEY`
   - Windows: `echo %ANTHROPIC_API_KEY%`

   If blank, the `.env` file isn't loading — make sure it's in the same folder as `main.py`.

2. Check you have credits/quota on your provider's dashboard.

3. **Try local Ollama:** install Ollama, run `ollama pull llama3.2`, start Arix with no keys — it auto-detects Ollama.

---

### Ollama not being detected

Make sure Ollama is **running** (not just installed):
```bash
ollama serve        # starts the Ollama server (keep this running)
ollama list         # should show your downloaded models
```

Then restart Arix — it probes `localhost:11434` at startup.

---

### Virtual environment issues (Mac/Linux)

```bash
# If venv creation fails with "ensurepip" error:
sudo apt install python3.11-venv   # Ubuntu/Debian

# If activation fails:
source .venv/bin/activate
```

**PowerShell execution policy (Windows):**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Browser (Playwright) errors

```bash
python -m playwright install chromium
```

---

### Bridge not connecting

- The **Arix server must be running first** before you start the bridge
- Use `ws://` for local connections, `wss://` for cloud/Replit
- Check the browser header: **Bridge: Off** = bridge not running

---

### macOS: desktop automation does nothing

Go to **System Settings → Privacy & Security → Accessibility** and add your terminal app to the allowed list.

---

### Integration not responding (Gmail, Notion, Slack…)

1. Confirm the variable is in `.env` with no extra spaces or quotes
2. **Restart the server** — `.env` is only read at startup
3. Open the **Integrations panel** in the browser UI for live status
4. For Google services: all three variables must be set (`CLIENT_ID`, `CLIENT_SECRET`, `REFRESH_TOKEN`)

---

## Quick Start Checklist

```
Core setup
─────────────────────────────────────────────────────────────
[ ] Python 3.11+ installed — python --version confirms it
[ ] Ran setup.bat (Windows) or bash setup.sh (Mac/Linux)
[ ] .env file has at least one AI key  — OR — Ollama is running
[ ] Ran launch.bat (Windows) or bash launch.sh (Mac/Linux)
[ ] http://localhost:5000 opens in browser
[ ] Onboarding completed (name, timezone, style)

Optional features
─────────────────────────────────────────────────────────────
[ ] Ollama installed + model pulled   ← free local AI, no key needed
[ ] playwright install chromium       ← browser automation
[ ] launch_bridge.bat / launch_bridge.sh running  ← desktop control
[ ] Integration credentials added to .env  ← Gmail, Notion, Slack…
```

---

*Arix v9.3 — Personal AI Computer-Control Agent*
*100 tools · 20 domains · 8 integrations · Ollama auto-fallback*
*Windows 10/11 · macOS 12+ · Ubuntu 20.04+*
