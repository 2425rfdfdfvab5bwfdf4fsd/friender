# Arix Configuration Reference

Arix stores its configuration in `~/.arix/config.json` (mode 0600). The file is created on first run with safe defaults.

## Environment Variables

These take priority over config file values.

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `GEMINI_API_KEY` | Google Gemini API key | — |
| `AI_INTEGRATIONS_ANTHROPIC_API_KEY` | Replit-managed Anthropic key (auto-set) | — |
| `Arix_ADMIN_TOKEN` | Bearer token for API auth. When set, all REST + WS require it. | — (disabled) |
| `Arix_ALLOWED_ORIGINS` | Comma-separated WebSocket origin hostnames | — (allow all) |
| `WHATSAPP_WEBHOOK_SECRET` | HMAC secret for Twilio WhatsApp webhook signatures | — |
| `TWILIO_ACCOUNT_SID` | Twilio account SID (WhatsApp integration) | — |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | — |
| `TWILIO_WHATSAPP_FROM` | Your Twilio WhatsApp number (`whatsapp:+1...`) | — |
| `WHATSAPP_ALLOWED_NUMBERS` | Comma-separated E.164 numbers allowed to send commands | — |

## Config File Fields (`~/.arix/config.json`)

### LLM

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `str` | `"anthropic"` | LLM provider: `anthropic`, `openai`, `gemini` |
| `model` | `str` | `"claude-opus-4-5"` | Model name for planning |
| `sanitizer_provider` | `str` | `"anthropic"` | Provider for content gateway sanitizer |
| `sanitizer_model` | `str` | `"claude-haiku-4-5"` | Model for sanitizer (use a cheaper/faster model) |
| `offline_mode` | `bool` | `false` | Skip all LLM calls; use heuristic planner only |

### Security

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allowed_path_prefixes` | `list[str]` | `[$HOME, $CWD, /tmp]` | Absolute paths tools are allowed to access |
| `grant_ttl_seconds` | `int` | `300` | Capability grant time-to-live (seconds) |
| `require_auth` | `bool` | `false` | Require `Arix_ADMIN_TOKEN` for all requests |
| `allowed_ws_origins` | `list[str]` | `[]` | Allowed WS origin hostnames. Empty = allow all |
| `api_rate_limit_per_minute` | `int` | `120` | Max HTTP API requests per IP per minute |
| `ws_command_rate_limit_per_minute` | `int` | `20` | Max WS commands per connection per minute |
| `tool_timeout_seconds` | `int` | `60` | Per-tool execution timeout (seconds) |

### Risk Thresholds

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `risk_proceed_threshold` | `float` | `30.0` | Below this risk score: auto-proceed |
| `risk_confirm_threshold` | `float` | `100.0` | Above this: require explicit YES confirmation |
| `max_steps` | `int` | `30` | Maximum steps allowed in a single plan |
| `max_file_egress_bytes` | `int` | `32768` | Max bytes of file content sent to LLM per step |

### Audit Log

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `audit_log_path_mode` | `str` | `"full"` | `"full"`, `"basename"`, or `"none"` |
| `audit_log_retention_days` | `int` | `90` | Days to retain audit log entries |
| `audit_log_encryption_enabled` | `bool` | `false` | Encrypt audit log entries (experimental) |

### Browser

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `browser_headless` | `bool` | `true` | Run browser in headless mode |

### Archive / Zip

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `archive_max_files` | `int` | `1000` | Max files in a zip |
| `archive_max_bytes` | `int` | `500000000` | Max uncompressed bytes (500 MB) |
| `archive_max_ratio` | `float` | `100.0` | Max zip decompression ratio (zip-bomb protection) |
| `archive_allow_symlinks` | `bool` | `false` | Allow symlinks in archives |
| `archive_allow_hardlinks` | `bool` | `false` | Allow hardlinks in archives |

### UX

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dry_run_mode` | `bool` | `false` | Preview plan without executing by default |
| `show_egress_notices` | `bool` | `true` | Show notices before sending data to LLM |

## Editing Config

Via Arix web UI: open **Settings** panel.

Via CLI:
```bash
pacca init          # interactive wizard
```

Via file (be careful with JSON syntax):
```bash
nano ~/.arix/config.json
chmod 600 ~/.arix/config.json
```

## Safe Deployment Checklist

```bash
# 1. Set a strong auth token
export Arix_ADMIN_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Restrict WebSocket origins to your domain
export Arix_ALLOWED_ORIGINS=yourdomain.com

# 3. Verify setup
pacca doctor

# 4. Start server
pacca serve
```
