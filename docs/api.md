# Arix v9.5 — REST API Reference

## Authentication

When `Arix_ADMIN_TOKEN` is set, all endpoints (except `GET /` and `POST /webhook/whatsapp`) require:

```
Authorization: Bearer <Arix_ADMIN_TOKEN>
```

Returns `401 Unauthorized` if missing or wrong.

## Rate Limiting

Default: 120 requests/minute per IP. Configurable via `api_rate_limit_per_minute` in config.

Returns `429 Too Many Requests` with `Retry-After` header when exceeded.

---

## Status

### `GET /api/status`
Returns server status, LLM availability, tool count.

```json
{
  "version": "9.5.0",
  "provider": "gemini",
  "model": "gemini-2.0-flash-lite",
  "offline_mode": false,
  "llm_available": true,
  "llm_error": null,
  "tool_count": 100,
  "circuit_breaker": {"state": "closed", "failure_count": 0}
}
```

### `GET /api/cache/stats`
Returns live hit/miss statistics for both the LLM response cache and the tool result cache.

```json
{
  "response_cache": {
    "hits": 42,
    "misses": 18,
    "hit_rate": 0.7,
    "api_calls_saved": 42,
    "size": 12,
    "max_size": 1000
  },
  "tool_cache": {
    "hits": 15,
    "misses": 31,
    "hit_rate": 0.326,
    "size": 8,
    "cached_tools": ["list_directory", "system_monitor", "git_status", "..."]
  }
}
```

### `POST /api/cache/clear`
Flushes both the LLM response cache and the tool cache. Useful after changing provider/model or editing files that would make cached results stale.

```json
{ "cleared": true }
```

### `GET /api/tools`
Returns list of all registered tools with metadata.

```json
{
  "tools": [
    {
      "name": "list_directory",
      "domain": "file",
      "risk_level": "LOW",
      "reversible": true,
      "description": "List files in a directory"
    }
  ]
}
```

---

## Commands

### `POST /api/command`
Execute a command synchronously (returns after completion).

**Request:**
```json
{
  "command": "list my downloads folder",
  "dry_run": false
}
```

**Response:** stream of events or final result.

---

## Tasks

### `GET /api/tasks`
List recent task history.

### `DELETE /api/tasks/{task_id}`
Cancel a running task.

### `POST /api/tasks/{task_id}/confirm`
Respond to a pending confirmation gate.

```json
{
  "confirmation_id": "plan_risk",
  "response": "YES",
  "skip_steps": []
}
```

### `POST /api/tasks/{task_id}/undo`
Undo the last reversible operation.

---

## Memory

### `GET /api/memory`
Returns recent tasks and preferences.

Query params: `limit` (default 20), `domain` (optional filter).

### `GET /api/memory/search`
Semantic search over memory.

Query params: `q` (required), `top_k` (default 5).

### `POST /api/memory/preference`
Set a user preference.

```json
{"key": "default_editor", "value": "vim"}
```

### `GET /api/memory/export`
Export all episodic memory as JSON. Useful for backup.

**Response:** `Content-Type: application/json`

```json
{
  "version": "8.0.0",
  "exported_at": 1718400000.0,
  "episodic": [...]
}
```

### `POST /api/memory/import`
Import episodic memory from a previously exported JSON file.

**Request:** `Content-Type: application/json` — same format as export.

### `DELETE /api/memory/episodic/{id}`
Delete a specific episodic memory entry by its integer ID ("forget").

### `GET /api/memory/stats`
Returns memory statistics (counts by domain, size).

### `GET /api/memory/weekly`
Returns weekly usage summary.

### `POST /api/memory/compress`
Trigger background memory compression (summarize old episodic records).

---

## Audit

### `GET /api/audit`
Returns recent audit log entries.

Query params: `limit` (default 50).

### `GET /api/audit/verify`
Verify audit log HMAC chain integrity.

**Response:**
```json
{
  "valid": true,
  "entries_checked": 142,
  "first_broken_entry": null
}
```

---

## Workflows

### `GET /api/workflows`
List all saved workflows.

### `POST /api/workflows`
Create a new workflow.

```json
{
  "command": "list downloads and report",
  "steps": []
}
```

### `DELETE /api/workflows/{name}`
Delete a workflow by name.

### `POST /api/workflows/{name}/toggle`
Enable or disable a workflow.

```json
{"enabled": false}
```

### `POST /api/workflows/{name}/run`
Trigger a workflow immediately.

---

## WebSocket

### `WS /ws`

Connect to the terminal interface.

**If `Arix_ADMIN_TOKEN` is set**, send auth as first message:
```json
{"type": "auth", "token": "<Arix_ADMIN_TOKEN>"}
```

**Incoming message types:**
| Type | Description |
|------|-------------|
| `command` | Execute a command: `{"type":"command","data":{"command":"...","dry_run":false}}` |
| `confirm` | Respond to confirmation: `{"type":"confirm","data":{"task_id":"...","confirmation_id":"...","response":"YES"}}` |
| `cancel` | Cancel task: `{"type":"cancel","data":{"task_id":"..."}}` |
| `undo` | Undo last action: `{"type":"undo","data":{}}` |

**Outgoing event types:**
| Type | Description |
|------|-------------|
| `welcome` | Sent on connect with server info |
| `status` | Short status message |
| `plan` | Full plan preview with risk score |
| `executing` | Task started executing |
| `step_start` | Individual step beginning |
| `step_complete` | Step finished with result |
| `step_error` | Step failed with error |
| `confirmation_required` | Waiting for user input |
| `completed` | Task finished |
| `cancelled` | Task cancelled |
| `error` | Fatal error |
| `advisory` | Advisory answer (no tools executed) |

---

## Calendar

### `GET /api/calendar/events`
List calendar events.

### `POST /api/calendar/events`
Create a calendar event.

### `DELETE /api/calendar/events/{id}`
Delete a calendar event.

---

## Profile

### `GET /api/profile`
Returns user profile.

### `POST /api/profile`
Update user profile.

---

## System

### `GET /api/sysmon`
Returns system resource usage (CPU, memory, disk).

### `GET /api/morning-brief`
Returns the daily morning brief.
