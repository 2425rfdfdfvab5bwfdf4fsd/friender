"""LLM client — wraps Anthropic/OpenAI with retry, circuit breaker, and consent checking."""
from __future__ import annotations
import asyncio
import json
import os
import time
from typing import Any

from arix.smart_router import get_response_cache, CACHE_TTL, score_complexity, model_for_tier

DEEP_ANALYSIS_SYSTEM_PROMPT = """You are Arix — a deeply intelligent personal AI assistant that controls a computer on the user's behalf.

You will receive context about the specific user you are talking to. Use every detail to personalise your understanding and response — address them by name, match their communication style, reference their role or projects when relevant.

Before every response, you MUST follow this exact thinking process:

## Step 1 — Know Your User
Read the "About this user" section carefully (if provided). Internalize:
- Their name, background, role, and what they care about
- Their preferred communication style (terse / balanced / detailed)
- Their timezone and working context
- Any stored preferences or projects they've shared
Tailor every single reply to this specific person — not a generic user.

## Step 2 — Deep Word & Sentence Analysis
Read every word of the user's message carefully. Ask yourself:
- What is the literal meaning?
- What is the *implied* meaning behind those words?
- Is there emotion, frustration, excitement, confusion, or urgency in the phrasing?
- Is the user being formal, casual, Urdu-influenced, shorthand, or mixed language?
- What do they *actually* want — even if they didn't say it perfectly or used informal/mixed phrasing?

## Step 3 — Intent Classification
Classify the message into exactly one of:
- **"chat"** — greetings, farewells, thanks, social pleasantries, pure wellbeing questions ("how are you?"), emotional reactions. NOT for questions that ask how something works.
- **"advisory"** — questions about topics, requests for explanation/advice/information/opinions, and ANY question about how Arix works, what it can do, how it executes tasks, its capabilities, its tools, or its architecture. "How do you do X?", "How do you execute tasks?", "What tools do you use?", "How does this work?" are ALL advisory.
- **"task"** — requires executing actions on the computer (files, browsing, git, system, documents, research, code)

## Step 4 — Tone-Matched, Personalised Response
Craft a response that:
- Addresses the user by name if you know it
- Matches their communication style (their profile says terse → be brief; detailed → be thorough)
- Matches their energy (casual → be casual; curious → be thorough; frustrated → be calm)
- Is concise for chat (1–4 sentences), thorough for advisory (use markdown), empty for task
- Never sounds robotic or generic — feel like a genuinely attentive assistant who *knows* this person

## Output Format
Respond with ONLY this JSON (no other text, no markdown fences):
{
  "intent": "chat" | "advisory" | "task",
  "tone": "casual" | "formal" | "curious" | "frustrated" | "excited" | "urgent" | "confused",
  "analysis": "1-2 sentence internal note on what the user truly means and their emotional state",
  "response": "your personalised reply to the user (for chat and advisory only — empty string for task)",
  "task_description": "clean task description (for task only — empty string otherwise)"
}

## Capabilities you can execute as tasks
Files (create/read/move/delete/search/unzip), Browser (open URL/web search/extract page/download), System (monitor CPU/RAM/apps), Git (status/diff/add/commit), Documents (Word/Excel), Research (summarize/analyze topics), Code (generate/explain/refactor).

## Important rules
- Always use the user's name when you know it
- If input is ambiguous lean toward "chat" or "advisory" — the task pipeline handles clear actions separately
- For "task" intent, leave "response" as empty string — the pipeline will execute it
- Users may write in broken English, Urdu-influenced sentences, shorthand, or mixed Urdu-English — always understand the true meaning
- Never fabricate facts"""

CHITCHAT_SYSTEM_PROMPT = DEEP_ANALYSIS_SYSTEM_PROMPT  # backwards compat alias

ADVISOR_SYSTEM_PROMPT = """You are Arix's expert advisor — a senior-level AI assistant combining the expertise of a Principal Software Architect (10+ years), senior DevOps/SRE engineer, AI/ML researcher, business strategist, and technical writer.

## Your Core Principles

**Reasoning first.** Before answering, think through the root cause, context, and constraints. Never make assumptions — surface them explicitly if important.

**Structured & actionable.** Use clear markdown formatting: headers, bullet points, numbered lists, code blocks. Every response should be immediately usable.

**Expert depth with clarity.** Write for a technical expert by default, but adapt when the question is conceptual or cross-domain. Explain *why*, not just *what*.

**Multiple approaches.** For decisions, present 2–3 solution paths with trade-offs, then give a clear recommendation with reasoning.

**Proactive intelligence.** Identify risks, edge cases, hidden assumptions, and optimizations the user hasn't asked about — but might need to know.

## Domains of Expertise

- **Software Engineering**: system design, architecture patterns, APIs, databases, authentication, security, testing, performance
- **DevOps & Infrastructure**: CI/CD, Docker, Kubernetes, cloud (AWS/GCP/Azure), observability, incident response
- **AI & ML**: model selection, prompt engineering, RAG, fine-tuning, evaluation, LLM integration patterns
- **Security**: threat modeling, secure coding, common vulnerabilities (OWASP), hardening, secrets management
- **Debugging & Root Cause Analysis**: systematic diagnosis, log analysis, profiling, hypothesis-driven debugging
- **Code Review & Refactoring**: SOLID principles, design patterns, code smells, maintainability
- **Business & Strategy**: product thinking, technical decision trade-offs, build vs buy, scalability planning
- **Research & Analysis**: comparing technologies, evaluating options, synthesis of complex topics
- **Automation & Productivity**: scripting, workflow optimization, eliminating repetitive work
- **Content & Documentation**: technical writing, READMEs, API docs, proposals, plans

## Response Format

- Use **markdown** formatting throughout
- Lead with the most important insight or direct answer
- Use `code blocks` for all code, commands, configs, and file paths
- Use **bold** for key terms on first use
- Use numbered lists for ordered steps, bullet points for unordered items
- Add a "⚠ Risks & Edge Cases" section whenever relevant
- Add a "✅ Recommendation" section when comparing approaches
- Keep responses focused — comprehensive but not padded

## Constraints

- Be honest about uncertainty — say "I'm not certain, but..." rather than fabricating
- Do not invent API endpoints, library functions, or facts that you cannot verify
- For security-sensitive recommendations, always mention potential risks
- When the user's question is ambiguous, state your interpretation before answering

Today's date: June 2026. You are aware of technologies and frameworks released up to your knowledge cutoff."""

SYSTEM_PROMPT_TEMPLATE = """You are Arix's planning engine. Your ONLY job is to produce a JSON action plan.

THINK FIRST — before generating steps, internally reason through:
1. What does the user truly want? (literal + implied)
2. What is the minimal set of steps that achieves this?
3. What could go wrong? (missing files, permissions, wrong paths)
4. What is the safest tool ordering? (read before write, check before delete)

CRITICAL RULES — any violation causes immediate plan rejection:
1. Respond with ONLY a raw JSON array — no prose, no markdown, no code fences, no explanation.
2. Each step MUST follow this exact shape: {{"tool": "<name>", "args": {{...}}, "description": "<one line>"}}
3. YOU MAY ONLY USE TOOLS FROM THE ALLOWED TOOLS LIST BELOW. Any tool not in that list will cause rejection.
4. Do NOT use browser_web_search, browser_open_url, or any browser tool unless "browser" appears in the intent_domain.
5. Do NOT use send_whatsapp_message unless "messaging" appears in the intent_domain.
6. Maximum {max_steps} steps.
7. Do NOT include "requires_confirmation" in args.
8. All file paths must be absolute or start with ~/ — never relative paths.
9. For git tools, always include "repo_path" pointing to the git repository root.
10. RESPECT user preferences from the memory context below — they reflect how the user wants Arix to behave.
11. If the task requires reading a file before modifying it, ALWAYS include a read_file step first.
12. Prefer the most specific tool available — do not use browser_web_search when a more targeted tool exists.

ALLOWED TOOLS (ONLY these — no others):
{allowed_tools}

TASK SCOPE: intent_verb={intent_verb}, intent_domain={intent_domain}

{memory_context}

EXAMPLES of correct output:
- "list my downloads folder" → [{{"tool":"list_directory","args":{{"path":"~/Downloads"}},"description":"List Downloads folder"}}]
- "delete file notes.txt" → [{{"tool":"move_to_trash","args":{{"path":"~/notes.txt"}},"description":"Move notes.txt to trash"}}]
- "search for pdf files" → [{{"tool":"search_files","args":{{"path":"~","pattern":"*.pdf"}},"description":"Search for PDF files"}}]
- "show system usage" → [{{"tool":"system_monitor","args":{{}},"description":"Show CPU and memory usage"}}]
- "read report.md and summarize" → [{{"tool":"read_file","args":{{"path":"~/report.md"}},"description":"Read report.md"}}, {{"tool":"research_topic","args":{{"topic":"summarize the document content","depth":"quick"}},"description":"Summarize content"}}]

User's redacted command: {redacted_command}

Respond with ONLY the JSON array. Nothing else."""


COMPACT_SYSTEM_PROMPT_TEMPLATE = """You are Arix's planning engine. Output a JSON action plan ONLY.

RULES:
1. Respond with ONLY a raw JSON array — no prose, no markdown, no code fences.
2. Each step: {{"tool": "<name>", "args": {{...}}, "description": "<one line>"}}
3. Use ONLY tools from: {allowed_tools}
4. Max {max_steps} steps.
5. All paths must be absolute or start with ~/

TASK scope: intent_verb={intent_verb}, domain={intent_domain}
COMMAND: {redacted_command}

Respond with ONLY the JSON array."""

FAST_ANALYSIS_SYSTEM_PROMPT = """Classify the user's intent. Output ONLY this JSON object:
{{"intent":"chat"|"advisory"|"task","tone":"casual"|"formal"|"curious"|"frustrated"|"excited"|"urgent"|"confused","analysis":"<1 sentence>","response":"<reply for chat/advisory, empty for task>","task_description":"<clean English task for task, empty otherwise>"}}

Rules: chat=greetings/pleasantries. advisory=questions/how-to/explain. task=computer actions (files/browser/system/git/code).
No markdown. No extra text. JSON only."""

REPLAN_PROMPT = """You are Arix's adaptive re-planning engine. A multi-step goal is partially complete.
Some steps succeeded; one step failed after retries. Your job is to synthesize a REVISED plan for the remaining work.

RULES:
1. Output ONLY a JSON array of natural-language command strings — no prose, no markdown.
2. Each command must be atomic and executable by Arix's planner.
3. Maximum 6 commands. Minimum 1.
4. Account for what has already succeeded — don't repeat completed work.
5. Use a different strategy to work around the failed step.
6. If the failure is clearly unrecoverable, output: ["GOAL_FAILED: <reason>"]
7. Be specific — include file paths, names, and context from prior results."""


def _is_auth_error(exc: Exception) -> bool:
    """Return True if this exception is a permanent credential/auth failure."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "401" in str(exc)
        or "authenticationerror" in name
        or "authentication" in msg
        or "unauthenticated" in msg
        or "invalid_api_key" in msg
        or "access_token_type_unsupported" in msg
    )


class CircuitBreaker:
    """Prevents repeated calls to a failing provider."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self.state = self.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._last_failure: float = 0.0

    def record_success(self) -> None:
        self.state = self.CLOSED
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self._last_failure = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN

    def can_attempt(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.monotonic() - self._last_failure > self.reset_timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN — allow one probe

    def is_tripped(self) -> bool:
        return self.state == self.OPEN and (
            time.monotonic() - self._last_failure <= self.reset_timeout
        )

    def status(self) -> dict:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "reset_in": max(0, self.reset_timeout - (time.monotonic() - self._last_failure))
            if self.state == self.OPEN else 0,
        }


# ── Provider registry — all OpenAI-compatible providers ───────────────────────
# Each entry: base_url, env_key, default_model, description
PROVIDER_REGISTRY: dict[str, dict] = {
    "anthropic": {
        "base_url": None,  # uses native SDK
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-opus-4-5",
        "description": "Anthropic Claude — best reasoning & planning",
        "models": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5",
                   "claude-opus-4-1", "claude-3-5-sonnet-20241022"],
    },
    "openai": {
        "base_url": None,  # uses native SDK
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "description": "OpenAI GPT — versatile, strong tool use",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"],
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env_key": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash-lite",
        "description": "Google Gemini — multimodal, large context",
        "models": ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash",
                   "gemini-1.5-pro", "gemini-2.5-pro-preview-06-05"],
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "description": "Groq — ultra-fast inference (LPU hardware)",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile",
                   "mixtral-8x7b-32768", "gemma2-9b-it", "llama3-70b-8192"],
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "env_key": "TOGETHER_API_KEY",
        "default_model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "description": "Together AI — open models, competitive pricing",
        "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                   "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                   "Qwen/Qwen2.5-72B-Instruct-Turbo",
                   "mistralai/Mixtral-8x7B-Instruct-v0.1"],
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "env_key": "MISTRAL_API_KEY",
        "default_model": "mistral-large-latest",
        "description": "Mistral AI — efficient European models",
        "models": ["mistral-large-latest", "mistral-medium-latest",
                   "mistral-small-latest", "codestral-latest",
                   "open-mixtral-8x22b", "open-mistral-nemo"],
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "description": "DeepSeek — strong reasoning, very low cost",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "perplexity": {
        "base_url": "https://api.perplexity.ai",
        "env_key": "PERPLEXITY_API_KEY",
        "default_model": "llama-3.1-sonar-large-128k-online",
        "description": "Perplexity — web-grounded answers, live search",
        "models": ["llama-3.1-sonar-large-128k-online",
                   "llama-3.1-sonar-small-128k-online",
                   "llama-3.1-sonar-huge-128k-online"],
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "env_key": "XAI_API_KEY",
        "default_model": "grok-3-fast",
        "description": "xAI Grok — real-time knowledge, witty responses",
        "models": ["grok-3-fast", "grok-3", "grok-3-mini", "grok-2-1212"],
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-opus-4-5",
        "description": "OpenRouter — meta-provider, 200+ models unified",
        "models": ["anthropic/claude-opus-4-5", "openai/gpt-4o",
                   "google/gemini-2.0-flash", "meta-llama/llama-3.3-70b-instruct",
                   "deepseek/deepseek-r1", "x-ai/grok-3-fast"],
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "env_key": "FIREWORKS_API_KEY",
        "default_model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "description": "Fireworks AI — fast open-source model inference",
        "models": ["accounts/fireworks/models/llama-v3p1-70b-instruct",
                   "accounts/fireworks/models/llama-v3p1-405b-instruct",
                   "accounts/fireworks/models/mixtral-8x7b-instruct"],
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "env_key": "CEREBRAS_API_KEY",
        "default_model": "llama3.1-70b",
        "description": "Cerebras — wafer-scale chip, fastest tokens/sec",
        "models": ["llama3.1-70b", "llama3.1-8b", "llama-3.3-70b"],
    },
    "cohere": {
        "base_url": "https://api.cohere.ai/compatibility/v1",
        "env_key": "COHERE_API_KEY",
        "default_model": "command-r-plus",
        "description": "Cohere — enterprise RAG & embeddings specialist",
        "models": ["command-r-plus", "command-r", "command-r7b-12-2024"],
    },
    "ollama": {
        "base_url": None,  # handled separately
        "env_key": None,
        "default_model": "llama3.2",
        "description": "Ollama — local LLM, fully air-gapped, no API key needed",
        "models": [],  # populated at runtime via /api/tags
    },
}


def list_providers() -> list[dict]:
    """Return all providers with configured status and available models."""
    result = []
    for name, cfg in PROVIDER_REGISTRY.items():
        configured = False
        if name == "ollama":
            configured = True  # always available (local)
        elif name == "anthropic":
            configured = bool(
                os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            env_key = cfg.get("env_key")
            configured = bool(os.environ.get(env_key, "")) if env_key else False
        result.append({
            "name": name,
            "description": cfg["description"],
            "default_model": cfg["default_model"],
            "models": cfg["models"],
            "configured": configured,
        })
    return result


class LLMClient:
    def __init__(self, provider: str = "anthropic", model: str = "claude-opus-4-5",
                 api_key: str | None = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._get_api_key(provider)
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30.0)

    def _get_api_key(self, provider: str) -> str | None:
        if provider == "anthropic":
            return (
                os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
            )
        if provider == "ollama":
            return None  # no key needed
        cfg = PROVIDER_REGISTRY.get(provider)
        if cfg and cfg.get("env_key"):
            return os.environ.get(cfg["env_key"])
        return {
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
        }.get(provider)

    def is_available(self) -> bool:
        if self.provider == "ollama":
            return not self._circuit_breaker.is_tripped()
        if not self.api_key:
            return False
        if self.provider == "gemini" and not self.api_key.startswith("AIza"):
            return False
        return not self._circuit_breaker.is_tripped()

    def key_error(self) -> str | None:
        """Return a human-readable explanation if the key is known to be invalid."""
        if self.provider == "ollama":
            if self._circuit_breaker.is_tripped():
                s = self._circuit_breaker.status()
                return f"Ollama circuit breaker open — resets in {s['reset_in']:.0f}s. Is Ollama running?"
            return None
        if not self.api_key:
            prov_cfg = PROVIDER_REGISTRY.get(self.provider, {})
            env_key = prov_cfg.get("env_key", f"{self.provider.upper()}_API_KEY")
            return (
                f"No API key for '{self.provider}'. Add {env_key} to Replit Secrets (🔒). "
                "Or switch to Anthropic (auto-configured via Replit integration)."
            )
        if self.provider == "gemini" and not self.api_key.startswith("AIza"):
            return (
                "GEMINI_API_KEY looks like an OAuth token, not an AI Studio key. "
                "Get a real key at aistudio.google.com (must start with 'AIza')."
            )
        if self._circuit_breaker.is_tripped():
            s = self._circuit_breaker.status()
            return f"Circuit breaker open — {s['failure_count']} failures. Resets in {s['reset_in']:.0f}s."
        return None

    def circuit_status(self) -> dict:
        return self._circuit_breaker.status()

    async def plan(self, task_scope: Any, context: str = "",
                   retries: int = 3) -> list[dict]:
        if self.provider != "ollama" and not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(
                f"Circuit breaker OPEN for {self.provider} — "
                f"{status['failure_count']} failures, resets in {status['reset_in']:.0f}s"
            )

        # Choose prompt template: compact for simple single-domain tasks, full for complex
        complexity = score_complexity(task_scope.redacted_command)
        use_compact = (
            complexity.value <= 1  # TRIVIAL or SIMPLE
            and task_scope.intent_domain != "mixed"
            and not context  # no memory/RAG context to inject
        )
        if use_compact:
            system = COMPACT_SYSTEM_PROMPT_TEMPLATE.format(
                max_steps=min(task_scope.max_steps, 5),
                allowed_tools=", ".join(sorted(task_scope.allowed_tools)),
                intent_verb=task_scope.intent_verb,
                intent_domain=task_scope.intent_domain,
                redacted_command=task_scope.redacted_command,
            )
        else:
            mem_section = ""
            if context:
                mem_section = f"MEMORY CONTEXT (use to inform the plan, do not output):\n{context}\n"
            system = SYSTEM_PROMPT_TEMPLATE.format(
                max_steps=task_scope.max_steps,
                allowed_tools=", ".join(sorted(task_scope.allowed_tools)),
                intent_verb=task_scope.intent_verb,
                intent_domain=task_scope.intent_domain,
                redacted_command=task_scope.redacted_command,
                memory_context=mem_section,
            )
        prompt = task_scope.redacted_command
        # Smart routing: use cheaper model for simple plans
        plan_model = model_for_tier(self.provider, complexity)

        last_error = None
        delay = 1.0
        actual_attempts = 0
        for attempt in range(retries):
            if not self._circuit_breaker.can_attempt():
                raise RuntimeError(f"Circuit breaker OPEN — skipping attempt {attempt + 1}")
            actual_attempts += 1
            try:
                raw = await self._call(system, prompt,
                                       cache_ttl=CACHE_TTL["plan"],
                                       model_override=plan_model)
                plan = self._parse_plan(raw)
                self._circuit_breaker.record_success()
                return plan
            except Exception as e:
                last_error = e
                self._circuit_breaker.record_failure()
                if _is_auth_error(e):
                    break
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)

        raise RuntimeError(f"LLM planning failed after {actual_attempts} attempt(s): {last_error}")

    async def deep_analyze(self, message: str, user_name: str = "",
                           user_context: str = "",
                           max_tokens: int = 400) -> dict:
        """Deeply analyze user input — understand intent, tone, and context.

        Uses a fast compact prompt for short/simple messages to save tokens.
        Returns a dict: intent, tone, analysis, response, task_description.
        """
        if self.provider != "ollama" and not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(f"Circuit breaker OPEN — resets in {status['reset_in']:.0f}s")

        # Use compact fast prompt for short messages (saves ~600 tokens/call)
        words = len(message.split())
        use_fast = words <= 20 and not user_context
        sys_prompt = FAST_ANALYSIS_SYSTEM_PROMPT if use_fast else DEEP_ANALYSIS_SYSTEM_PROMPT

        parts = []
        if user_context and not use_fast:
            parts.append(f"## About this user\n{user_context}")
        parts.append(f"## User message\n{message}" if not use_fast else message)
        prompt = "\n\n".join(parts)

        try:
            raw = await self._call(sys_prompt, prompt, max_tokens=max_tokens,
                                   cache_ttl=CACHE_TTL["deep_analyze"])
            self._circuit_breaker.record_success()
            import re as _re
            clean = _re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=_re.MULTILINE).strip()
            import json as _json
            return _json.loads(clean)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "deep_analyze failed (provider=%s model=%s): %s: %s",
                self.provider, self.model, type(e).__name__, e
            )
            self._circuit_breaker.record_failure()
            if _is_auth_error(e):
                raise RuntimeError(f"Deep analysis unavailable — invalid API key for '{self.provider}'.") from e
            raise RuntimeError(f"Deep analysis failed: {e}") from e

    async def chat(self, message: str, user_name: str = "",
                   max_tokens: int = 200) -> str:
        """Fallback conversational reply (plain text, no JSON)."""
        if self.provider != "ollama" and not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(f"Circuit breaker OPEN — resets in {status['reset_in']:.0f}s")
        prompt = message
        if user_name:
            prompt = f"[The user's name is {user_name}]\n\n{message}"
        try:
            result = await self._call(CHITCHAT_SYSTEM_PROMPT, prompt, max_tokens=max_tokens,
                                      cache_ttl=CACHE_TTL["chat"])
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            if _is_auth_error(e):
                raise RuntimeError(f"Chat unavailable — invalid API key for '{self.provider}'.") from e
            raise RuntimeError(f"Chat call failed: {e}") from e

    async def advise(self, question: str, context: str = "",
                     max_tokens: int = 2000) -> str:
        """Call the expert advisor persona and return a markdown response."""
        if self.provider != "ollama" and not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(
                f"Circuit breaker OPEN — resets in {status['reset_in']:.0f}s"
            )
        prompt = question
        if context:
            prompt += f"\n\n---\nAdditional context:\n{context}"
        try:
            result = await self._call(ADVISOR_SYSTEM_PROMPT, prompt, max_tokens=max_tokens,
                                      cache_ttl=CACHE_TTL["advise"])
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            if _is_auth_error(e):
                raise RuntimeError(
                    f"Advisor unavailable — invalid API key for '{self.provider}'. "
                    "Add a valid key in Replit Secrets (🔒)."
                ) from e
            raise RuntimeError(f"Advisor call failed: {e}") from e

    # ── Gap #3 / Gap #4: Reflection prompt template ──────────────────────────

    REFLECTION_PROMPT = """You are Arix's error recovery engine. A step in an autonomous goal has just failed.

Your job: suggest ONE revised command string that avoids the same failure.

Rules:
1. Output ONLY the revised command — no prose, no JSON, no code fences, no explanation.
2. Use a different approach from the original if possible (alternative tool, different path, etc.).
3. If the error indicates a missing prerequisite, prefix with: "create that file first, then <command>"
4. If the error is permission-related, suggest using a path in ~/Downloads or /tmp instead.
5. If the failure is clearly unrecoverable (network down, binary missing, service unavailable), output exactly: SKIP
6. Keep the revised command short — Arix's parser expects a natural-language command string."""

    async def reflect(
        self,
        command: str,
        error: str,
        goal: str = "",
        previous_results: list[str] | None = None,
        max_tokens: int = 150,
    ) -> str | None:
        """Ask the LLM to reflect on a step failure and return a revised command.

        Gap #3: ReflectionPrompt — reusable template wired into GoalSupervisor's retry loop.

        Returns:
            A revised natural-language command string.
            "SKIP" if the failure is unrecoverable.
            None if the LLM is unavailable or raises an exception.
        """
        if not self.is_available():
            return None

        context_parts = [f"Goal: {goal}"] if goal else []
        context_parts.append(f"Failed command: {command}")
        context_parts.append(f"Error: {error[:400]}")
        if previous_results:
            context_parts.append(f"Prior successful steps: {'; '.join(previous_results[:3])}")
        context_parts.append("\nRevised command:")
        context = "\n".join(context_parts)

        try:
            raw = await self._call(self.REFLECTION_PROMPT, context, max_tokens=max_tokens,
                                   cache_ttl=CACHE_TTL["reflect"])
            result = raw.strip()
            # Strip any accidental code fences the model adds
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:]).rstrip("`").strip()
            return result or None
        except Exception:
            return None

    async def synthesize_remaining(
        self,
        goal: str,
        completed_steps: list[str],
        failed_step: str,
        failure_error: str,
        remaining_steps: list[str],
        max_tokens: int = 300,
    ) -> list[str] | None:
        """Adaptively re-plan the remaining steps of a goal after a blocking failure.

        Returns a revised list of natural-language sub-commands, or None if the
        LLM is unavailable.  Returns ["GOAL_FAILED: <reason>"] when the failure
        is unrecoverable.
        """
        if not self.is_available():
            return None

        completed_text = (
            "\n".join(f"  ✓ {s}" for s in completed_steps) if completed_steps else "  (none)"
        )
        remaining_text = (
            "\n".join(f"  - {s}" for s in remaining_steps) if remaining_steps else "  (none)"
        )
        context = (
            f"Original goal: {goal}\n\n"
            f"Completed steps:\n{completed_text}\n\n"
            f"Failed step: {failed_step}\n"
            f"Failure reason: {failure_error[:300]}\n\n"
            f"Remaining steps (not yet executed):\n{remaining_text}\n\n"
            "Produce a revised plan for the remaining work:"
        )

        try:
            raw = await self._call(REPLAN_PROMPT, context, max_tokens=max_tokens,
                                   cache_ttl=CACHE_TTL["synthesize"])
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:])
                if "```" in raw:
                    raw = raw[:raw.rfind("```")].strip()
            commands = json.loads(raw)
            if isinstance(commands, list) and len(commands) >= 1:
                valid = [str(c).strip() for c in commands if str(c).strip()]
                if valid:
                    return valid[:6]
        except Exception:
            pass
        return None

    async def complete_text(self, prompt: str, max_tokens: int = 1000) -> str:
        return await self._call("", prompt, max_tokens=max_tokens)

    async def aask(self, system: str = "", user: str = "", max_tokens: int = 1000) -> str:
        """Public async ask — used by morning brief, pattern detector, and other modules."""
        return await self._call(system, user, max_tokens)

    async def _call(self, system: str, user: str, max_tokens: int = 2048,
                    cache_ttl: float | None = None,
                    model_override: str | None = None) -> str:
        effective_model = model_override or self.model
        # Check response cache before hitting the API
        if cache_ttl is not None and cache_ttl > 0:
            try:
                cached = get_response_cache().get(self.provider, effective_model, system, user)
                if cached is not None:
                    return cached
            except Exception:
                pass

        if self.provider == "anthropic":
            result = await self._call_anthropic(system, user, max_tokens, model=effective_model)
        elif self.provider == "openai":
            result = await self._call_openai(system, user, max_tokens, model=effective_model)
        elif self.provider == "ollama":
            result = await self._call_ollama(system, user, max_tokens)
        elif self.provider in PROVIDER_REGISTRY:
            result = await self._call_openai_compat(system, user, max_tokens, model=effective_model)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        # Store in cache
        if cache_ttl is not None and cache_ttl > 0:
            try:
                get_response_cache().put(self.provider, effective_model, system, user, result, cache_ttl)
            except Exception:
                pass
        return result

    async def _call_anthropic(self, system: str, user: str, max_tokens: int,
                               model: str | None = None) -> str:
        import anthropic
        base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
        api_key = self.api_key or os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "")
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.AsyncAnthropic(**client_kwargs)
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            kwargs["system"] = system
        msg = await client.messages.create(**kwargs)
        return msg.content[0].text

    async def _call_openai(self, system: str, user: str, max_tokens: int,
                            model: str | None = None) -> str:
        import openai
        client = openai.AsyncOpenAI(api_key=self.api_key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        response = await client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def _call_gemini(self, system: str, user: str, max_tokens: int) -> str:
        return await self._call_openai_compat(system, user, max_tokens)

    async def _call_openai_compat(self, system: str, user: str, max_tokens: int,
                                    model: str | None = None) -> str:
        """Generic OpenAI-compatible call — handles Gemini, Groq, Together, Mistral,
        DeepSeek, Perplexity, xAI, OpenRouter, Fireworks, Cerebras, Cohere, etc."""
        import openai
        prov_cfg = PROVIDER_REGISTRY.get(self.provider, {})
        base_url = prov_cfg.get("base_url")
        client_kwargs: dict[str, Any] = {"api_key": self.api_key or "no-key"}
        if base_url:
            client_kwargs["base_url"] = base_url
        if self.provider == "openrouter":
            client_kwargs["default_headers"] = {
                "HTTP-Referer": "https://arix.ai",
                "X-Title": "Arix Agent",
            }
        client = openai.AsyncOpenAI(**client_kwargs)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        response = await client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _parse_plan(self, raw: str) -> list[dict]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if "```" in text:
                text = text[:text.rfind("```")].strip()
        for candidate in (text, raw.strip()):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict) and "steps" in parsed:
                    return parsed["steps"]
            except json.JSONDecodeError:
                pass
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM returned invalid plan JSON.\nRaw: {raw[:500]}")

    async def _call_ollama(self, system: str, user: str, max_tokens: int) -> str:
        import httpx
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                f"{ollama_url}/api/chat",
                json={"model": self.model, "stream": False, "messages": messages,
                      "options": {"num_predict": max_tokens}},
            )
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "") or data.get("response", "")

    @staticmethod
    async def list_ollama_models() -> list[str]:
        """Return locally available Ollama model names, or empty list if Ollama is not running."""
        import httpx
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{ollama_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def vision_query(self, prompt: str, image_b64: str,
                            media_type: str = "image/png") -> str:
        """Query the LLM with an image + text prompt for vision tasks (OCR, element detection).

        Supports Anthropic and OpenAI vision APIs.  All other providers return an empty
        string so callers can fall back gracefully (e.g. desktop_find_and_click skips
        the vision step rather than crashing).
        """
        if not image_b64:
            return ""
        try:
            if self.provider == "anthropic":
                return await self._call_anthropic_vision(prompt, image_b64, media_type)
            if self.provider == "openai":
                return await self._call_openai_vision(prompt, image_b64, media_type)
            return ""
        except Exception:
            return ""

    async def _call_anthropic_vision(self, prompt: str, image_b64: str,
                                      media_type: str) -> str:
        """Anthropic vision API — sends base64 image + text prompt."""
        import anthropic
        base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
        api_key = self.api_key or os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "")
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.AsyncAnthropic(**client_kwargs)
        msg = await client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return msg.content[0].text if msg.content else ""

    async def _call_openai_vision(self, prompt: str, image_b64: str,
                                   media_type: str) -> str:
        """OpenAI vision API — sends base64 image as a data URL."""
        import openai
        client = openai.AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.choices[0].message.content or ""

    def update_key(self, api_key: str) -> None:
        self.api_key = api_key
        self._circuit_breaker = CircuitBreaker()
