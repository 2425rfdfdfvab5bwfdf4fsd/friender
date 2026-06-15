"""LLM client — wraps Anthropic/OpenAI with retry, circuit breaker, and consent checking."""
from __future__ import annotations
import asyncio
import json
import os
import time
from typing import Any

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

ALLOWED TOOLS (ONLY these — no others):
{allowed_tools}

TASK SCOPE: intent_verb={intent_verb}, intent_domain={intent_domain}

EXAMPLES of correct output:
- "list my downloads folder" → [{{"tool":"list_directory","args":{{"path":"~/Downloads"}},"description":"List Downloads folder"}}]
- "delete file notes.txt" → [{{"tool":"move_to_trash","args":{{"path":"~/notes.txt"}},"description":"Move notes.txt to trash"}}]
- "search for pdf files" → [{{"tool":"search_files","args":{{"path":"~","pattern":"*.pdf"}},"description":"Search for PDF files"}}]
- "show system usage" → [{{"tool":"system_monitor","args":{{}},"description":"Show CPU and memory usage"}}]

User's redacted command: {redacted_command}

Respond with ONLY the JSON array. Nothing else."""


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
        return {
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
        }.get(provider)

    def is_available(self) -> bool:
        if self.provider == "ollama":
            return not self._circuit_breaker.is_tripped()
        return bool(self.api_key) and not self._circuit_breaker.is_tripped()

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

        system = SYSTEM_PROMPT_TEMPLATE.format(
            max_steps=task_scope.max_steps,
            allowed_tools=", ".join(sorted(task_scope.allowed_tools)),
            intent_verb=task_scope.intent_verb,
            intent_domain=task_scope.intent_domain,
            redacted_command=task_scope.redacted_command,
        )
        prompt = task_scope.redacted_command
        if context:
            prompt += f"\n\nAdditional context:\n{context}"

        last_error = None
        delay = 1.0
        for attempt in range(retries):
            if not self._circuit_breaker.can_attempt():
                raise RuntimeError(f"Circuit breaker OPEN — skipping attempt {attempt + 1}")
            try:
                raw = await self._call(system, prompt)
                plan = self._parse_plan(raw)
                self._circuit_breaker.record_success()
                return plan
            except Exception as e:
                last_error = e
                self._circuit_breaker.record_failure()
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)

        raise RuntimeError(f"LLM planning failed after {retries} attempts: {last_error}")

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
            raise RuntimeError(f"Advisor call failed: {e}") from e

    async def complete_text(self, prompt: str, max_tokens: int = 1000) -> str:
        return await self._call("", prompt, max_tokens=max_tokens)

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
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
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
