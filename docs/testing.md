# Arix — Testing Guide

## Quick Start

```bash
# Install dev dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=pacca --cov-report=term-missing
```

## Test Modules

| Module | Count | What it covers |
|--------|-------|----------------|
| `test_url_safety` | 22 | URL blocklist: private IPs, metadata service, IPv6, schemes, credentials |
| `test_audit_email_redaction` | 4 | Email redaction in audit log entries |
| `test_used_grant_registry` | 4 | Grant replay prevention + SQLite persistence across restarts |
| `test_memory_wal` | 2 | SQLite WAL mode for MemoryManager |
| `test_plan_validator_urls` | 6 | Blocked URLs rejected by PlanValidator |
| `test_task_scope_run_code` | 2 | `run_code` present in `DOMAIN_TOOL_MAP["coding"]` |
| `test_config_new_fields` | 4 | v8.0 config fields have correct defaults |
| `test_config_atomic_save` | 3 | Atomic write-then-rename for config file |
| `test_local_text_redactor` | 14 | Redaction of API keys, passwords, PII, egress truncation |
| `test_capability_grant` | 12 | Grant issuance, signing, expiry, tamper detection, replay |
| `test_safe_resource_resolver` | 9 | Path safety, symlink escape, TOCTOU, credential path blocking |
| `test_risk_evaluator` | 8 | Risk scoring, gates, breakdown accuracy |

**Total: 90 tests** (all passing as of v8.0.0)

## Writing New Tests

### Mocking LLM Calls

All tests must mock LLM calls to avoid network dependencies and API costs:

```python
from unittest.mock import patch, AsyncMock

@patch("pacca.llm_client.LLMClient.plan", new_callable=AsyncMock)
async def test_something(mock_plan):
    mock_plan.return_value = [
        {"step_id": "s1", "tool": "list_directory",
         "args": {"path": "/tmp"}, "description": "List tmp"}
    ]
    # ... test code
```

### Mocking Filesystem

Use `tmp_path` (pytest built-in) for filesystem tests:

```python
def test_file_operation(tmp_path):
    target = tmp_path / "test.txt"
    target.write_text("hello")
    # ... test code
```

### Testing Security Properties

Security tests should verify **negative** cases (attacks are blocked), not just positive cases:

```python
def test_path_traversal_blocked(resolver, tmp_dir):
    scope = _make_scope([tmp_dir])
    traversal = os.path.join(tmp_dir, "../../../etc/passwd")
    resource = resolver.resolve(traversal, scope)
    assert not resource.allowed   # ← must be blocked

def test_replay_prevented(verifier, grant):
    verifier.verify(grant, ...)   # first use — ok
    with pytest.raises(CapabilityViolation):
        verifier.verify(grant, ...)  # second use — must raise
```

## Integration Tests

Integration tests live in `tests/test_integration.py` and cover end-to-end agent flows with mocked LLM:

```bash
python -m pytest tests/test_integration.py -v
```

Covered scenarios:
- Simple file listing task (low risk → auto-proceed)
- Blocked path traversal attempt
- Blocked private URL in plan
- Grant replay attack via registry
- High-risk approval gate
- Dry-run mode (no tools executed)
- Memory search

## Running Against the Live Server

For smoke tests against the running server (requires `httpx`):

```bash
python -m pytest tests/test_api.py -v -k "not ws"
```

WebSocket tests require the server to be running:

```bash
# Terminal 1
pacca serve

# Terminal 2
python -m pytest tests/test_api.py -v
```

## CI

A GitHub Actions workflow is provided in `.github/workflows/ci.yml`:

- Runs on Python 3.11
- Installs dev dependencies
- Runs `ruff check` (linting)
- Runs `mypy` (type checking)
- Runs `pytest` with coverage
- Fails if coverage drops below 60%

## Known Test Limitations

- Browser tool tests require Playwright to be installed and may be slow.
- `test_safe_resource_resolver.py::TestCredentialPathBlocking` skips if `~/.ssh` doesn't exist.
- `test_safe_resource_resolver.py::TestTOCTOU` may be flaky on very fast filesystems where mtime doesn't update between writes within the same millisecond.
