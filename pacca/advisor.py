"""AdvisoryIntentDetector — classifies a command as advisory (question/analysis)
vs. action (computer-control tool invocation).

Advisory commands go to the expert LLM advisor persona.
Action commands go to the normal tool-execution pipeline.
"""
from __future__ import annotations
import re

# ── Explicit prefixes that force advisory mode ───────────────────────────────
ADVISORY_PREFIXES: tuple[str, ...] = (
    "ask:",
    "ask ",
    "?",
    "explain ",
    "explain:",
    "advise ",
    "analyze ",
    "analyse ",
    "review ",
    "compare ",
    "suggest ",
    "recommend ",
    "help me ",
    "how do i ",
    "how do you ",
    "how should i ",
    "how would i ",
    "how can i ",
    "what is ",
    "what are ",
    "what's ",
    "what was ",
    "what would ",
    "what should ",
    "why is ",
    "why are ",
    "why does ",
    "why do ",
    "why would ",
    "why should ",
    "which is ",
    "which are ",
    "which would ",
    "who is ",
    "who are ",
    "when should ",
    "when would ",
    "should i ",
    "could you ",
    "can you explain",
    "can you help",
    "can you analyze",
    "can you review",
    "can you describe",
    "can you compare",
    "can you suggest",
    "can you recommend",
    "can you assess",
    "can you outline",
    "can you write ",
    "can you create a plan",
    "can you design",
    "tell me ",
    "give me ",
    "show me how",
    "walk me through",
    "describe ",
    "diagnose ",
    "troubleshoot ",
    "debug this:",
    "debug this ",
    "think through",
    "brainstorm ",
    "draft ",
    "outline ",
    "summarize ",
    "summarise ",
    "write a ",
    "write an ",
    "design a ",
    "design an ",
    "plan a ",
    "plan an ",
    "plan for ",
    "assess ",
    "evaluate ",
    "critique ",
    "pros and cons",
    "trade-off",
    "tradeoff",
    "best practice",
    "best approach",
    "best way",
    "difference between",
    "vs ",
    "versus ",
    "what's the best",
    "what is the best",
    "how to ",
    "i need advice",
    "i need help",
    "i'm stuck",
    "i am stuck",
    "i don't understand",
    "i do not understand",
    "explain the",
    "explain this",
    "explain how",
    "explain why",
    "explain what",
    "is it possible",
    "is there a way",
    "are there any",
    "are there ways",
)

# ── Action command prefixes (NOT advisory) ────────────────────────────────────
ACTION_PREFIXES: tuple[str, ...] = (
    "list ",
    "ls ",
    "create a file",
    "create file",
    "create a folder",
    "create folder",
    "create a directory",
    "make a file",
    "make file",
    "make folder",
    "make a folder",
    "move ",
    "mv ",
    "rename ",
    "copy ",
    "cp ",
    "delete ",
    "trash ",
    "remove file",
    "remove folder",
    "unzip ",
    "extract ",
    "zip ",
    "compress ",
    "read the file",
    "read file",
    "open file",
    "open url",
    "open app",
    "close app",
    "launch app",
    "start app",
    "git status",
    "git diff",
    "git add",
    "git commit",
    "git log",
    "git push",
    "git pull",
    "show system",
    "send whatsapp",
    "search for files",
    "search files",
    "find files",
    "find all",
    "search the web",
    "web search",
    "download ",
    "dry-run:",
    "dry run:",
    "dryrun:",
)

# ── Advisory content patterns (phrase-level) ─────────────────────────────────
ADVISORY_PATTERNS: list[re.Pattern] = [re.compile(p, re.I) for p in [
    r'\b(explain|elaborat|clarify|describ)\b',
    r'\b(analyz|analys|evaluat|assess)\b',
    r'\b(recommend|suggest|advise|proposes?)\b',
    r'\b(pros?\s+and\s+cons?|trade.?offs?|advantages?|disadvantages?)\b',
    r'\b(best\s+practice|best\s+approach|best\s+way|better\s+approach)\b',
    r'\b(architecture|design\s+pattern|design\s+principle)\b',
    r'\b(what\s+is|what\s+are|what\'s)\b',
    r'\b(how\s+(do|does|can|should|would|to))\b',
    r'\b(why\s+(is|are|does|do|would|should))\b',
    r'\b(difference\s+between|compare\s+.+\s+(to|with|vs|versus))\b',
    r'\b(debugging|troubleshoot|root\s+cause|diagnos)\b',
    r'\b(optimiz|improv|refactor|restructur)\b',
    r'\b(secur(ity|e)|vulnerab|exploit|harden)\b',
    r'\b(scalab|performanc|bottleneck|throughput|latency)\b',
    r'\b(help\s+me|assist\s+me|guide\s+me|walk\s+me)\b',
    r'\bhow\s+should\s+I\b',
    r'\bshould\s+I\b',
    r'\bcan\s+you\s+(explain|help|analyze|review|suggest|recommend|write|design|plan|create\s+a\s+plan|outline|assess)\b',
    r'\bstrateg(y|ies|ic)\b',
    r'\bplan\s+(for|to|a|an)\b',
    r'\b(brainstorm|ideate|idea\s+for)\b',
    r'\b(write\s+a|draft\s+a|compose\s+a|generate\s+a)\b.*(plan|report|email|letter|proposal|summary|outline|strategy|spec|document)\b',
    r'\bI\s+(need|want)\s+(advice|help|guidance|your\s+opinion|your\s+thoughts)\b',
    r'\bwhat\s+would\s+you\b',
    r'\byour\s+(opinion|thought|recommendation|suggestion|advice)\b',
    r'\b(is|are)\s+there\s+(a|any|better)\b',
    r'\b(overview|summary|breakdown)\s+of\b',
    r'\b(think\s+through|walk\s+(me\s+)?through|talk\s+me\s+through)\b',
]]


def _low(s: str) -> str:
    return s.lower().strip()


class AdvisoryIntentDetector:
    """
    Classifies a raw user command as advisory (conversational/analytical)
    or as an action (computer-control tool invocation).

    Uses a layered approach:
    1. Explicit force prefixes ("ask:", "?") → always advisory
    2. Clear action verb prefixes → always action
    3. Question-word prefixes → advisory
    4. Content-pattern matching → advisory if strong signal found
    5. Default → action (let the normal pipeline decide)
    """

    def is_advisory(self, command: str) -> bool:
        low = _low(command)

        # 1. Explicit advisory force prefix
        if low.startswith("ask:") or low.startswith("ask ") or low.startswith("?"):
            return True

        # 2. Clear action prefixes → NOT advisory
        for prefix in ACTION_PREFIXES:
            if low.startswith(prefix):
                return False

        # 3. Advisory starter phrases
        for prefix in ADVISORY_PREFIXES:
            if low.startswith(prefix):
                return True

        # 4. Advisory content patterns
        for pat in ADVISORY_PATTERNS:
            if pat.search(command):
                return True

        # 5. Ends with a question mark → likely advisory
        if command.strip().endswith("?"):
            return True

        return False
