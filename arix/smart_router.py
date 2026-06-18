"""SmartRouter — response cache, complexity classifier, and model tier selector.

Three responsibilities:
1. ResponseCache — TTL LRU cache that prevents duplicate LLM API calls entirely.
2. score_complexity — fast heuristic classifying commands as TRIVIAL/SIMPLE/MEDIUM/COMPLEX.
3. model_for_tier — maps (provider, complexity) to the cheapest capable model.
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from enum import IntEnum


# ── Complexity tiers ──────────────────────────────────────────────────────────

class Complexity(IntEnum):
    TRIVIAL = 0   # Pure chitchat — no LLM needed, answered offline
    SIMPLE  = 1   # Single domain, 1-2 step clear action
    MEDIUM  = 2   # 2-3 domains or moderate multi-step task
    COMPLEX = 3   # Research, code gen, multi-domain goals, long plans


_TRIVIAL_PHRASES = frozenset({
    "hi", "hello", "hey", "yo", "hiya", "howdy",
    "thanks", "thank you", "thx", "ty", "cheers",
    "bye", "goodbye", "see you", "cya", "later",
    "how are you", "how r u", "how are u",
    "good morning", "good afternoon", "good evening", "good night",
})

_COMPLEX_KEYWORDS = frozenset({
    "research", "investigate", "analyze", "analyse",
    "generate code", "write code", "write a script",
    "refactor", "explain code", "debug",
    "summarize", "summarise", "compare", "evaluate",
    "multi-step", "step by step",
})

_MEDIUM_KEYWORDS = frozenset({
    "search", "find", "look up", "browse", "open website",
    "gmail", "slack", "notion", "drive", "calendar",
    "trello", "spotify", "youtube", "whatsapp",
    "download", "upload", "screenshot",
})

_CONNECTORS = frozenset({"and then", "after that", "finally", "first then", "next then"})


def score_complexity(command: str, domains: set[str] | None = None) -> Complexity:
    """Fast heuristic complexity score — no LLM, no I/O."""
    lower = command.lower().strip()
    words = lower.split()

    if len(words) <= 6:
        if lower in _TRIVIAL_PHRASES:
            return Complexity.TRIVIAL
        for phrase in _TRIVIAL_PHRASES:
            if lower.startswith(phrase):
                return Complexity.TRIVIAL

    if any(kw in lower for kw in _COMPLEX_KEYWORDS):
        return Complexity.COMPLEX

    if domains and len(domains) >= 3:
        return Complexity.COMPLEX

    connector_count = sum(1 for c in _CONNECTORS if c in lower)
    if connector_count >= 2:
        return Complexity.COMPLEX
    if connector_count == 1:
        return Complexity.MEDIUM

    if domains and len(domains) == 2:
        return Complexity.MEDIUM

    if any(kw in lower for kw in _MEDIUM_KEYWORDS):
        return Complexity.MEDIUM

    if len(words) > 15:
        return Complexity.MEDIUM

    return Complexity.SIMPLE


# ── Model tier map ────────────────────────────────────────────────────────────
# Always use the cheapest model that meets the quality bar for that tier.
# SIMPLE/MEDIUM use lite/mini models; COMPLEX upgrades one level.

_TIER_MAP: dict[str, dict[Complexity, str]] = {
    "gemini": {
        Complexity.TRIVIAL: "gemini-2.0-flash-lite",
        Complexity.SIMPLE:  "gemini-2.0-flash-lite",
        Complexity.MEDIUM:  "gemini-2.0-flash-lite",
        Complexity.COMPLEX: "gemini-2.0-flash",
    },
    "anthropic": {
        Complexity.TRIVIAL: "claude-haiku-4-5",
        Complexity.SIMPLE:  "claude-haiku-4-5",
        Complexity.MEDIUM:  "claude-haiku-4-5",
        Complexity.COMPLEX: "claude-sonnet-4-5",
    },
    "openai": {
        Complexity.TRIVIAL: "gpt-4o-mini",
        Complexity.SIMPLE:  "gpt-4o-mini",
        Complexity.MEDIUM:  "gpt-4o-mini",
        Complexity.COMPLEX: "gpt-4o",
    },
    "groq": {
        Complexity.TRIVIAL: "gemma2-9b-it",
        Complexity.SIMPLE:  "gemma2-9b-it",
        Complexity.MEDIUM:  "llama-3.3-70b-versatile",
        Complexity.COMPLEX: "llama-3.3-70b-versatile",
    },
    "mistral": {
        Complexity.TRIVIAL: "mistral-small-latest",
        Complexity.SIMPLE:  "mistral-small-latest",
        Complexity.MEDIUM:  "mistral-small-latest",
        Complexity.COMPLEX: "mistral-large-latest",
    },
    "deepseek": {
        Complexity.TRIVIAL: "deepseek-chat",
        Complexity.SIMPLE:  "deepseek-chat",
        Complexity.MEDIUM:  "deepseek-chat",
        Complexity.COMPLEX: "deepseek-reasoner",
    },
}


def model_for_tier(provider: str, complexity: Complexity) -> str | None:
    """Return the optimal model name for (provider, complexity).

    Returns None if the provider has no tier map — caller keeps its default.
    """
    return _TIER_MAP.get(provider, {}).get(complexity)


# ── TTL LRU response cache ────────────────────────────────────────────────────

# Default TTLs per call type
CACHE_TTL: dict[str, float] = {
    "plan":        120.0,   # task plans — same command often repeated
    "deep_analyze": 300.0,  # intent analysis — message text never changes
    "advise":      600.0,   # advisory answers — frequently repeated questions
    "chat":        300.0,   # chitchat replies
    "reflect":      60.0,   # error reflection — context-sensitive, shorter TTL
    "synthesize":  120.0,   # goal replan
    "sanitize":    600.0,   # content sanitization — content never changes
}

_CACHE_MAX_SIZE = 1_000


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: str, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class ResponseCache:
    """Single-process TTL LRU cache for LLM text responses.

    Cache key = SHA-256 of (provider, model, first 300 chars of system, full user prompt).
    Eviction: LRU once max_size is reached; expired entries lazily pruned on access.
    """

    def __init__(self, max_size: int = _CACHE_MAX_SIZE) -> None:
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._saves = 0

    def get(self, provider: str, model: str, system: str, user: str) -> str | None:
        key = _cache_key(provider, model, system, user)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        self._saves += 1
        return entry.value

    def put(self, provider: str, model: str, system: str, user: str,
            value: str, ttl: float = 300.0) -> None:
        key = _cache_key(provider, model, system, user)
        while len(self._store) >= self._max_size:
            self._store.popitem(last=False)
        self._store[key] = _Entry(value, time.monotonic() + ttl)
        self._store.move_to_end(key)

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits":     self._hits,
            "misses":   self._misses,
            "hit_rate": round(self._hits / total, 3) if total else 0.0,
            "api_calls_saved": self._saves,
            "size":     len(self._store),
            "max_size": self._max_size,
        }

    def clear(self) -> None:
        self._store.clear()
        self._hits = self._misses = self._saves = 0


def _cache_key(provider: str, model: str, system: str, user: str) -> str:
    payload = f"{provider}\x00{model}\x00{system[:300]}\x00{user}"
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


# ── Global singleton ──────────────────────────────────────────────────────────

_response_cache = ResponseCache()


def get_response_cache() -> ResponseCache:
    return _response_cache
