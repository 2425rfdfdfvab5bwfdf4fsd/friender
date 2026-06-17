# Arix — Windows Setup Guide

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

Already have Python 3.11+ installed? Here's the fastest path. Open **Command Prompt** and run:

```cmd
cd C:\Users\YourName\Downloads\friender

rmdir /s /q .venv
py -3.11 -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

copy .env.example .env
```

Open `.env` in Notepad, paste your `ANTHROPIC_API_KEY`, save, then:

```cmd
python main.py
```

Open **http://localhost:5000** in your browser.

---

## 2. Requirements

| What | Minimum |
|------|---------|
| Windows | **Windows 10** (build 1903+) or **Windows 11** |
| Python | **3.11** or newer |
| pip | Latest (bundled with Python) |
| RAM | 512 MB free |
| Internet | Required for AI features |

---

## 3. Install Python

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and download the latest **Python 3.11** or **3.12** Windows installer.
2. Run the installer (`python-3.11.x-amd64.exe`).
3. **Critical:** On the first screen, tick **"Add Python to PATH"** before clicking Install Now.

   ![Add to PATH checkbox](https://www.python.org/static/img/python-logo.png)

4. Open a new **Command Prompt** and verify:

   ```cmd
   python --version
   ```

   You should see `Python 3.11.x` or higher. If you see an error, restart your PC and try again.

5. Alternatively, if you have multiple Python versions installed, use the Python Launcher:

   ```cmd
   py -3.11 --version
   ```

---

## 4. Download Arix

### Option A — ZIP download (easiest)

1. Download the ZIP from Replit and unzip it.
2. The unzipped folder will be named something like `friender` or `arix`.
3. Open **Command Prompt** inside that folder:

   ```cmd
   cd C:\Users\YourName\Downloads\friender
   ```

   Replace `YourName` and `friender` with your actual username and folder name.

### Option B — Git clone

If you have Git installed:

```cmd
git clone https://github.com/your-username/arix.git
cd arix
```

---

## 5. Install Dependencies

### Step 1 — Create a virtual environment

A virtual environment keeps Arix's packages separate from other Python projects on your PC.

```cmd
py -3.11 -m venv .venv
```

### Step 2 — Activate it

```cmd
.venv\Scripts\activate
```

Your prompt will change to show `(.venv)` at the start — this means it's active. **Every time you open a new terminal to run Arix, you must activate the venv first.**

### Step 3 — Install all packages

```cmd
pip install -r requirements.txt
```

This installs FastAPI, the Anthropic SDK, Playwright, document tools, and everything else Arix needs. It takes 1–3 minutes on first run.

### Step 4 — Optional extras

| Feature | Install command |
|---------|----------------|
| Desktop automation (mouse & keyboard control) | `pip install pyautogui` |
| Browser automation (already in requirements.txt) | `playwright install chromium` |

---

## 6. Configure Your API Key

Arix needs at least one AI provider key to understand and plan your tasks.

### Option A — Anthropic Claude *(recommended — best results)*

1. Go to **[console.anthropic.com](https://console.anthropic.com)** → sign up / log in.
2. Click **API Keys** → **Create Key**.
3. Copy the key — it starts with `sk-ant-...`.

### Option B — OpenAI GPT-4

1. Go to **[platform.openai.com](https://platform.openai.com)** → sign up / log in.
2. Go to **API Keys** → **Create new secret key**.
3. Copy the key — it starts with `sk-...`.

> **Bonus:** An OpenAI key also enables **vector memory search** — Arix can find similar past tasks using AI embeddings instead of just keyword matching.

### Option C — Google Gemini *(free tier available)*

1. Go to **[aistudio.google.com](https://aistudio.google.com)**.
2. Click **Get API key** and copy it.

> **No key at all?** Arix still runs in **demo mode** using its built-in heuristic planner — no API costs.

---

## 7. Set Up Your .env File

### Create the file

```cmd
copy .env.example .env
```

Then open it in Notepad (or VS Code):

```cmd
notepad .env
```

### Minimal .env (just paste your key)

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Full .env reference

```env
# ── AI Providers (set at least one) ──────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...        # Claude — default, best results
# OPENAI_API_KEY=sk-...            # GPT-4 + enables vector memory
# GEMINI_API_KEY=...               # Google Gemini

# ── Security (optional — recommended if others can reach your PC) ─────────────
# Protects all API endpoints with a Bearer token.
# Generate one by running: python -c "import secrets; print(secrets.token_urlsafe(32))"
# Arix_ADMIN_TOKEN=

# Comma-separated allowed WebSocket origins (blank = allow all, fine for local use)
# PACCA_ALLOWED_ORIGINS=localhost,127.0.0.1

# ── Runtime Tuning ────────────────────────────────────────────────────────────
# How many seconds before a tool call times out (default: 60)
# PACCA_TOOL_TIMEOUT=60

# ── Integrations (all optional — add only what you need) ──────────────────────
# See Section 10 for how to obtain each credential
```

> **Never share your `.env` file.** It contains your private API keys. It is already listed in `.gitignore` so it won't be accidentally uploaded to GitHub.

---

## 8. Start the Server

Make sure your virtual environment is activated (`(.venv)` shows in your prompt), then:

```cmd
python main.py
```

Expected output:

```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)
```

Open your browser and go to:

```
http://localhost:5000
```

On your first visit you'll see the **onboarding screen** — enter your name, timezone, and preferred communication style. This personalises how Arix talks to you.

### To stop the server

Press **Ctrl+C** in the Command Prompt window.

### To restart after a reboot

```cmd
cd C:\Users\YourName\Downloads\friender
.venv\Scripts\activate
python main.py
```

---

## 9. Local Bridge (Desktop Control)

The **Local Bridge** gives Arix mouse and keyboard control over your PC — clicking buttons, typing text, reading the screen — just like a human would.

| Without bridge | With bridge |
|----------------|-------------|
| File management, web browsing, integrations, code | Everything + click inside any app, fill forms, control OBS Studio, use TikTok/Instagram, type anywhere |

### Setup

**Step 1 — Install bridge dependency** *(one time only)*

With your venv activated:

```cmd
pip install pyautogui
```

**Step 2 — Run the bridge in a second Command Prompt window**

Keep `python main.py` running in your first window. Open a **second Command Prompt**, navigate to the project folder, activate the venv, then:

```cmd
cd C:\Users\YourName\Downloads\friender
.venv\Scripts\activate
python local_bridge/bridge_agent.py --server ws://localhost:5000/ws/bridge
```

You'll see:

```
╔══════════════════════════════════════════╗
║   Arix Local Bridge Agent               ║
║   Server : ws://localhost:5000/ws/bridge ║
╚══════════════════════════════════════════╝
Connected to Arix server ✓
```

The header badge in the browser changes from **Bridge: Off** to **Bridge: On ✓**.

### Connecting to a cloud-hosted Arix (Replit)

```cmd
python local_bridge/bridge_agent.py --server wss://your-app.replit.app/ws/bridge
```

### Safety features

- **Failsafe:** Move your mouse to the **top-left corner** of the screen at any time to immediately stop all desktop automation.
- **Disconnect:** Press `Ctrl+C` in the bridge terminal.
- **Tip:** If something goes wrong mid-task, slam the mouse to the top-left — automation halts instantly.
- **Admin token:** If you set `Arix_ADMIN_TOKEN` in `.env`, also pass `--token YOUR_TOKEN` when starting the bridge.

---

## 10. Integrations (Optional)

These connect Arix to external services. Add the relevant lines to your `.env` file and restart the server — Arix auto-detects which services are configured.

---

### Gmail

Read, search, send, and delete emails.

**Get credentials:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services** → **Credentials**
2. Enable the **Gmail API**
3. Create an **OAuth 2.0 Client ID** (Application type: Desktop App)
4. Download the JSON, run the OAuth flow to get a refresh token

```env
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

**What you can say:** *"Show my unread emails"*, *"Search Gmail for invoices"*, *"Send an email to…"*

---

### Google Drive

List, search, read, and upload files.

```env
GOOGLE_DRIVE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=your-client-secret
GOOGLE_DRIVE_REFRESH_TOKEN=your-refresh-token
```

*(Use the same Google Cloud project as Gmail — just also enable the Drive API.)*

---

### Google Calendar

List, create, and delete calendar events.

```env
GOOGLE_CALENDAR_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
GOOGLE_CALENDAR_REFRESH_TOKEN=your-refresh-token
```

*(Same Google Cloud project — enable the Calendar API.)*

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
3. Install to workspace → copy the **Bot User OAuth Token**

```env
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
```

---

### Trello

Manage boards, lists, and cards.

1. Go to [trello.com/app-key](https://trello.com/app-key) and copy your **API Key**
2. Generate a **Token** on the same page

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

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services**
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

Once Arix is running, type in plain English in the browser terminal:

### Files & System
```
Delete temp files from my PC
Organize my Downloads folder by file type
Find all PDFs in my Documents folder
Zip the project folder
Free up disk space and show me a report
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

Arix's config is stored at **`C:\Users\YourName\.arix\config.json`** and is created automatically on first run. You can also change most settings from the **Settings panel** inside the browser UI.

| Setting | What it does | Default |
|---------|--------------|---------|
| `provider` | Which AI to use: `anthropic`, `openai`, `gemini` | `anthropic` |
| `model` | Model name (auto-detected from your key) | `claude-sonnet-4-5` |
| `risk_proceed_threshold` | Risk score below this → auto-proceed silently | `30` |
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

### "Module not found" or import errors

Make sure your virtual environment is active (`(.venv)` in your prompt), then reinstall:

```cmd
pip install -r requirements.txt
```

---

### "python is not recognized as an internal or external command"

Python is not on your PATH. Either:
- Re-run the Python installer and tick **"Add Python to PATH"**
- Or use `py -3.11` instead of `python` in every command

---

### Internal Server Error at localhost:5000

This usually means the server started but hit an error processing your first request. Check the Command Prompt window running `python main.py` for the full error message. Common causes:

- Missing or malformed `.env` file
- A dependency wasn't installed — run `pip install -r requirements.txt` again
- Port 5000 is in use by another process (see next section)

---

### Server won't start — port already in use

Find and kill the process using port 5000:

```cmd
netstat -ano | findstr :5000
```

Note the PID number in the last column, then:

```cmd
taskkill /PID 12345 /F
```

Replace `12345` with the actual PID, then start `python main.py` again.

---

### AI not working — generic or no responses

1. Check your key is visible to the server:

   ```cmd
   echo %ANTHROPIC_API_KEY%
   ```

   If blank, the `.env` file isn't loading. Make sure it's in the project root folder (same folder as `main.py`).

2. Verify you have credits/quota on your API provider's dashboard.
3. Test offline mode — add `"offline_mode": true` to `C:\Users\YourName\.arix\config.json` to confirm the rest of the app is working.

---

### Virtual environment not activating

If you see `".venv\Scripts\activate" is not recognized`:

```cmd
py -3.11 -m venv .venv
```

Then try activating again. If PowerShell blocks it with an execution policy error:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run `.venv\Scripts\activate` again.

---

### Bridge not connecting

- The Arix server (`python main.py`) must be **running first** before you start the bridge
- Use `ws://` for local connections (not `wss://`)
- Use `wss://` only when connecting to a cloud/Replit-hosted server
- Check the browser header badge — **Bridge: Off** means the bridge script isn't running

---

### Desktop automation not working (click/type does nothing)

- Confirm the bridge terminal shows **Connected to Arix server ✓**
- Try running the bridge Command Prompt **as Administrator** (right-click → Run as administrator)
- Move the mouse to the **top-left corner** to reset the failsafe if automation is stuck

---

### Browser (Playwright) errors

```cmd
playwright install chromium
```

If `playwright` isn't recognised, run it via Python:

```cmd
python -m playwright install chromium
```

---

### Integration not responding (Gmail, Notion, Slack…)

1. Open `.env` and confirm the variable is present and has no extra spaces or quotes around the value.
2. **Restart the server** after editing `.env` — it only reads the file at startup.
3. Open the **Integrations panel** in the browser UI for a live connection status.
4. For Google services (Gmail, Drive, Calendar): all three variables must be set — `CLIENT_ID`, `CLIENT_SECRET`, and `REFRESH_TOKEN`.

---

## Quick Start Checklist

```
Core setup
─────────────────────────────────────────────────────────────
[ ] Python 3.11+ installed — python --version confirms it
[ ] Project folder opened in Command Prompt
[ ] py -3.11 -m venv .venv  completed
[ ] .venv\Scripts\activate  — prompt shows (.venv)
[ ] pip install -r requirements.txt  — no errors
[ ] copy .env.example .env  completed
[ ] API key pasted into .env and file saved
[ ] python main.py  running — "Application startup complete."
[ ] http://localhost:5000  opens in browser
[ ] Onboarding completed (name, timezone, style)

Optional features
─────────────────────────────────────────────────────────────
[ ] pip install pyautogui              ← desktop control
[ ] python local_bridge/bridge_agent.py running  ← bridge on
[ ] playwright install chromium        ← browser automation
[ ] Integration credentials added to .env  ← Gmail, Notion…
```

---

*Arix v8.2 — Personal AI Computer-Control Agent · Windows 10/11*
*For architecture details see `README.md` · For API docs see `docs/`*
