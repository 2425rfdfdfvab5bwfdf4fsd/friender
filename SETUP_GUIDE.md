# Arix — Personal AI Digital Employee
## Complete Setup Guide

---

## What is Arix?

Arix is your personal AI digital employee that runs on your computer. You give it tasks in plain language — like *"delete temp files from my PC"*, *"open TikTok and go to upload"*, or *"start recording on OBS Studio"* — and it figures out the steps, executes them automatically, and reports back when done.

It can open and control any app on your computer, manage files, browse the web, send messages, fill forms, and complete multi-step workflows on your behalf. For sensitive actions (deleting files, sending messages, making purchases), it always asks for your approval first.

---

## Requirements

| Item | Minimum Version |
|------|----------------|
| Python | 3.11 or newer |
| pip | latest |
| Internet connection | Required for AI features |
| Operating System | Windows 10/11, macOS 12+, or Ubuntu 20.04+ |

---

## Step 1 — Install Python

### Windows
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download Python **3.11** or newer
3. Run the installer — **check "Add Python to PATH"** before clicking Install
4. Open **Command Prompt** and verify:
   ```cmd
   python --version
   ```

### macOS
```bash
# Install Homebrew first if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Then install Python
brew install python@3.11
```

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.11 python3.11-pip python3.11-venv -y
```

---

## Step 2 — Download Arix

### Option A — Clone from Git (recommended)
```bash
git clone https://github.com/your-username/pacca.git
cd pacca
```

### Option B — Download ZIP
1. Download the project ZIP from Replit or GitHub
2. Unzip it to a folder, e.g. `C:\Users\YourName\pacca` or `~/pacca`
3. Open a terminal and navigate into the folder:
   ```bash
   cd ~/pacca      # macOS/Linux
   cd C:\Users\YourName\pacca   # Windows
   ```

---

## Step 3 — Create a Virtual Environment (Recommended)

A virtual environment keeps Arix's dependencies separate from your system Python.

```bash
# Create the environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

You should see `(.venv)` at the start of your terminal prompt when it's active.

---

## Step 4 — Install Dependencies

```bash
pip install -e .
```

This installs all required packages listed in `pyproject.toml` including FastAPI, the Anthropic SDK, document tools, and more.

### Optional — Browser automation (for web scraping and form filling)
```bash
pip install playwright playwright-stealth
playwright install chromium
```

---

## Step 5 — Get an AI API Key

Arix needs an AI provider to understand your commands and plan tasks. Choose one:

### Option A — Anthropic Claude (Recommended, best results)
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up / log in
3. Click **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-...`)

### Option B — OpenAI (GPT-4)
1. Go to [platform.openai.com](https://platform.openai.com)
2. Sign up / log in
3. Go to **API Keys** → **Create new secret key**
4. Copy the key (starts with `sk-...`)

### Option C — Google Gemini (Free tier available)
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API key**
3. Copy the key

---

## Step 6 — Set Your API Key

### Windows (Command Prompt — lasts until you close the window)
```cmd
set ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Windows (Permanent — saved to your user environment)
1. Press **Win + R**, type `sysdm.cpl`, press Enter
2. Click **Advanced** → **Environment Variables**
3. Under **User variables**, click **New**
4. Name: `ANTHROPIC_API_KEY`
5. Value: `sk-ant-your-key-here`
6. Click OK

### macOS / Linux (lasts until you close the terminal)
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### macOS / Linux (Permanent — add to your shell profile)
```bash
# For bash users:
echo 'export ANTHROPIC_API_KEY=sk-ant-your-key-here' >> ~/.bashrc
source ~/.bashrc

# For zsh users (default on modern macOS):
echo 'export ANTHROPIC_API_KEY=sk-ant-your-key-here' >> ~/.zshrc
source ~/.zshrc
```

> **Note:** Replace `ANTHROPIC_API_KEY` with `OPENAI_API_KEY` or `GEMINI_API_KEY` if you chose a different provider.

---

## Step 7 — Start the Arix Server

```bash
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Now open your browser and go to:
```
http://localhost:5000
```

Arix's chat interface will load. You'll see the onboarding screen on your first visit — enter your name, timezone, and communication style.

---

## Step 8 — Set Up the Local Bridge (for full desktop control)

The **Local Bridge** lets Arix control your physical desktop — clicking buttons, typing text, taking screenshots, and using any app installed on your PC, just like you would.

> **Without the bridge:** Arix can manage files, browse the web, and open apps via web browser.
> **With the bridge:** Arix can also click inside apps, fill forms, control OBS Studio, navigate TikTok/Instagram, and do anything you can do with a mouse and keyboard.

### Install bridge dependencies (one time only)

```bash
pip install pyautogui pillow websockets
```

### Run the bridge

Open a **second terminal window** (keep the server running in the first), then:

```bash
cd pacca
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

The **Bridge: Off** badge in the Arix header will turn green: **Bridge: On ✓**

### Safety tip
- Move your mouse to the **top-left corner** of your screen at any time to instantly stop all desktop automation (pyautogui failsafe).
- Press `Ctrl+C` in the bridge terminal to disconnect at any time.

---

## Step 9 — Using Arix as a Digital Employee

Once everything is running, you can give Arix tasks like a real employee. Here are examples:

### File & System Tasks
| Say this... | Arix will... |
|------------|--------------|
| `Delete temp files from my PC` | Scan, show what it found, ask approval, then clean up |
| `Free up disk space` | Check usage, clean temp files, report results |
| `Organize my Downloads folder` | Create subfolders by type, move files |
| `Backup my Documents to ~/Backup` | Copy all documents to backup folder |
| `Find all PDF files in my Downloads` | Search and list every PDF |

### App Control
| Say this... | Arix will... |
|------------|--------------|
| `Open TikTok and go to upload` | Launch TikTok in browser, navigate to upload page |
| `Open Instagram and go to reels` | Open Instagram, navigate to Reels section |
| `Open WhatsApp and go to messages` | Open WhatsApp Web, open messages |
| `Open LinkedIn and check my messages` | Open LinkedIn, go to messaging inbox |
| `Open Microsoft Excel` | Launch Excel on your PC |
| `Open Chrome and search for Python tutorials` | Open Chrome, search Google |

### OBS Studio
| Say this... | Arix will... |
|------------|--------------|
| `Start recording on OBS` | Launch OBS Studio, click Start Recording |
| `Stop recording` | Click Stop Recording in OBS |
| `Start streaming on OBS` | Launch OBS, click Start Streaming |
| `Stop streaming` | Click Stop Streaming |

### Web & Research
| Say this... | Arix will... |
|------------|--------------|
| `Search the web for iPhone 16 Pro reviews and save to a file` | Search, collect results, create a file |
| `Download the file at https://example.com/report.pdf` | Download and save it |
| `What's the latest news about AI?` | Search and summarize |

### Multi-Step Goals (autonomous mode)
| Say this... | Arix will... |
|------------|--------------|
| `Research the top 5 cloud storage services and create a comparison spreadsheet` | Research online → create Excel file |
| `Open TikTok, go to messages, and check new messages` | Multi-step app navigation |
| `Send a WhatsApp message to John saying I'll be late` | Open WhatsApp → find John → type message (asks approval before sending) |
| `Clean up my PC and show me how much space was freed` | Full cleanup workflow with report |

---

## Sensitive Actions — Approval Required

Arix **always asks for your approval** before doing anything that can't be easily undone. A confirmation dialog will pop up showing:

- What action is about to happen
- The risk level (low / medium / high / critical)
- A step-by-step list of exactly what will execute
- **Approve** / **Cancel** buttons

For critical actions (like bulk file deletion), you must type **YES** before it proceeds.

**Sensitive actions that trigger approval:**
- Deleting files or folders
- Sending messages (WhatsApp, email)
- Publishing or posting content (Instagram, TikTok, LinkedIn)
- Making purchases
- Changing system settings
- Git commits and pushes

---

## Configuration

Arix stores its config at `~/.pacca/config.json`. You can edit this file directly or change settings through the **Settings** panel in the UI.

### Key settings

| Setting | Description | Default |
|---------|-------------|---------|
| `provider` | AI provider: `anthropic`, `openai`, `gemini` | `anthropic` |
| `model` | Model name (auto-detected from API key) | `claude-sonnet-4-5` |
| `risk_proceed_threshold` | Risk score below this = auto-proceed | `30` |
| `risk_confirm_threshold` | Risk score above this = require YES | `100` |
| `offline_mode` | Run without any API key (demo mode) | `false` |

---

## Environment Variables Reference

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic (Claude) API key |
| `OPENAI_API_KEY` | Your OpenAI (GPT) API key |
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `Arix_BRIDGE_TOKEN` | Optional security token for the bridge connection |

---

## Running Arix on Replit (No Local Install Needed)

If you're using the Replit-hosted version:

1. The server is already running — open the **Webview** tab in Replit
2. To connect the local bridge from your computer:
   ```bash
   pip install pyautogui pillow websockets
   python local_bridge/bridge_agent.py \
     --server wss://your-repl-name.replit.app/ws/bridge \
     --token YOUR_BRIDGE_TOKEN
   ```
3. Find your Replit app URL in the Replit webview address bar

---

## Troubleshooting

### "Module not found" error
```bash
pip install -e .
```

### Server won't start (port already in use)
```bash
# Kill whatever is using port 5000
# Windows:
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# macOS/Linux:
lsof -ti:5000 | xargs kill -9
```

### Bridge not connecting
- Make sure the Arix server is running first
- Check the server URL — use `ws://` for local, `wss://` for HTTPS/Replit
- If you see "Bridge: Off" in the header, the bridge script is not running

### AI features not working (responses are generic)
- Check your API key is set correctly: `echo $ANTHROPIC_API_KEY` (macOS/Linux) or `echo %ANTHROPIC_API_KEY%` (Windows)
- Make sure you have credits/quota on your API account
- Try running in demo mode first: set `offline_mode: true` in `~/.pacca/config.json`

### Desktop automation not working (click/type commands fail)
- The local bridge must be running
- On macOS: go to **System Settings → Privacy & Security → Accessibility** and allow Terminal / Python
- On Windows: run the bridge as Administrator if needed
- Move mouse to top-left corner to reset if anything gets stuck

### Browser automation (Playwright) errors
```bash
pip install playwright playwright-stealth
playwright install chromium
```

---

## Quick Start Checklist

- [ ] Python 3.11+ installed
- [ ] Project downloaded / cloned
- [ ] Virtual environment created and activated
- [ ] `pip install -e .` completed
- [ ] API key obtained (Anthropic / OpenAI / Gemini)
- [ ] API key set as environment variable
- [ ] `python main.py` running — browser shows Arix interface
- [ ] Onboarding completed (name, timezone, style)
- [ ] *(Optional)* `pip install pyautogui pillow websockets` for desktop control
- [ ] *(Optional)* `python local_bridge/bridge_agent.py` running for full desktop automation
- [ ] *(Optional)* `playwright install chromium` for browser automation

---

## What Arix Can Control

| Category | Apps / Actions |
|----------|---------------|
| **Social Media** | TikTok, Instagram, WhatsApp, LinkedIn, Facebook, Twitter/X, Snapchat, Telegram, Discord, Reddit |
| **Productivity** | Gmail, Google Drive, Google Docs, Google Sheets, Google Calendar, Outlook, OneDrive, Notion, Trello |
| **Desktop Apps** | Microsoft Excel, Word, PowerPoint, OBS Studio, Chrome, Firefox, Edge, Spotify, VLC, VS Code, Zoom, Slack |
| **Files** | Create, read, move, copy, search, zip/unzip, delete (with approval), clean temp files |
| **System** | Monitor CPU/RAM/disk, list running apps, close apps, disk cleanup |
| **Browser** | Open URLs, search the web, extract page content, fill forms, click elements, download files |
| **Git** | Status, diff, add, commit (with approval) |
| **Documents** | Create/read Word (.docx) and Excel (.xlsx) files |

---

*Arix v8.x — Personal AI Computer-Control Agent*
