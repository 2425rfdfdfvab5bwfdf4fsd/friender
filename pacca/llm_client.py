"""LLM client — wraps Anthropic/OpenAI with retry, circuit breaker, and consent checking."""
from __future__ import annotations
import asyncio
import json
import os
import time
from typing import Any

DEEP_ANALYSIS_SYSTEM_PROMPT = """You are PACCA — a deeply intelligent personal AI assistant that controls a computer on the user's behalf.

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
- **"chat"** — greeting, casual conversation, social messages, emotional expression, thanks, farewells, reactions, simple questions about you
- **"advisory"** — questions about topics, requests for explanation/advice/information/opinions that don't require executing computer actions
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

ADVISOR_SYSTEM_PROMPT = """You are PACCA's expert advisor — a senior-level AI assistant combining the expertise of a Principal Software Architect (10+ years), senior DevOps/SRE engineer, AI/ML researcher, business strategist, and technical writer.

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

SYSTEM_PROMPT_TEMPLATE = """You are PACCA's planning engine. Your ONLY job is to produce a JSON action plan.

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
10. RESPECT user preferences from the memory context below — they reflect how the user wants PACCA to behave.

ALLOWED TOOLS (ONLY these — no others):
{allowed_tools}

TASK SCOPE: intent_verb={intent_verb}, intent_domain={intent_domain}

{memory_context}

EXAMPLES of correct output:
- "list my downloads folder" → [{{"tool":"list_directory","args":{{"path":"~/Downloads"}},"description":"List Downloads folder"}}]
- "delete file notes.txt" → [{{"tool":"move_to_trash","args":{{"path":"~/notes.txt"}},"description":"Move notes.txt to trash"}}]
- "search for pdf files" → [{{"tool":"search_files","args":{{"path":"~","pattern":"*.pdf"}},"description":"Search for PDF files"}}]
- "show system usage" → [{{"tool":"system_monitor","args":{{}},"description":"Show CPU and memory usage"}}]

User's redacted command: {redacted_command}

Respond with ONLY the JSON array. Nothing else."""


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


class LLMClient:
    def __init__(self, provider: str = "anthropic", model: str = "claude-opus-4-5",
                 api_key: str | None = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._get_api_key(provider)
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30.0)

    def _get_api_key(self, provider: str) -> str | None:
        if provider == "anthropic":
            # Prefer Replit AI Integrations managed key, fall back to user-supplied key
            return (
                os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
            )
        return {
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
        }.get(provider)

    def is_available(self) -> bool:
        if self.provider == "ollama":
            return not self._circuit_breaker.is_tripped()
        if not self.api_key:
            return False
        # Gemini keys must start with "AIza" — OAuth tokens (AQ.*, ya29.*) always 401
        if self.provider == "gemini" and not self.api_key.startswith("AIza"):
            return False
        return not self._circuit_breaker.is_tripped()

    def key_error(self) -> str | None:
        """Return a human-readable explanation if the key is known to be invalid."""
        if not self.api_key:
            return (
                "No API key configured. Add ANTHROPIC_API_KEY or GEMINI_API_KEY "
                "in Replit Secrets (🔒 sidebar)."
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
        if not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(
                f"Circuit breaker OPEN for {self.provider} — "
                f"{status['failure_count']} failures, resets in {status['reset_in']:.0f}s"
            )

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

        last_error = None
        delay = 1.0
        actual_attempts = 0
        for attempt in range(retries):
            if not self._circuit_breaker.can_attempt():
                raise RuntimeError(f"Circuit breaker OPEN — skipping attempt {attempt + 1}")
            actual_attempts += 1
            try:
                raw = await self._call(system, prompt)
                plan = self._parse_plan(raw)
                self._circuit_breaker.record_success()
                return plan
            except Exception as e:
                last_error = e
                self._circuit_breaker.record_failure()
                # Auth / credential errors are permanent — no point retrying
                if _is_auth_error(e):
                    break
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)

        raise RuntimeError(f"LLM planning failed after {actual_attempts} attempt(s): {last_error}")

    async def deep_analyze(self, message: str, user_name: str = "",
                           user_context: str = "",
                           max_tokens: int = 1024) -> dict:
        """Deeply analyze user input — understand intent, tone, and context.

        user_context: rich string about who the user is (profile, preferences, history).
        Returns a dict with keys:
          intent: "chat" | "advisory" | "task"
          tone: str
          analysis: str (internal reasoning)
          response: str (for chat/advisory; empty for task)
          task_description: str (for task; empty otherwise)
        """
        if not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(f"Circuit breaker OPEN — resets in {status['reset_in']:.0f}s")

        parts = []
        if user_context:
            parts.append(f"## About this user\n{user_context}")
        parts.append(f"## User message\n{message}")
        prompt = "\n\n".join(parts)

        try:
            raw = await self._call(DEEP_ANALYSIS_SYSTEM_PROMPT, prompt, max_tokens=max_tokens)
            self._circuit_breaker.record_success()
            # Strip markdown code fences the model may add despite instructions
            import re as _re
            clean = _re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=_re.MULTILINE).strip()
            import json as _json
            return _json.loads(clean)
        except Exception as e:
            self._circuit_breaker.record_failure()
            if _is_auth_error(e):
                raise RuntimeError(f"Deep analysis unavailable — invalid API key for '{self.provider}'.") from e
            raise RuntimeError(f"Deep analysis failed: {e}") from e

    async def chat(self, message: str, user_name: str = "",
                   max_tokens: int = 512) -> str:
        """Fallback conversational reply (plain text, no JSON)."""
        if not self.api_key:
            raise RuntimeError(f"No API key for provider '{self.provider}'")
        if self._circuit_breaker.is_tripped():
            status = self._circuit_breaker.status()
            raise RuntimeError(f"Circuit breaker OPEN — resets in {status['reset_in']:.0f}s")
        prompt = message
        if user_name:
            prompt = f"[The user's name is {user_name}]\n\n{message}"
        try:
            result = await self._call(CHITCHAT_SYSTEM_PROMPT, prompt, max_tokens=max_tokens)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            if _is_auth_error(e):
                raise RuntimeError(f"Chat unavailable — invalid API key for '{self.provider}'.") from e
            raise RuntimeError(f"Chat call failed: {e}") from e

    async def advise(self, question: str, context: str = "",
                     max_tokens: int = 4096) -> str:
        """Call the expert advisor persona and return a markdown response."""
        if not self.api_key:
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
            result = await self._call(ADVISOR_SYSTEM_PROMPT, prompt, max_tokens=max_tokens)
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

    async def complete_text(self, prompt: str, max_tokens: int = 1000) -> str:
        return await self._call("", prompt, max_tokens=max_tokens)

    async def aask(self, system: str = "", user: str = "", max_tokens: int = 1000) -> str:
        """Public async ask — used by morning brief, pattern detector, and other modules."""
        return await self._call(system, user, max_tokens)

    async def _call(self, system: str, user: str, max_tokens: int = 2048) -> str:
        if self.provider == "anthropic":
            return await self._call_anthropic(system, user, max_tokens)
        elif self.provider == "openai":
            return await self._call_openai(system, user, max_tokens)
        elif self.provider == "gemini":
            return await self._call_gemini(system, user, max_tokens)
        elif self.provider == "ollama":
            return await self._call_ollama(system, user, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def _call_anthropic(self, system: str, user: str, max_tokens: int) -> str:
        import anthropic
        # Use Replit AI Integrations proxy URL when available
        base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
        api_key = self.api_key or os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "")
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.AsyncAnthropic(**client_kwargs)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            kwargs["system"] = system
        msg = await client.messages.create(**kwargs)
        return msg.content[0].text

    async def _call_openai(self, system: str, user: str, max_tokens: int) -> str:
        import openai
        client = openai.AsyncOpenAI(api_key=self.api_key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    async def _call_gemini(self, system: str, user: str, max_tokens: int) -> str:
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

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
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "http://localhost:11434/api/chat",
                json={"model": self.model, "stream": False, "messages": messages,
                      "options": {"num_predict": max_tokens}},
            )
            r.raise_for_status()
            return r.json()["message"]["content"]

    def update_key(self, api_key: str) -> None:
        self.api_key = api_key
        self._circuit_breaker = CircuitBreaker()
