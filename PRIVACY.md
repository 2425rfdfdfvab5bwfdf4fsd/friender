# Privacy Policy — PACCA v8.0

## Data Collected Locally

PACCA stores the following data **only on your local machine** (`~/.pacca/`):

| File / Database | Contents | Retention |
|-----------------|----------|-----------|
| `memory.db` | Task history, preferences, skill library | Until you delete it |
| `used_grants.db` | Consumed grant IDs (no personal data) | Auto-pruned after TTL expires |
| `audit.log` | Redacted command summaries, tool names, risk scores | Until you delete it |
| `config.json` | Configuration (no secrets) | Until you delete it |

Audit logs are written at permission `0600` (owner read/write only).

## Data Sent to External Services

PACCA may send data to external LLM providers **only when a key is configured**:

### Anthropic (Claude)
- What is sent: the **redacted** command text (secrets/credentials stripped by `LocalTextRedactor`), relevant memory context, plan steps
- What is NOT sent: raw file contents unless you explicitly ask PACCA to read a file as part of a task
- Privacy policy: https://www.anthropic.com/privacy

### OpenAI (GPT / embeddings)
- What is sent: same as Anthropic above; also text chunks for semantic memory indexing
- Privacy policy: https://openai.com/policies/privacy-policy

You are shown an **egress notice** before data is sent to any external provider (configurable via `show_egress_notices` in config).

## Credentials & Secrets

- PACCA **never** logs raw credentials or API keys
- `LocalTextRedactor` strips patterns matching passwords, tokens, SSH keys, credit card numbers, and email addresses **before** any text reaches the LLM
- API keys are loaded from environment variables and never written to disk by PACCA

## Your Rights

You can delete all locally stored data at any time:

```bash
rm -rf ~/.pacca/
```

## Contact

If you have privacy concerns, contact the maintainer privately (see `SECURITY.md`).
