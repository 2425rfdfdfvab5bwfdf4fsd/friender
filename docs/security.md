# Security Policy — Arix v8.0

## Supported Versions

| Version | Supported |
|---------|-----------|
| 8.x     | ✅ Current |
| 7.x     | ⚠ Security fixes only until 2025-12 |
| < 7.0   | ❌ End of life |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Send a report to the maintainer privately. Include:

1. A description of the vulnerability and its impact
2. Steps to reproduce (proof-of-concept if possible)
3. Which version(s) are affected
4. Any suggested mitigations

You will receive an acknowledgement within **48 hours** and a status update within **7 days**.

## Security Model

Arix uses a layered defense-in-depth architecture:

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | `LocalTextRedactor` | Strips secrets/credentials before any LLM call |
| 2 | `TaskScope` | Freezes allowed tool set at parse time |
| 3 | `SafeResourceResolver` | Only authority that resolves file paths |
| 4 | `PlanValidator` | Enforces tool allowlist, path scope, URL blocklist |
| 5 | `CumulativePlanRiskEvaluator` | Scores full plan; gates on risk threshold |
| 6 | `CapabilityGrant` | HMAC-signed single-use token per tool call |
| 7 | `UsedGrantRegistry` | Persistent SQLite replay prevention |
| 8 | `RuntimeStepValidator` | Re-validates + TOCTOU check before each step |
| 9 | `AuditLogger` | Tamper-resistant, privacy-safe log (mode 0600) |

## Known Limitations

- **No sandbox isolation**: `run_code` executes in the host Python process via `exec()`.  
  Mitigation: `run_code` is locked behind `coding` TaskScope; grant requires explicit HIGH-risk confirmation.
- **WebSocket auth** requires `Arix_ADMIN_TOKEN` to be set. Without it the WS is unauthenticated.  
  Recommended: always set `Arix_ADMIN_TOKEN` in production.

## Security Checklist for Deployment

- [ ] Set `Arix_ADMIN_TOKEN` to a cryptographically random value (≥32 bytes)
- [ ] Set `Arix_ALLOWED_ORIGINS` to only your frontend's domain
- [ ] Serve behind TLS (HTTPS/WSS) — never expose plain HTTP
- [ ] Keep `~/.arix/audit.log` (mode 0600) on a persistent volume
- [ ] Rotate `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` if exposed
- [ ] Review `~/.arix/audit.log` regularly for anomalous patterns
