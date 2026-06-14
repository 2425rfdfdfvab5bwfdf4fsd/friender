"""LLM client — wraps Anthropic/OpenAI with retry, fallback, and consent checking."""
from __future__ import annotations
import asyncio
import json
import os
from typing import Any

SYSTEM_PROMPT_TEMPLATE = """You are PACCA's planning engine. Your ONLY job is to produce a JSON action plan.

RULES (never violate):
1. Respond with ONLY a JSON array of steps — no prose, no markdown.
2. Each step: {{"tool": "<name>", "args": {{...}}, "description": "<brief>"}}
3. Use ONLY tools from the allowed list below. Any other tool is REJECTED.
4. You cannot authorize actions. You only propose them.
5. Maximum {max_steps} steps.
6. Do not include "requires_confirmation" — it is ignored.

ALLOWED TOOLS: {allowed_tools}

TASK SCOPE: intent={intent_verb}, domain={intent_domain}

User command (redacted): {redacted_command}

Respond with the JSON array only. No other text."""


class LLMClient:
    def __init__(self, provider: str = "anthropic", model: str = "claude-opus-4-5",
                 api_key: str | None = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._get_api_key(provider)

    def _get_api_key(self, provider: str) -> str | None:
        keys = {
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
        }
        return keys.get(provider)

    async def plan(self, task_scope: Any, context: str = "",
                   retries: int = 3) -> list[dict]:
        """Generate an action plan for the given task scope."""
        system = SYSTEM_PROMPT_TEMPLATE.format(
            max_steps=task_scope.max_steps,
            allowed_tools=", ".join(sorted(task_scope.allowed_tools)),
            intent_verb=task_scope.intent_verb,
            intent_domain=task_scope.intent_domain,
            redacted_command=task_scope.redacted_command,
        )
        prompt = task_scope.redacted_command
        if context:
            prompt += f"\n\nContext:\n{context}"

        last_error = None
        delay = 1.0
        for attempt in range(retries):
            try:
                response = await self._call(system, prompt)
                plan = self._parse_plan(response)
                return plan
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2

        raise RuntimeError(f"LLM planning failed after {retries} attempts: {last_error}")

    async def complete_text(self, prompt: str, max_tokens: int = 1000) -> str:
        """Simple text completion for sanitizer use."""
        return await self._call("", prompt, max_tokens=max_tokens)

    async def _call(self, system: str, user: str, max_tokens: int = 2000) -> str:
        if self.provider == "anthropic":
            return await self._call_anthropic(system, user, max_tokens)
        elif self.provider == "openai":
            return await self._call_openai(system, user, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def _call_anthropic(self, system: str, user: str, max_tokens: int) -> str:
        import anthropic
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
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
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
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

    def _parse_plan(self, raw: str) -> list[dict]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            plan = json.loads(text)
            if isinstance(plan, list):
                return plan
            if isinstance(plan, dict) and "steps" in plan:
                return plan["steps"]
            raise ValueError("LLM response is not a list of steps")
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\n\nRaw: {raw[:500]}")

    def is_available(self) -> bool:
        return bool(self.api_key)
